from __future__ import annotations

import hashlib
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.enums import AnnotationStatus, DatasetStatus
from app.schemas.upload import BatchUploadResponse, ImageUploadResponse

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-matroska", "video/webm"}
ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_VIDEO_TYPES
MAX_FILE_SIZE_BY_TYPE = {
    **{mime: 20 * 1024 * 1024 for mime in ALLOWED_IMAGE_TYPES},
    **{mime: 250 * 1024 * 1024 for mime in ALLOWED_VIDEO_TYPES},
}

image_upload_router = APIRouter(prefix="/upload", tags=["Image Upload"])


@image_upload_router.post(
    "/images",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_images(
    files: list[UploadFile] = File(..., description="Images (jpg/png/webp, max 20MB each)"),
    dataset_id: str = Form(..., description="Dataset string ID or UUID to upload to"),
    user: dict = Depends(require_role(["ADMIN", "OPERATOR", "ANNOTATOR", "QA", "BUYER"])),
    db: AsyncSession = Depends(get_db),
):
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 files per upload")

    ds = await _resolve_or_create_dataset(db, dataset_id)

    idx_stmt = select(func.max(Annotation.image_index)).where(Annotation.dataset_id == ds.id)
    max_idx = (await db.execute(idx_stmt)).scalar() or -1

    uploaded = []
    skipped = 0
    errors = []
    next_index = max_idx + 1

    for f in files:
        if f.content_type not in ALLOWED_TYPES:
            errors.append({"filename": f.filename, "error": f"Unsupported type: {f.content_type}"})
            continue

        content = await f.read()
        max_size = MAX_FILE_SIZE_BY_TYPE.get(f.content_type, 20 * 1024 * 1024)
        if len(content) > max_size:
            errors.append({
                "filename": f.filename,
                "error": f"File too large (max {max_size // (1024 * 1024)}MB)",
            })
            continue

        checksum = hashlib.sha256(content).hexdigest()

        existing = await _find_duplicate(db, checksum)
        if existing:
            skipped += 1
            uploaded.append(ImageUploadResponse(
                filename=f.filename or "unknown",
                annotation_id=str(existing.id),
                status="skipped_duplicate",
                checksum=checksum,
            ))
            continue

        ext = _get_extension(f.filename or "image.jpg", f.content_type)
        image_name = f"{uuid4().hex}.{ext}"
        minio_path = f"datasets/{ds.dataset_id}/images/{image_name}"

        try:
            from io import BytesIO

            from app.core.config import settings
            from app.core.dependencies import get_minio_client

            mc = await get_minio_client()
            content_type = f.content_type or "application/octet-stream"
            mc.put_object(
                settings.MINIO_BUCKET,
                minio_path,
                data=BytesIO(content),
                length=len(content),
                content_type=content_type,
            )
        except Exception:
            import logging

            logging.exception(f"MinIO upload failed for {minio_path}")
            raise HTTPException(status_code=500, detail=f"Storage upload failed for {f.filename}")

        from app.models.enums import BatchStatus
        from app.models.ingestion import IngestionBatch

        existing_batch = (await db.execute(
            select(IngestionBatch).where(IngestionBatch.batch_id.startswith(f"UPLOAD-{ds.dataset_id}")).limit(1)
        )).scalar_one_or_none()

        if existing_batch is None:
            batch = IngestionBatch(
                batch_id=f"UPLOAD-{ds.dataset_id}-{uuid4().hex[:8]}",
                node_id=(await _get_or_create_upload_node(db)).id,
                hub_id="upload-hub",
                event_count=0,
                file_size_bytes=0,
                checksum_sha256=checksum,
                node_signature=b"\x00",
                compression_codec="none",
                status=BatchStatus.INGESTED,
                quality_scores={},
            )
            db.add(batch)
            await db.flush()
        else:
            batch = existing_batch

        annotation = Annotation(
            batch_id=batch.id,
            image_index=next_index,
            image_path=minio_path,
            thumbnail_path=minio_path,
            detected_objects={"objects": [], "_checksum": checksum},
            auto_labels={"labels": []},
            status=AnnotationStatus.PENDING,
            quality_score=0.0,
            dataset_id=ds.id,
        )
        db.add(annotation)
        await db.flush()
        next_index += 1

        uploaded.append(ImageUploadResponse(
            filename=f.filename or "unknown",
            annotation_id=str(annotation.id),
            status="uploaded",
            checksum=checksum,
        ))

    if ds.status == DatasetStatus.BUILDING and len(uploaded) > 0:
        ds.status = DatasetStatus.READY

    ds.sample_count = (ds.sample_count or 0) + len([u for u in uploaded if u.status == "uploaded"])
    await db.commit()

    return BatchUploadResponse(
        dataset_id=ds.dataset_id,
        dataset_name=ds.name,
        uploaded=len([u for u in uploaded if u.status == "uploaded"]),
        skipped=skipped,
        total=len(files),
        images=uploaded,
    )


async def _resolve_or_create_dataset(db: AsyncSession, identifier: str) -> Dataset:
    try:
        from uuid import UUID as UUIDType
        uid = UUIDType(identifier)
        ds = await db.get(Dataset, uid)
        if ds is not None:
            return ds
    except (ValueError, TypeError):
        pass

    stmt = select(Dataset).where(Dataset.dataset_id == identifier).limit(1)
    ds = (await db.execute(stmt)).scalar_one_or_none()
    if ds is not None:
        return ds

    ds = Dataset(
        dataset_id=identifier,
        name=f"Dataset {identifier}",
        version="1.0",
        status=DatasetStatus.BUILDING,
        sample_count=0,
        classes={},
        annotations_per_image=0.0,
        image_width=0,
        image_height=0,
        geographic_coverage={"districts": []},
        demographic_report={"age_groups": {}},
        consent_coverage_pct=0.0,
        pii_scrub_verified=False,
        iaa_score=0.0,
        formats=[],
        price_usd=0,
        license_type="ANNUAL",
    )
    db.add(ds)
    await db.flush()
    return ds


async def _find_duplicate(db: AsyncSession, checksum: str) -> Annotation | None:
    stmt = select(Annotation).where(
        Annotation.detected_objects["_checksum"].astext == checksum
    ).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


_upload_node_cache = None


async def _get_or_create_upload_node(db: AsyncSession):
    global _upload_node_cache
    from app.models.enums import NodeCategory, NodeStatus, PIIMode
    from app.models.node import Node

    if _upload_node_cache is not None:
        return _upload_node_cache

    stmt = select(Node).where(Node.node_id == "upload-node").limit(1)
    node = (await db.execute(stmt)).scalar_one_or_none()

    if node is None:
        node = Node(
            node_id="upload-node",
            district="Lilongwe",
            latitude=-13.9626,
            longitude=33.7741,
            category=NodeCategory.ROAD,
            hardware_profile={"type": "upload"},
            network_config={},
            capture_schedule="manual",
            interest_classes=[],
            pii_mode=PIIMode.MODERATE,
            firmware_version="1.0.0",
            public_key=b"\x00" * 32,
            status=NodeStatus.ONLINE,
            is_enabled=True,
        )
        db.add(node)
        await db.flush()
        _upload_node_cache = node
    else:
        _upload_node_cache = node

    return _upload_node_cache


def _get_extension(filename: str, content_type: str) -> str:
    ext_map = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "video/mp4": "mp4",
        "video/quicktime": "mov",
        "video/x-matroska": "mkv",
        "video/webm": "webm",
    }
    if "." in filename:
        return filename.rsplit(".", 1)[-1].lower()
    return ext_map.get(content_type, "bin")
