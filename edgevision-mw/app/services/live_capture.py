"""Persistence layer for live-captured frames and clips.

Extracted from the ``POST /annotations/live`` endpoint so the live
WebSocket event layer can auto-save pre/post event clips through the
same PII-redacting, MinIO-backed, studio-bridged path as manual saves.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
import sqlalchemy as sa
from uuid import UUID, uuid4

from PIL import Image

from app.ai.mask_utils import mask_to_rle, polygon_to_mask, pycocotools_available
from app.core.logging import get_logger

logger = get_logger("edgevision.live_capture")


def _attach_mask_rle(objects: list, width: int, height: int) -> None:
    """Encode polygon masks as COCO RLE when pycocotools is available."""
    if width <= 0 or height <= 0:
        return
    if not pycocotools_available():
        logger.warning("mask_rle_unavailable", reason="pycocotools_not_installed")
        return

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if obj.get("mask_rle"):
            continue
        polygon = obj.get("mask")
        if not isinstance(polygon, list) or len(polygon) < 3:
            continue
        if obj.get("mask_format") not in (None, "polygon"):
            continue
        mask = polygon_to_mask(polygon, width, height)
        if not mask.any():
            continue
        try:
            mask_rle = mask_to_rle(mask)
        except ImportError:
            logger.warning("mask_rle_unavailable", reason="pycocotools_not_installed")
            return
        obj["mask_rle"] = mask_rle
        obj["mask_format"] = "rle"


def _attach_masks_and_3d(
    ann_list: list,
    mask_list: list | None,
    bbox_3d_list: list | None,
) -> list:
    if mask_list:
        enriched = []
        for i, ann in enumerate(ann_list):
            item = dict(ann) if isinstance(ann, dict) else {"class_name": str(ann)}
            mask_data = mask_list[i] if i < len(mask_list) else None
            if mask_data:
                if isinstance(mask_data, dict) and mask_data.get("format") == "rle":
                    item["mask"] = mask_data
                    item["mask_format"] = "rle"
                elif isinstance(mask_data, list):
                    item["mask"] = mask_data
                    item["mask_format"] = "polygon"
            enriched.append(item)
        ann_list = enriched

    if bbox_3d_list:
        enriched = []
        for i, ann in enumerate(ann_list):
            item = dict(ann) if isinstance(ann, dict) else {"class_name": str(ann)}
            box3d = bbox_3d_list[i] if i < len(bbox_3d_list) else None
            if box3d:
                item["bbox_3d"] = box3d
            enriched.append(item)
        ann_list = enriched

    return ann_list


async def save_live_capture(
    db,
    *,
    content: bytes,
    ann_list: list,
    source: str,
    dataset_id: str | None,
    confidence_threshold: float,
    orientation: str,
    depth_available: bool,
    user_id: UUID,
    tenant_id: UUID | None,
    masks: list | None = None,
    bbox_3d: list | None = None,
    capture_reason: str = "manual",
    event_id: str | None = None,
) -> dict:
    """Store one live-captured frame (PII-redacted) and return a save result."""
    from app.models.annotation import Annotation
    from app.models.enums import AnnotationStatus, BatchStatus, NodeStatus
    from app.models.image import ImageRecord
    from app.models.ingestion import IngestionBatch
    from app.models.node import Node, NodeCategory, PIIMode

    # Apply face + plate privacy blur before persisting live captures.
    faces_blurred = 0
    plates_blurred = 0
    try:
        from app.ai.pii_redaction import redact_image_bytes

        redaction = redact_image_bytes(content)
        content = redaction.image_bytes
        faces_blurred = redaction.faces_blurred
        plates_blurred = redaction.plates_blurred
    except Exception as exc:
        logger.warning("pii_redaction_failed", error=str(exc))

    ann_list = _attach_masks_and_3d(ann_list, masks, bbox_3d)

    # Store frame in MinIO
    ts = datetime.now(UTC).isoformat().replace(":", "-")
    object_key = f"tenants/{tenant_id if tenant_id else 'system'}/live-captures/{ts}_{uuid4().hex}.jpg"

    from app.core.config import settings
    from app.core.minio_helper import put_object

    try:
        await put_object(settings.MINIO_BUCKET, object_key, content, "image/jpeg")
    except Exception as exc:
        logger.error("minio_upload_failed", error=str(exc))
        raise RuntimeError(f"Failed to store frame: {exc}") from exc

    try:
        img = Image.open(io.BytesIO(content))
        width, height = img.size
    except Exception:
        width, height = 0, 0

    # Resolve optional dataset — live frames must land in the studio catalog when requested.
    ds = None
    if dataset_id:
        from app.services.dataset_sync import resolve_dataset

        ds = await resolve_dataset(db, dataset_id)
        if ds is None:
            raise ValueError(f"Dataset {dataset_id} not found")

    frame_id = uuid4()
    checksum = __import__("hashlib").sha256(content).hexdigest()

    if ds is not None:
        db.add(
            ImageRecord(
                id=frame_id,
                storage_key=object_key,
                thumbnail_key=object_key,
                filename=f"live_{ts}.jpg",
                content_type="image/jpeg",
                size_bytes=len(content),
                width=width,
                height=height,
                source=source,
                metadata_={
                    "live_capture": True,
                    "annotation_count": len(ann_list),
                    "confidence_threshold": confidence_threshold,
                    "orientation": orientation,
                    "capture_reason": capture_reason,
                    "event_id": event_id,
                    "has_mask_rle": False,
                },
                dataset_id=ds.id,
                uploaded_by=user_id,
                tenant_id=tenant_id,
                checksum_sha256=checksum,
            )
        )
        await db.flush()

    if ds is not None:
        from app.api.studio import _get_or_create_studio_batch

        batch = await _get_or_create_studio_batch(db, ds)
        max_idx = (
            await db.execute(sa.select(sa.func.max(Annotation.image_index)).where(Annotation.dataset_id == ds.id))
        ).scalar()
        image_index = (max_idx if max_idx is not None else -1) + 1
    else:
        node_result = await db.execute(sa.select(Node).limit(1))
        live_node = node_result.scalar_one_or_none()
        if live_node is None:
            live_node = Node(
                node_id=f"LIVE-{uuid4().hex[:12]}",
                district="virtual",
                latitude=0.0,
                longitude=0.0,
                category=NodeCategory.ROAD,
                hardware_profile={"type": "live-capture"},
                network_config={},
                capture_schedule="on-demand",
                interest_classes=[],
                pii_mode=PIIMode.STRICT,
                firmware_version="0.0.0",
                public_key=b"\x00" * 32,
                status=NodeStatus.ONLINE,
                is_enabled=True,
            )
            db.add(live_node)
            await db.flush()

        batch = IngestionBatch(
            batch_id=f"LIVE-{uuid4().hex[:12]}",
            node_id=live_node.id,
            hub_id="live-capture",
            event_count=1,
            file_size_bytes=len(content),
            checksum_sha256=checksum,
            node_signature=b"\x00" * 64,
            compression_codec="raw",
            status=BatchStatus.INGESTED,
            quality_scores={},
        )
        db.add(batch)
        await db.flush()
        image_index = 0

    detected_payload: dict | list
    if isinstance(ann_list, list):
        _attach_mask_rle(ann_list, width, height)
        has_mask_rle = any(isinstance(o, dict) and o.get("mask_rle") for o in ann_list)
        detected_payload = {
            "objects": ann_list,
            "source": source,
            "orientation": orientation,
            "depth_available": depth_available,
            "live_capture": True,
            "capture_reason": capture_reason,
        }
    else:
        detected_payload = ann_list if ann_list else {"objects": [], "orientation": orientation}
        has_mask_rle = False

    record = Annotation(
        id=frame_id if ds is not None else uuid4(),
        batch_id=batch.id,
        image_index=image_index,
        image_path=object_key,
        thumbnail_path=object_key,
        detected_objects=detected_payload,
        auto_labels={"source": source, "ai_assisted": True, "model_type": "live_inference"},
        status=AnnotationStatus.PENDING,
        quality_score=0.0,
        annotator_id=user_id,
        dataset_id=ds.id if ds is not None else None,
    )

    if ds is not None and isinstance(ann_list, list) and ann_list and width > 0 and height > 0:
        from app.services.live_label_bridge import live_detections_to_studio_boxes

        studio_boxes = live_detections_to_studio_boxes(ann_list, width, height)
        if studio_boxes:
            tool = "polygon" if any(b.get("polygon") for b in studio_boxes) else "bbox"
            record.human_labels = {
                "boxes": studio_boxes,
                "tool": tool,
                "source": "live_ai_assisted",
                "ai_draft": True,
            }

    db.add(record)

    if ds is not None and has_mask_rle:
        img_row = await db.get(ImageRecord, frame_id)
        if img_row is not None:
            meta = dict(img_row.metadata_ or {})
            meta["has_mask_rle"] = True
            img_row.metadata_ = meta

    if ds is not None:
        from app.services.dataset_sync import refresh_dataset_sample_count

        await refresh_dataset_sample_count(db, ds)

    await db.commit()
    await db.refresh(record)

    from app.api.metrics import annotations_total

    annotations_total.labels(status="created", label="live").inc()

    logger.info(
        "live_annotation_saved",
        annotation_id=str(record.id),
        object_count=len(ann_list),
        source=source,
        has_mask_rle=has_mask_rle,
        capture_reason=capture_reason,
        event_id=event_id,
    )

    return {
        "id": str(record.id),
        "annotation_id": str(record.id),
        "image_index": image_index,
        "image_path": object_key,
        "annotations_count": len(ann_list) if isinstance(ann_list, list) else 0,
        "source": source,
        "dataset_id": ds.dataset_id if ds is not None else None,
        "width": width,
        "height": height,
        "orientation": orientation,
        "depth_available": depth_available,
        "has_mask_rle": has_mask_rle,
        "faces_blurred": faces_blurred > 0,
        "plates_blurred": plates_blurred > 0,
        "pii_redacted": (faces_blurred + plates_blurred) > 0,
        "ai_draft": bool(record.human_labels and record.human_labels.get("ai_draft")),
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
