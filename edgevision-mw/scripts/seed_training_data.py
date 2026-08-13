#!/usr/bin/env python3
"""Seed training data: datasets, annotations with labels, synthetic images.

Creates 3 datasets (road, agri_crop, agri_health) each with 20 synthetic
images and CERTIFIED annotations containing bounding-box labels, then
uploads images to MinIO.  After seeding, a training job can be started via
POST /studio/training/start.

Usage:
    cd edgevision-mw
    source .venv/bin/activate
    POSTGRES_HOST=localhost MINIO_ENDPOINT=localhost:9000 python scripts/seed_training_data.py
"""
from __future__ import annotations

import asyncio
import io
import os
import random
import sys
from datetime import UTC, datetime
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import minio as minio_lib
import numpy as np
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

NUM_IMAGES = 20
IMG_W, IMG_H = 640, 480
THUMB_W, THUMB_H = 160, 120

DATASETS = [
    {
        "dataset_id": "DS-ROAD-DEMO-001",
        "name": "Road Surface Demo",
        "model_type": "road_segmentation",
        "classes": {
            0: "good_road", 1: "pothole", 2: "crack", 3: "dust_road",
            4: "gravel_road", 5: "road_marking", 6: "shoulder",
        },
    },
    {
        "dataset_id": "DS-AGRI-CROP-DEMO-001",
        "name": "Agri Crop Demo",
        "model_type": "agri_crop_classification",
        "classes": {
            0: "maize", 1: "rice", 2: "cassava", 3: "groundnuts",
            4: "cotton", 5: "tobacco", 6: "sugarcane", 7: "beans",
            8: "sweet_potato", 9: "vegetables",
        },
    },
    {
        "dataset_id": "DS-AGRI-HEALTH-DEMO-001",
        "name": "Agri Health Demo",
        "model_type": "agri_health_classification",
        "classes": {
            0: "healthy", 1: "stressed", 2: "diseased", 3: "pest_infested",
            4: "nutrient_deficient", 5: "bare_soil", 6: "weed_infestation",
            7: "water_logged", 8: "drought_stressed",
        },
    },
]

SCENES = [
    (120, 140, 100), (160, 120, 80), (80, 160, 60), (140, 130, 110),
    (100, 150, 180), (130, 130, 130), (60, 120, 50), (70, 130, 170),
    (180, 180, 180), (150, 110, 90), (90, 150, 70), (170, 160, 140),
    (70, 140, 55), (60, 120, 160), (140, 120, 100), (50, 110, 180),
    (85, 155, 65), (130, 130, 120), (55, 115, 170), (160, 170, 190),
]


