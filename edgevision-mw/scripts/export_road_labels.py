#!/usr/bin/env python3
"""
Export human-reviewed road_annotations from PostgreSQL to YOLO-seg training format.

Reads ``road_annotations`` rows with ``reviewed=True``, resolves source images
via the linked ``annotations`` row (MinIO fetch), and writes paired
``images/{split}/*.jpg`` + ``labels/{split}/*.txt`` under
``datasets/road_seg_corrected/``. Emits ``road_dataset_corrected.yaml``.

Retrain recipe (after export):
    python scripts/export_road_labels.py --dataset-id 23952171-1159-4eff-844d-8f30fb3c98db
    python scripts/render_road_overlays.py --dataset datasets/road_seg_corrected
    python scripts/train_road_seg.py --data road_dataset_corrected.yaml --model yolov8n-seg.pt --epochs 100
    python scripts/export_road_seg_onnx.py --weights runs/segment/train/weights/best.pt --output models/road_seg/
    # Set ROAD_SEG_MODEL_PATH=models/road_seg/best.onnx and ROAD_SEG_CONF_THRESHOLD=0.5, then rebuild app.

Usage:
    cd edgevision-mw
    POSTGRES_HOST=localhost MINIO_ENDPOINT=localhost:9000 python scripts/export_road_labels.py
    python scripts/export_road_labels.py --dataset-id 23952171-1159-4eff-844d-8f30fb3c98db --val-ratio 0.15
"""
from __future__ import annotations

import argparse
import asyncio
import io
import os
import random
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import minio as minio_lib
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.annotation import Annotation
from app.models.road_annotation import RoadAnnotation

CLASS_NAMES = [
    "good_road", "pothole", "crack", "dust_road",
    "gravel_road", "road_marking", "shoulder",
]
NAME_TO_ID = {name: idx for idx, name in enumerate(CLASS_NAMES)}

DEFAULT_DATASET_UUID = "23952171-1159-4eff-844d-8f30fb3c98db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export reviewed road annotations to YOLO-seg dataset")
    parser.add_argument(
        "--dataset-id",
        type=str,
        default=DEFAULT_DATASET_UUID,
        help="Dataset UUID (datasets.id) to filter annotations",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT / "datasets" / "road_seg_corrected"),
        help="Output dataset root",
    )
    parser.add_argument("--val-ratio", type=float, default=0.15, help="Validation split fraction")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for train/val split")
    parser.add_argument(
        "--yaml-out",
        type=str,
        default=str(ROOT / "road_dataset_corrected.yaml"),
        help="Path for generated dataset YAML",
    )
    return parser.parse_args()


def _minio_client() -> minio_lib.Minio:
    return minio_lib.Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def _instance_to_yolo_line(inst: dict) -> str | None:
    class_id = inst.get("class_id")
    if class_id is None:
        name = inst.get("class_name", "")
        class_id = NAME_TO_ID.get(name)
    if class_id is None:
        return None
    polygon = inst.get("polygon")
    if not polygon or len(polygon) < 3:
        return None
    coords = " ".join(f"{float(p[0]):.6f} {float(p[1]):.6f}" for p in polygon)
    return f"{int(class_id)} {coords}"


def _write_yaml(yaml_path: Path, dataset_root: Path) -> None:
    rel = dataset_root.relative_to(ROOT) if dataset_root.is_relative_to(ROOT) else dataset_root
    content = f"""# Corrected road segmentation dataset (human-reviewed labels)
path: {rel}
train: images/train
val: images/val
test: images/test

nc: {len(CLASS_NAMES)}

names:
"""
    for idx, name in enumerate(CLASS_NAMES):
        content += f"  {idx}: {name}\n"
    content += '\ndownload: ""\n'
    yaml_path.write_text(content)


async def export_labels(args: argparse.Namespace) -> dict[str, int]:
    if not settings.DATABASE_URL:
        settings.DATABASE_URL = (
            f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
            f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        )

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(class_=AsyncSession, bind=engine, expire_on_commit=False)
    dataset_uuid = UUID(args.dataset_id)
    output_root = Path(args.output)
    mc = _minio_client()
    rng = random.Random(args.seed)

    stats = {"reviewed": 0, "exported": 0, "skipped_no_polygon": 0, "skipped_fetch": 0}

    async with session_factory() as db:
        result = await db.execute(
            select(RoadAnnotation, Annotation)
            .join(Annotation, RoadAnnotation.annotation_id == Annotation.id)
            .where(
                RoadAnnotation.reviewed.is_(True),
                Annotation.dataset_id == dataset_uuid,
            )
        )
        pairs = result.all()

    stats["reviewed"] = len(pairs)
    if not pairs:
        print(f"No reviewed road annotations for dataset {args.dataset_id}")
        await engine.dispose()
        return stats

    indices = list(range(len(pairs)))
    rng.shuffle(indices)
    val_count = max(1, int(len(indices) * args.val_ratio))
    val_set = set(indices[:val_count])

    for idx, (ra, ann) in enumerate(pairs):
        split = "val" if idx in val_set else "train"
        instances = ra.instances if isinstance(ra.instances, list) else []
        lines = []
        for inst in instances:
            if isinstance(inst, dict):
                line = _instance_to_yolo_line(inst)
                if line:
                    lines.append(line)
        if not lines:
            stats["skipped_no_polygon"] += 1
            continue

        stem = Path(ann.image_path).stem or str(ann.id)
        img_out = output_root / "images" / split / f"{stem}.jpg"
        lbl_out = output_root / "labels" / split / f"{stem}.txt"
        img_out.parent.mkdir(parents=True, exist_ok=True)
        lbl_out.parent.mkdir(parents=True, exist_ok=True)

        try:
            resp = mc.get_object(settings.MINIO_BUCKET, ann.image_path)
            pil = Image.open(io.BytesIO(resp.read()))
            if pil.mode != "RGB":
                pil = pil.convert("RGB")
            pil.save(img_out, format="JPEG", quality=92)
        except Exception as exc:
            print(f"WARN: fetch failed for {ann.image_path}: {exc}")
            stats["skipped_fetch"] += 1
            continue

        lbl_out.write_text("\n".join(lines) + "\n")
        stats["exported"] += 1

    _write_yaml(Path(args.yaml_out), output_root)
    await engine.dispose()
    return stats


def main() -> None:
    args = parse_args()
    stats = asyncio.run(export_labels(args))
    print("\n=== Road label export complete ===")
    for key, val in stats.items():
        print(f"  {key}: {val}")
    print(f"  output: {args.output}")
    print(f"  yaml: {args.yaml_out}")
    print("\nRetrain:")
    print("  python scripts/train_road_seg.py --data road_dataset_corrected.yaml --model yolov8n-seg.pt --epochs 100")


if __name__ == "__main__":
    main()
