#!/usr/bin/env python3
"""Seed MinIO with sample images and create matching annotation records.

Usage:
    cd edgevision-mw
    source .venv/bin/activate
    POSTGRES_HOST=localhost MINIO_ENDPOINT=localhost:9000 python scripts/seed_minio.py
"""
from __future__ import annotations

import asyncio
import io
import os
import struct
import sys
import zlib
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import minio as minio_lib
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATASET_ID_STR = "DS-LILONGWE-001"
NUM_IMAGES = 20
IMG_W, IMG_H = 640, 480
THUMB_W, THUMB_H = 160, 120

SCENES = [
    (120, 140, 100), (160, 120, 80),  (80, 160, 60),  (140, 130, 110),
    (100, 150, 180), (130, 130, 130), (60, 120, 50),  (70, 130, 170),
    (180, 180, 180), (150, 110, 90),  (90, 150, 70),  (170, 160, 140),
    (70, 140, 55),   (60, 120, 160),  (140, 120, 100), (50, 110, 180),
    (85, 155, 65),   (130, 130, 120), (55, 115, 170),  (160, 170, 190),
]


def _chunk(ct: bytes, data: bytes) -> bytes:
    c = ct + data
    return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)


def _make_png(w: int, h: int, r: int, g: int, b: int) -> bytes:
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    raw = b""
    for row in range(h):
        raw += b"\x00"
        for col in range(w):
            if (row + col) % 40 < 2 or (row - col) % 40 < 2:
                raw += bytes([min(r + 40, 255), min(g + 40, 255), min(b + 40, 255)])
            else:
                raw += bytes([r, g, b])
    idat = _chunk(b"IDAT", zlib.compress(raw))
    iend = _chunk(b"IEND", b"")
    return header + ihdr + idat + iend


async def seed():
    from app.core.config import settings
    from app.models.annotation import Annotation
    from app.models.dataset import Dataset
    from app.models.enums import AnnotationStatus

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

    # Create our own engine to avoid pool contention with running backend
    db_url = f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    engine = create_async_engine(db_url, pool_size=2, max_overflow=2)
    session_factory = async_sessionmaker(class_=AsyncSession, bind=engine, expire_on_commit=False)

    async with session_factory() as db:
        stmt = select(Dataset).where(Dataset.dataset_id == DATASET_ID_STR).limit(1)
        ds = (await db.execute(stmt)).scalar_one_or_none()
        if ds is None:
            print(f"ERROR: Dataset '{DATASET_ID_STR}' not found")
            await engine.dispose()
            sys.exit(1)
        dataset_pk = ds.id
        print(f"Dataset: {ds.dataset_id} (pk={dataset_pk})")

        # Check existing
        existing = (await db.execute(
            select(Annotation).where(Annotation.dataset_id == dataset_pk)
        )).scalars().all()
        print(f"Existing annotations: {len(existing)}")

        if len(existing) < NUM_IMAGES:
            needed = NUM_IMAGES - len(existing)
            start_idx = max((a.image_index for a in existing), default=-1) + 1
            print(f"Creating {needed} annotation records starting at index {start_idx}...")
            for i in range(needed):
                idx = start_idx + i
                db.add(Annotation(
                    id=uuid4(),
                    dataset_id=dataset_pk,
                    image_index=idx,
                    image_path=f"images/{idx:04d}.png",
                    thumbnail_path=f"thumbs/{idx:04d}.png",
                    detected_objects={},
                    auto_labels={},
                    status=AnnotationStatus.PENDING,
                    quality_score=0.0,
                ))
            await db.commit()

        # Fetch all
        annotations = (await db.execute(
            select(Annotation)
            .where(Annotation.dataset_id == dataset_pk)
            .order_by(Annotation.image_index)
        )).scalars().all()
        print(f"Total annotations: {len(annotations)}")

        # Upload to MinIO
        uploaded = 0
        for ann in annotations:
            r, g, b = SCENES[ann.image_index % len(SCENES)]
            r = (r + ann.image_index * 7) % 256
            g = (g + ann.image_index * 11) % 256
            b = (b + ann.image_index * 13) % 256

            png = _make_png(IMG_W, IMG_H, r, g, b)
            mc.put_object(bucket, ann.image_path, io.BytesIO(png), len(png), content_type="image/png")

            thumb = _make_png(THUMB_W, THUMB_H, r, g, b)
            mc.put_object(bucket, ann.thumbnail_path, io.BytesIO(thumb), len(thumb), content_type="image/png")

            uploaded += 1
            if uploaded % 5 == 0:
                print(f"  Uploaded {uploaded}/{len(annotations)}")

    # Verify
    first = annotations[0]
    resp = mc.get_object(bucket, first.image_path)
    data = resp.read()
    print(f"\nVerification: read {len(data)} bytes from {first.image_path}")
    print(f"  PNG header valid: {data[:4] == b'\\x89PNG'}")

    await engine.dispose()
    print(f"\nSeed complete! {uploaded} images in MinIO bucket '{bucket}'")


if __name__ == "__main__":
    asyncio.run(seed())
