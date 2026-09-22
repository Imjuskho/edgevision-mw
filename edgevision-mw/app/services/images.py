from __future__ import annotations

import hashlib
import time
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.minio_helper import put_object
from app.models.image import ImageRecord
from app.services.image_processing import (
    extract_exif,
    generate_thumbnail,
    normalize_image,
    validate_image,
)

logger = get_logger("edgevision.images")


async def process_upload(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    source: str,
    user_id: UUID,
    tenant_id: UUID | None,
    dataset_id: UUID | None,
    db: AsyncSession,
    telemetry: dict | None = None,
    bucket: str | None = None,
    trace_id: str | None = None,
) -> ImageRecord:
    from app.core.config import settings

    bucket = bucket or settings.MINIO_BUCKET
    start = time.monotonic()
    trace_id = trace_id or str(uuid4())

    logger.info("svc_validate_start", trace_id=trace_id, source=source, filename=filename)

    # 1. Validate
    meta = validate_image(file_bytes)
    final_content_type = f"image/{meta.format.lower()}"
    logger.info("svc_validate_done", trace_id=trace_id, width=meta.width, height=meta.height, fmt=meta.format)

    # 2. Normalize (WebP/TIFF/BMP → PNG)
    strip_exif = source != "drone"
    normalized_bytes, output_format = normalize_image(file_bytes, strip_exif=strip_exif)
    if output_format == "JPEG":
        final_content_type = "image/jpeg"
        ext = "jpg"
    else:
        final_content_type = "image/png"
        ext = "png"
    logger.info(
        "svc_normalize_done", trace_id=trace_id, output_format=output_format, normalized_size=len(normalized_bytes)
    )

    # 3. Extract EXIF
    exif_data = extract_exif(file_bytes) if source == "drone" else None
    if exif_data:
        logger.info("svc_exif_extracted", trace_id=trace_id, exif_keys=list(exif_data.keys()))

    # 4. Build metadata
    metadata: dict = {}
    if telemetry:
        metadata["telemetry"] = telemetry
    if source == "drone" and exif_data:
        metadata["exif"] = exif_data
        if "gps_lat" in exif_data:
            metadata["gps_lat"] = exif_data["gps_lat"]
        if "gps_lon" in exif_data:
            metadata["gps_lon"] = exif_data["gps_lon"]

    # 5. Generate storage key — no leading slash
    tenant_part = f"tenants/{tenant_id}" if tenant_id else "tenants/anonymous"
    ds_part = f"datasets/{dataset_id}" if dataset_id else "datasets/unassigned"
    image_id = uuid4()
    storage_key = f"{tenant_part}/{ds_part}/images/{image_id}.{ext}"
    thumbnail_key = f"{tenant_part}/{ds_part}/thumbnails/{image_id}.jpg"
    logger.info("svc_key_generated", trace_id=trace_id, image_id=str(image_id), storage_key=storage_key)

    # 6. Compute checksum
    checksum = hashlib.sha256(file_bytes).hexdigest()

    # 7. Upload original to MinIO
    logger.info("svc_minio_put_start", trace_id=trace_id, bucket=bucket, key=storage_key, size=len(normalized_bytes))
    await put_object(
        bucket,
        storage_key,
        data=normalized_bytes,
        content_type=final_content_type,
        metadata={"source": source, "original_filename": filename},
    )
    logger.info("svc_minio_put_done", trace_id=trace_id, key=storage_key)

    # 8. Generate and upload thumbnail
    thumb_bytes = generate_thumbnail(normalized_bytes)
    logger.info("svc_thumb_generated", trace_id=trace_id, thumb_size=len(thumb_bytes))
    await put_object(
        bucket,
        thumbnail_key,
        data=thumb_bytes,
        content_type="image/jpeg",
    )
    logger.info("svc_thumb_uploaded", trace_id=trace_id, key=thumbnail_key)

    # 9. Persist record
    record = ImageRecord(
        id=image_id,
        storage_key=storage_key,
        thumbnail_key=thumbnail_key,
        filename=filename,
        content_type=final_content_type,
        size_bytes=len(normalized_bytes),
        width=meta.width,
        height=meta.height,
        source=source,
        metadata_=metadata if metadata else None,
        exif=exif_data if exif_data else None,
        dataset_id=dataset_id,
        uploaded_by=user_id,
        tenant_id=tenant_id,
        checksum_sha256=checksum,
    )
    db.add(record)
    await db.flush()
    logger.info("svc_db_flushed", trace_id=trace_id, image_id=str(image_id))

    duration_ms = round((time.monotonic() - start) * 1000, 2)
    logger.info(
        "upload_success",
        trace_id=trace_id,
        image_id=str(image_id),
        storage_key=storage_key,
        source=source,
        size_bytes=len(normalized_bytes),
        width=meta.width,
        height=meta.height,
        duration_ms=duration_ms,
    )

    # Always create a studio Annotation when assigned to a dataset so annotate/list work.
    if dataset_id is not None:
        try:
            from sqlalchemy import func, select

            from app.api.studio import _get_or_create_studio_batch
            from app.models.annotation import Annotation
            from app.models.dataset import Dataset
            from app.models.enums import AnnotationStatus

            ds = await db.get(Dataset, dataset_id)
            if ds is not None:
                batch = await _get_or_create_studio_batch(db, ds)
                max_idx = (
                    await db.execute(select(func.max(Annotation.image_index)).where(Annotation.dataset_id == ds.id))
                ).scalar()
                next_index = (max_idx if max_idx is not None else -1) + 1

                ann = Annotation(
                    id=image_id,
                    batch_id=batch.id,
                    image_index=next_index,
                    image_path=record.storage_key,
                    thumbnail_path=record.thumbnail_key or record.storage_key,
                    detected_objects={"objects": [], "_checksum": record.checksum_sha256 or ""},
                    auto_labels={"labels": [], "source": source},
                    status=AnnotationStatus.PENDING,
                    quality_score=0.0,
                    dataset_id=ds.id,
                )
                db.add(ann)
                await db.flush()

                from app.core.config import settings as _settings

                if _settings.AUTO_PRELABEL_ON_UPLOAD:
                    from app.workers.tasks import auto_label_annotations_task

                    try:
                        auto_label_annotations_task.delay([str(ann.id)])
                    except Exception:
                        logger.exception("enqueue_auto_prelabel_failed", trace_id=trace_id, image_id=str(image_id))
        except Exception:
            logger.exception("annotation_create_failed", trace_id=trace_id, image_id=str(image_id))

    return record
