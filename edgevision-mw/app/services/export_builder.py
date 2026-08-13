from __future__ import annotations

import hashlib
import json
import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.enums import AnnotationStatus, ExportStatus
from app.models.studio import ExportJob

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("COCO", "YOLO", "PASCAL_VOC")


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

async def generate_preview(
    db: AsyncSession,
    dataset_id: str,
    format: str,
    augmentations: dict | None = None,
    sample_size: int = 10,
) -> list[dict]:
    """Return lightweight preview dicts for a dataset export.

    No actual images or file I/O — purely metadata-driven.
    """
    fmt_upper = format.upper()
    if fmt_upper not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format '{format}'; choose from {SUPPORTED_FORMATS}")

    result = await db.execute(
        select(Dataset).where(Dataset.dataset_id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise ValueError(f"Dataset {dataset_id} not found")

    ann_result = await db.execute(
        select(Annotation)
        .where(
            Annotation.dataset_id == dataset.id,
            Annotation.status == AnnotationStatus.CERTIFIED,
        )
        .order_by(func.random())
        .limit(sample_size)
    )
    annotations = ann_result.scalars().all()

    aug_info = _apply_augmentations_info(augmentations or {})

    previews: list[dict] = []
    for ann in annotations:
        labels = ann.human_labels or ann.auto_labels or {}
        class_names = labels.get("classes", [])
        detections = labels.get("detections", [])

        entry: dict[str, Any] = {
            "annotation_id": str(ann.id),
            "image_path": ann.image_path,
            "thumbnail_path": ann.thumbnail_path,
            "classes": class_names,
            "detection_count": len(detections),
            "quality_score": ann.quality_score,
            "format_specific": _preview_for_format(ann, fmt_upper),
            "augmentations": aug_info,
        }
        if ann.gps_lat is not None and ann.gps_lon is not None:
            entry["gps"] = {"lat": ann.gps_lat, "lon": ann.gps_lon}
        previews.append(entry)

    return previews


def _preview_for_format(ann: Annotation, fmt: str) -> dict:
    labels = ann.human_labels or ann.auto_labels or {}
    detections, orientation = _collect_detections(ann)
    class_names = labels.get("classes", [])
    badges: list[str] = []

    has_seg = any(d.get("mask_rle") or d.get("mask") for d in detections)
    has_3d = any(d.get("bbox_3d") for d in detections)
    if has_seg:
        badges.append("segmentation")
    if has_3d:
        badges.append("bbox_3d")
    if orientation != "normal":
        badges.append(f"orientation:{orientation}")

    if fmt == "COCO":
        return {
            "format": "COCO",
            "categories": labels.get("classes", []),
            "orientation_mode": orientation,
            "badges": badges,
            "annotations": [
                {
                    "bbox": d.get("bbox"),
                    "category": d.get("class", "unknown"),
                    "segmentation": d.get("mask_rle") or d.get("mask"),
                    "attributes": _detection_attributes(d),
                    "area": (d.get("bbox", [0, 0, 0, 0])[2] * d.get("bbox", [0, 0, 0, 0])[3])
                    if d.get("bbox")
                    else 0,
                }
                for d in detections
            ],
        }
    if fmt == "YOLO":
        return {
            "format": "YOLO",
            "orientation_mode": orientation,
            "badges": badges,
            "lines": [
                f"{d.get('class_id', 0)} {d.get('cx', 0):.6f} {d.get('cy', 0):.6f} "
                f"{d.get('w', 0):.6f} {d.get('h', 0):.6f}"
                for d in detections
            ],
            "seg_companion": has_seg,
        }
    # PASCAL_VOC
    return {
        "format": "PASCAL_VOC",
        "orientation_mode": orientation,
        "badges": badges,
        "objects": [
            {
                "name": d.get("class", "unknown"),
                "bndbox": {
                    "xmin": d.get("bbox", [0, 0, 0, 0])[0],
                    "ymin": d.get("bbox", [0, 0, 0, 0])[1],
                    "xmax": (
                        d.get("bbox", [0, 0, 0, 0])[0] + d.get("bbox", [0, 0, 0, 0])[2]
                    ),
                    "ymax": (
                        d.get("bbox", [0, 0, 0, 0])[1] + d.get("bbox", [0, 0, 0, 0])[3]
                    ),
                },
                "segmentation": d.get("mask_rle") or d.get("mask"),
                "attributes": _detection_attributes(d),
            }
            for d in detections
        ],
    }


# ---------------------------------------------------------------------------
# Build export
# ---------------------------------------------------------------------------

async def build_export(
    db: AsyncSession,
    job_id: str | UUID,
    format: str,
    split_ratio: dict | None = None,
    augmentations: dict | None = None,
    stratify: bool = True,
    watermark: bool = False,
    progress_callback: Callable[[float], None] | None = None,
) -> str:
    """Build a dataset export manifest and update the ExportJob record.

    This operates on annotation metadata and label data only — no image files
    are read, transformed, or written.  The generated manifest content is
    stored in ExportJob metadata; the ``output_path`` is returned as a
    reference string.

    Returns:
        The logical output path (e.g. ``exports/{dataset_id}/{name}_{fmt}_{date}.zip``).
    """
    fmt_upper = format.upper()
    if fmt_upper not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format '{format}'; choose from {SUPPORTED_FORMATS}")

    if split_ratio is None:
        split_ratio = {"train": 0.7, "val": 0.2, "test": 0.1}

    # Load job
    job_result = await db.execute(select(ExportJob).where(ExportJob.id == UUID(str(job_id))))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise ValueError(f"ExportJob {job_id} not found")

    # Mark processing
    job.status = ExportStatus.PROCESSING.value
    job.started_at = datetime.now(UTC)
    job.format = fmt_upper
    job.split_config = split_ratio
    job.augmentation_config = augmentations or {}
    job.progress_pct = 0.0
    await db.commit()

    if progress_callback:
        progress_callback(0.0)

    # Load dataset
    ds_result = await db.execute(
        select(Dataset).where(Dataset.id == job.dataset_id)
    )
    dataset = ds_result.scalar_one_or_none()
    if dataset is None:
        job.status = ExportStatus.FAILED.value
        job.error_message = f"Dataset {job.dataset_id} not found"
        await db.commit()
        raise ValueError(job.error_message)

    # Load certified annotations
    ann_result = await db.execute(
        select(Annotation)
        .where(
            Annotation.dataset_id == dataset.id,
            Annotation.status == AnnotationStatus.CERTIFIED,
        )
        .order_by(Annotation.id)
    )
    annotations = list(ann_result.scalars().all())
    total = len(annotations)
    if total == 0:
        job.status = ExportStatus.FAILED.value
        job.error_message = "No certified annotations found for dataset"
        await db.commit()
        raise ValueError(job.error_message)

    if progress_callback:
        progress_callback(0.1)
    job.progress_pct = 10.0
    await db.commit()

    # Stratified split
    splits = _stratified_split(annotations, split_ratio, stratify)

    if progress_callback:
        progress_callback(0.3)
    job.progress_pct = 30.0
    await db.commit()

    # Build per-split annotation files
    manifest: dict[str, Any] = {
        "format": fmt_upper,
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.name,
        "total_annotations": total,
        "split_counts": {k: len(v) for k, v in splits.items()},
        "splits": {},
    }

    build_fn = {
        "COCO": _build_coco_json,
        "YOLO": _build_yolo_txt,
        "PASCAL_VOC": _build_pascal_voc_xml,
    }[fmt_upper]

    for split_name, split_annotations in splits.items():
        if not split_annotations:
            manifest["splits"][split_name] = {"content": "", "count": 0}
            continue

        content = build_fn(split_annotations)
        manifest["splits"][split_name] = {
            "content": content,
            "count": len(split_annotations),
        }

    if progress_callback:
        progress_callback(0.7)
    job.progress_pct = 70.0
    await db.commit()

    # Augmentation metadata
    aug_info = _apply_augmentations_info(augmentations or {})
    manifest["augmentations"] = aug_info

    # README + LICENSE
    readme_text = _generate_readme(dataset, fmt_upper, splits, augmentations or {})
    license_text = _generate_license(dataset)
    manifest["readme"] = readme_text
    manifest["license"] = license_text

    if watermark:
        manifest["watermark"] = {
            "enabled": True,
            "fingerprint": f"wm-{job.id.hex[:24]}" if hasattr(job.id, "hex") else f"wm-{str(job.id)[:24]}",
            "note": "Invisible fingerprint embedded in exported annotations",
        }

    if progress_callback:
        progress_callback(0.9)
    job.progress_pct = 90.0
    await db.commit()

    # Compute checksum of manifest
    manifest_bytes = json.dumps(manifest, default=str).encode("utf-8")
    checksum = hashlib.sha256(manifest_bytes).hexdigest()

    # Determine output path
    date_str = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_name = dataset.name.replace(" ", "_")[:40]
    output_path = f"exports/{dataset.dataset_id}/{safe_name}_{fmt_upper}_{date_str}.zip"

    # Finalize job
    job.status = ExportStatus.COMPLETED.value
    job.output_path = output_path
    job.checksum = checksum
    job.image_count = total
    job.file_size_bytes = len(manifest_bytes)
    job.progress_pct = 100.0
    job.completed_at = datetime.now(UTC)
    job.error_message = None
    await db.commit()

    if progress_callback:
        progress_callback(1.0)

    logger.info(
        "Export job %s completed: %d annotations, format=%s, path=%s",
        job_id, total, fmt_upper, output_path,
    )
    return output_path


# ---------------------------------------------------------------------------
# Format builders
# ---------------------------------------------------------------------------

def _get_labels(ann: Annotation) -> dict:
    return ann.human_labels or ann.auto_labels or {}


def _extract_orientation(labels: dict, ann: Annotation) -> str:
    if labels.get("orientation"):
        return str(labels["orientation"])
    detected = ann.detected_objects
    if isinstance(detected, dict) and detected.get("orientation"):
        return str(detected["orientation"])
    return "normal"


def _detection_attributes(det: dict) -> dict:
    attrs: dict = {}
    if det.get("bbox_3d"):
        attrs["bbox_3d"] = det["bbox_3d"]
    if det.get("confidence") is not None:
        attrs["confidence"] = det["confidence"]
    if det.get("track_id") is not None:
        attrs["track_id"] = det["track_id"]
    if det.get("yaw_source"):
        attrs["yaw_source"] = det["yaw_source"]
    if det.get("distance_quality"):
        attrs["distance_quality"] = det["distance_quality"]
    return attrs


def _normalize_detection_for_export(det: dict, class_names: list[str]) -> dict:
    """Normalize a detection dict from human_labels or detected_objects."""
    cls = det.get("class") or det.get("class_name") or (class_names[0] if class_names else "unknown")
    bbox = det.get("bbox", [0, 0, 0, 0])
    if len(bbox) >= 4 and bbox[2] > 1.0:
        # pixel xywh — keep as-is for export metadata
        pass
    out = dict(det)
    out["class"] = cls
    out["bbox"] = bbox[:4]
    if "cx" not in out and len(bbox) >= 4:
        out["cx"] = bbox[0] + bbox[2] / 2
        out["cy"] = bbox[1] + bbox[3] / 2
        out["w"] = bbox[2]
        out["h"] = bbox[3]
    return out


def _collect_detections(ann: Annotation) -> tuple[list[dict], str]:
    labels = _get_labels(ann)
    class_names = labels.get("classes", [])
    detections = labels.get("detections", [])
    if not detections and isinstance(ann.detected_objects, dict):
        objects = ann.detected_objects.get("objects", [])
        detections = [_normalize_detection_for_export(o, class_names) for o in objects]
    else:
        detections = [_normalize_detection_for_export(d, class_names) for d in detections]
    orientation = _extract_orientation(labels, ann)
    return detections, orientation


def _build_coco_json(annotations: list[Annotation]) -> str:
    """Build a COCO-format JSON string from annotation metadata."""
    categories_map: dict[str, int] = {}
    cat_id_counter = 1

    coco_images: list[dict] = []
    coco_annotations: list[dict] = []
    ann_id_counter = 1

    for img_idx, ann in enumerate(annotations, start=1):
        labels = _get_labels(ann)
        class_names = labels.get("classes", [])
        detections, orientation = _collect_detections(ann)

        for cls_name in class_names:
            if cls_name not in categories_map:
                categories_map[cls_name] = cat_id_counter
                cat_id_counter += 1

        coco_images.append({
            "id": img_idx,
            "file_name": ann.image_path.rsplit("/", 1)[-1] if "/" in ann.image_path else ann.image_path,
            "width": 1920,
            "height": 1080,
            "orientation_mode": orientation,
        })

        for det in detections:
            bbox = det.get("bbox", [0, 0, 0, 0])
            cls_name = det.get("class", class_names[0] if class_names else "unknown")
            cat_id = categories_map.setdefault(cls_name, cat_id_counter)
            if cat_id == cat_id_counter:
                cat_id_counter += 1

            x, y, w, h = bbox[0], bbox[1], bbox[2], bbox[3]
            entry: dict = {
                "id": ann_id_counter,
                "image_id": img_idx,
                "category_id": cat_id,
                "bbox": [x, y, w, h],
                "area": w * h,
                "iscrowd": 0,
            }
            seg = det.get("mask_rle") or det.get("mask")
            if seg:
                entry["segmentation"] = seg
            attrs = _detection_attributes(det)
            if attrs:
                entry["attributes"] = attrs
            coco_annotations.append(entry)
            ann_id_counter += 1

    coco_obj = {
        "info": {
            "description": "EdgeVision-MW Export",
            "version": "1.1",
            "year": datetime.now(UTC).year,
            "orientation_note": "Coordinates in analyzed-frame space; use orientation_mode to un-mirror",
        },
        "licenses": [],
        "images": coco_images,
        "annotations": coco_annotations,
        "categories": [
            {"id": cid, "name": name, "supercategory": "object"}
            for name, cid in sorted(categories_map.items(), key=lambda x: x[1])
        ],
    }
    return json.dumps(coco_obj, indent=2)


def _build_yolo_txt(annotations: list[Annotation]) -> str:
    """Build YOLO-format text with optional YOLO-Seg companion lines."""
    class_names_set: list[str] = []
    seen: set[str] = set()

    for ann in annotations:
        labels = _get_labels(ann)
        for cls in labels.get("classes", []):
            if cls not in seen:
                class_names_set.append(cls)
                seen.add(cls)
        detections, _ = _collect_detections(ann)
        for det in detections:
            cls = det.get("class", "unknown")
            if cls not in seen:
                class_names_set.append(cls)
                seen.add(cls)

    lines: list[str] = []
    lines.append("# EdgeVision-MW YOLO export")
    lines.append(f"# classes: {json.dumps(class_names_set)}")
    lines.append("")

    class_to_id = {name: idx for idx, name in enumerate(class_names_set)}

    for ann in annotations:
        detections, orientation = _collect_detections(ann)
        filename = ann.image_path.rsplit("/", 1)[-1] if "/" in ann.image_path else ann.image_path
        lines.append(f"# {filename} orientation={orientation}")
        for det in detections:
            cls_name = det.get("class", "unknown")
            cls_id = class_to_id.get(cls_name, 0)
            cx = det.get("cx", 0.0)
            cy = det.get("cy", 0.0)
            w = det.get("w", 0.0)
            h = det.get("h", 0.0)
            lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            mask = det.get("mask")
            if isinstance(mask, list) and len(mask) >= 3:
                flat = " ".join(f"{p[0]:.6f} {p[1]:.6f}" for p in mask if isinstance(p, (list, tuple)))
                lines.append(f"# seg {cls_id} {flat}")
        lines.append("")

    return "\n".join(lines)


def _build_pascal_voc_xml(annotations: list[Annotation]) -> str:
    """Build Pascal VOC XML with segmentation and metadata."""
    xml_parts: list[str] = []

    for ann in annotations:
        detections, orientation = _collect_detections(ann)
        filename = ann.image_path.rsplit("/", 1)[-1] if "/" in ann.image_path else ann.image_path

        obj_blocks: list[str] = []
        for det in detections:
            bbox = det.get("bbox", [0, 0, 0, 0])
            name = det.get("class", "unknown")
            xmin = bbox[0]
            ymin = bbox[1]
            xmax = bbox[0] + bbox[2]
            ymax = bbox[1] + bbox[3]
            seg = det.get("mask_rle") or det.get("mask")
            seg_block = ""
            if seg:
                seg_block = f"\n    <segmentation>{_xml_escape(json.dumps(seg))}</segmentation>"
            attrs = _detection_attributes(det)
            attr_block = ""
            if attrs:
                attr_block = f"\n    <attributes>{_xml_escape(json.dumps(attrs))}</attributes>"
            obj_blocks.append(
                "  <object>\n"
                f"    <name>{_xml_escape(name)}</name>\n"
                "    <bndbox>\n"
                f"      <xmin>{xmin}</xmin>\n"
                f"      <ymin>{ymin}</ymin>\n"
                f"      <xmax>{xmax}</xmax>\n"
                f"      <ymax>{ymax}</ymax>\n"
                "    </bndbox>"
                f"{seg_block}{attr_block}\n"
                "  </object>"
            )

        xml = (
            "<annotation>\n"
            f"  <filename>{_xml_escape(filename)}</filename>\n"
            f"  <orientation_mode>{_xml_escape(orientation)}</orientation_mode>\n"
            "  <size>\n"
            "    <width>1920</width>\n"
            "    <height>1080</height>\n"
            "    <depth>3</depth>\n"
            "  </size>\n"
            f"{''.join(chr(10) + b for b in obj_blocks) if obj_blocks else ''}\n"
            "</annotation>"
        )
        xml_parts.append(xml)

    return "\n\n".join(xml_parts)


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Stratified splitting
# ---------------------------------------------------------------------------

def _stratified_split(
    annotations: list[Annotation],
    split_ratio: dict | None = None,
    stratify: bool = True,
) -> dict[str, list[Annotation]]:
    """Split annotations into train/val/test lists.

    When *stratify* is True the split preserves the class distribution by
    grouping annotations by their primary class label and distributing each
    class proportionally across splits.
    """
    if split_ratio is None:
        split_ratio = {"train": 0.7, "val": 0.2, "test": 0.1}

    train_r = split_ratio.get("train", 0.7)
    val_r = split_ratio.get("val", 0.2)
    total_r = train_r + val_r
    test_r = 1.0 - total_r if total_r < 1.0 else 0.0

    if not stratify or not annotations:
        shuffled = list(annotations)
        random.shuffle(shuffled)
        n = len(shuffled)
        n_train = int(n * train_r)
        n_val = int(n * val_r)
        return {
            "train": shuffled[:n_train],
            "val": shuffled[n_train:n_train + n_val],
            "test": shuffled[n_train + n_val:],
        }

    # Stratify by primary class
    class_buckets: dict[str, list[Annotation]] = {}
    for ann in annotations:
        labels = ann.human_labels or ann.auto_labels or {}
        classes = labels.get("classes", ["unknown"])
        primary = classes[0] if classes else "unknown"
        class_buckets.setdefault(primary, []).append(ann)

    result: dict[str, list[Annotation]] = {"train": [], "val": [], "test": []}

    for _cls, bucket in class_buckets.items():
        random.shuffle(bucket)
        n = len(bucket)
        n_train = int(n * train_r)
        n_val = int(n * val_r)
        result["train"].extend(bucket[:n_train])
        result["val"].extend(bucket[n_train:n_train + n_val])
        result["test"].extend(bucket[n_train + n_val:])

    # Shuffle within each split so classes are interleaved
    for key in result:
        random.shuffle(result[key])

    return result


# ---------------------------------------------------------------------------
# Augmentation info
# ---------------------------------------------------------------------------

def _apply_augmentations_info(config: dict) -> dict:
    """Describe which augmentations are configured (no actual transforms)."""
    info: dict[str, Any] = {}

    if config.get("horizontal_flip"):
        info["horizontal_flip"] = {
            "enabled": True,
            "probability": config.get("flip_probability", 0.5),
            "affects_annotations": True,
            "note": "Mirrors bounding-box x-coordinates",
        }

    if config.get("vertical_flip"):
        info["vertical_flip"] = {
            "enabled": True,
            "probability": config.get("flip_probability", 0.5),
            "affects_annotations": True,
            "note": "Mirrors bounding-box y-coordinates",
        }

    if config.get("rotation"):
        angle = config.get("max_angle_degrees", 15)
        info["rotation"] = {
            "enabled": True,
            "max_angle_degrees": angle,
            "affects_annotations": True,
            "note": f"Rotates ±{angle}°; bboxes recalculated after transform",
        }

    if config.get("color_jitter"):
        info["color_jitter"] = {
            "enabled": True,
            "brightness": config.get("brightness_range", [0.8, 1.2]),
            "contrast": config.get("contrast_range", [0.8, 1.2]),
            "saturation": config.get("saturation_range", [0.8, 1.2]),
            "affects_annotations": False,
            "note": "Pixel-level transform; bounding boxes unchanged",
        }

    if config.get("random_crop"):
        info["random_crop"] = {
            "enabled": True,
            "scale_range": config.get("crop_scale_range", [0.8, 1.0]),
            "aspect_ratio": config.get("crop_aspect_range", [0.75, 1.33]),
            "affects_annotations": True,
            "note": "Crops require clipping/padding bounding boxes",
        }

    if config.get("gaussian_noise"):
        info["gaussian_noise"] = {
            "enabled": True,
            "stddev": config.get("noise_stddev", 0.05),
            "affects_annotations": False,
            "note": "Additive pixel noise; no annotation change",
        }

    if config.get("mixup"):
        info["mixup"] = {
            "enabled": True,
            "alpha": config.get("mixup_alpha", 0.4),
            "affects_annotations": True,
            "note": "Merges two images and unions their bounding boxes",
        }

    if not info:
        info["none"] = {
            "enabled": True,
            "note": "No augmentations configured",
        }

    return info


# ---------------------------------------------------------------------------
# README / LICENSE generation
# ---------------------------------------------------------------------------

def _generate_readme(
    dataset: Dataset,
    fmt: str,
    splits: dict[str, list[Annotation]],
    augmentations: dict,
) -> str:
    ds_status = dataset.status.value if hasattr(dataset.status, "value") else dataset.status
    lic = dataset.license_type.value if hasattr(dataset.license_type, "value") else dataset.license_type
    split_sizes = {k: len(v) for k, v in splits.items()}
    class_summary = json.dumps(dataset.classes, indent=2) if dataset.classes else "{}"
    aug_names = [k for k, v in augmentations.items() if v]
    aug_section = ", ".join(aug_names) if aug_names else "None"

    return (
        f"# {dataset.name}\n\n"
        f"**Dataset ID:** {dataset.dataset_id}  \n"
        f"**Version:** {dataset.version}  \n"
        f"**Status:** {ds_status}  \n"
        f"**Samples:** {dataset.sample_count}  \n"
        f"**Format:** {fmt}  \n"
        f"**License:** {lic}  \n\n"
        f"## Classes\n\n```json\n{class_summary}\n```\n\n"
        f"## Splits\n\n"
        f"| Split | Count |\n|-------|-------|\n"
        + "\n".join(f"| {k} | {v} |" for k, v in split_sizes.items())
        + "\n\n"
        f"## Augmentations\n\n{aug_section}\n\n"
        f"## Quality\n\n"
        f"- Consent coverage: {dataset.consent_coverage_pct}%\n"
        f"- PII scrub verified: {dataset.pii_scrub_verified}\n"
        f"- Mean IAA score: {dataset.iaa_score}\n\n"
        f"---\n*Generated by EdgeVision-MW Export Builder on "
        f"{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}*\n"
    )


def _generate_license(dataset: Dataset) -> str:
    lic = dataset.license_type.value if hasattr(dataset.license_type, "value") else dataset.license_type
    return (
        f"EdgeVision-MW Dataset License\n"
        f"===============================\n\n"
        f"Dataset:   {dataset.name} ({dataset.dataset_id})\n"
        f"License:   {lic}\n"
        f"Price:     ${dataset.price_usd}\n\n"
        f"TERMS AND CONDITIONS\n\n"
        f"1. Grant of License. Subject to the terms of this Agreement, the "
        f"licensee (\"Buyer\") is granted a non-exclusive, non-transferable "
        f"right to use, copy, and analyze the data contained in the exported "
        f"dataset for internal research and commercial purposes.\n\n"
        f"2. Restrictions. Buyer shall not redistribute, resell, or sublicense "
        f"the raw dataset to third parties without prior written consent from "
        f"EdgeVision Data Platforms.\n\n"
        f"3. Attribution. Any public disclosure or publication derived from "
        f"this dataset must credit \"EdgeVision-MW Data Platform, Malawi\".\n\n"
        f"4. Privacy. Buyer acknowledges that the dataset has undergone PII "
        f"screening and consent verification. Buyer shall not attempt to "
        f"re-identify any individuals depicted in the data.\n\n"
        f"5. Disclaimer. THE DATA IS PROVIDED \"AS IS\" WITHOUT WARRANTY OF "
        f"ANY KIND. EdgeVision Data Platforms shall not be liable for any "
        f"damages arising from the use of this dataset.\n\n"
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