def _make_image(w: int, h: int, r: int, g: int, b: int) -> bytes:
    arr = np.full((h, w, 3), [r, g, b], dtype=np.uint8)
    mask = (np.arange(h)[:, None] + np.arange(w)[None, :]) % 40 < 2
    mask |= (np.arange(h)[:, None] - np.arange(w)[None, :]) % 40 < 2
    arr[mask] = np.clip(arr[mask].astype(np.int16) + 40, 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def _synthetic_boxes(ds_classes: dict[int, str], seed_val: int = 42) -> list[dict]:
    rng = random.Random(seed_val)
    classes_list = list(ds_classes.values())
    boxes = []
    for _ in range(rng.randint(2, 5)):
        bw = rng.uniform(0.1, 0.5)
        bh = rng.uniform(0.1, 0.5)
        boxes.append({
            "x": round(rng.uniform(0.0, 1.0 - bw), 6),
            "y": round(rng.uniform(0.0, 1.0 - bh), 6),
            "width": round(bw, 6),
            "height": round(bh, 6),
            "label": rng.choice(classes_list),
        })
    return boxes


async def seed():
    from app.core.config import settings
    from app.models.annotation import Annotation, AnnotationStatus
    from app.models.dataset import Dataset, DatasetStatus, LicenseType
    from app.models.ingestion import IngestionBatch, BatchStatus

    endpoint = os.environ.get("MINIO_ENDPOINT", settings.MINIO_ENDPOINT)
    print(f"MinIO endpoint: {endpoint}")

    mc = minio_lib.Minio(
        endpoint,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )

    bucket = settings.MINIO_BUCKET
    if not mc.bucket_exists(bucket):
        mc.make_bucket(bucket)
        print(f"Created bucket: {bucket}")
    else:
        print(f"Bucket OK: {bucket}")

    db_url = (
        f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )
    engine = create_async_engine(db_url, pool_size=2, max_overflow=2)
    session_factory = async_sessionmaker(class_=AsyncSession, bind=engine, expire_on_commit=False)

    async with session_factory() as db:
        result = await db.execute(select(IngestionBatch).limit(1))
        dummy_batch = result.scalar_one_or_none()
        if dummy_batch is None:
            dummy_batch = IngestionBatch(
                batch_id=f"seed-batch-{uuid4().hex[:8]}",
                node_id=uuid4(),
                checksum_sha256="0" * 64,
                node_signature=b"",
                status=BatchStatus.INGESTED,
                quality_scores={},
            )
            db.add(dummy_batch)
            await db.commit()
            await db.refresh(dummy_batch)
            print(f"Created dummy ingestion batch: {dummy_batch.batch_id}")
        else:
            print(f"Using existing ingestion batch: {dummy_batch.batch_id}")

        now = datetime.now(UTC)

        for ds_cfg in DATASETS:
            ds_id_str = ds_cfg["dataset_id"]
            ds_classes = ds_cfg["classes"]
            prefix = ds_cfg["model_type"]
            print(f"\n=== {ds_id_str} ({ds_cfg['model_type']}) ===")

            result = await db.execute(
                select(Dataset).where(Dataset.dataset_id == ds_id_str).limit(1)
            )
            ds = result.scalar_one_or_none()
            if ds is None:
                ds = Dataset(
                    dataset_id=ds_id_str,
                    name=ds_cfg["name"],
                    version="v1",
                    status=DatasetStatus.READY,
                    sample_count=0,
                    classes={},
                    annotations_per_image=0.0,
                    image_width=IMG_W,
                    image_height=IMG_H,
                    geographic_coverage={"countries": ["MW"]},
                    demographic_report={},
                    consent_coverage_pct=100.0,
                    pii_scrub_verified=False,
                    iaa_score=0.0,
                    formats=["coco", "yolo"],
                    price_usd=0,
                    license_type=LicenseType.PERPETUAL,
                    metadata_={"source": "seed_training_data.py", "created": now.isoformat()},
                )
                db.add(ds)
                await db.commit()
                await db.refresh(ds)
                print(f"  Created dataset")
            else:
                print(f"  Dataset exists (pk={ds.id})")

            existing = await db.execute(
                select(Annotation).where(Annotation.dataset_id == ds.id)
            )
            existing_anns = existing.scalars().all()
            print(f"  Existing annotations: {len(existing_anns)}")

            if len(existing_anns) < NUM_IMAGES:
                needed = NUM_IMAGES - len(existing_anns)
                start_idx = max((a.image_index for a in existing_anns), default=-1) + 1
                print(f"  Creating {needed} annotations...")
                for i in range(needed):
                    idx = start_idx + i
                    rng_seed = hash(f"{ds_id_str}-{idx}") % (2**31)
                    boxes = _synthetic_boxes(ds_classes, rng_seed)
                    db.add(Annotation(
                        id=uuid4(),
                        batch_id=dummy_batch.id,
                        dataset_id=ds.id,
                        image_index=idx,
                        image_path=f"{prefix}/images/{idx:04d}.png",
                        thumbnail_path=f"{prefix}/thumbs/{idx:04d}.png",
                        detected_objects={},
                        auto_labels={"boxes": boxes},
                        status=AnnotationStatus.CERTIFIED,
                        quality_score=1.0,
                        iaa_score=1.0,
                        is_certified=True,
                    ))
                await db.commit()
                print(f"  Created {needed} annotations")
            else:
                print(f"  Already has enough annotations")

            annotations = (await db.execute(
                select(Annotation)
                .where(Annotation.dataset_id == ds.id)
                .order_by(Annotation.image_index)
            )).scalars().all()

            uploaded = 0
            for ann in annotations:
                r, g, b = SCENES[ann.image_index % len(SCENES)]
                r = (r + ann.image_index * 7) % 256
                g = (g + ann.image_index * 11) % 256
                b = (b + ann.image_index * 13) % 256

                png = _make_image(IMG_W, IMG_H, r, g, b)
                mc.put_object(bucket, ann.image_path, io.BytesIO(png), len(png), content_type="image/png")

                thumb = _make_image(THUMB_W, THUMB_H, r, g, b)
                mc.put_object(bucket, ann.thumbnail_path, io.BytesIO(thumb), len(thumb), content_type="image/png")

                uploaded += 1
                if uploaded % 5 == 0:
                    print(f"  Uploaded {uploaded}/{len(annotations)}")

            print(f"  Done: {uploaded} images")

    await engine.dispose()
    print("\nSeed complete!  Ready to start training jobs:")
    for ds_cfg in DATASETS:
        print(f"  \u2022 {ds_cfg['dataset_id']} \u2192 {ds_cfg['model_type']}")


if __name__ == "__main__":
    asyncio.run(seed())
