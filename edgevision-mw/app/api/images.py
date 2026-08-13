from __future__ import annotations

import hashlib
import json
import traceback
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.logging import get_logger
from app.core.minio_helper import (
    get_object_bytes,
    get_presigned_get_url,
)
from app.core.tenant import get_current_tenant_id
from app.models.dataset import Dataset
from app.models.enums import DatasetStatus, LicenseType
from app.models.image import ImageRecord
from app.schemas.upload import BatchUploadResponse, ImageUploadResponse
from app.services.image_processing import (
    ImageValidationError,
    validate_image,
)
from app.services.images import process_upload
from app.services.video_processing import (
    VideoProcessingError,
    extract_video_frames,
    is_video_upload,
)

logger = get_logger("edgevision.api.images")

images_router = APIRouter(prefix="/upload", tags=["Image Upload"])

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/tiff",
    "image/bmp",
}
ALLOWED_VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-matroska",
    "video/webm",
    "video/hevc",
    "video/x-hevc",
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_VIDEO_SIZE = 250 * 1024 * 1024  # 250MB
MAX_FILES = 50


VALID_SOURCES = {"file", "webcam", "screen_capture", "url", "drone"}


@images_router.post("/images", response_model=BatchUploadResponse, status_code=201)
async def upload_images(
    files: list[UploadFile] = File(..., description="Images (jpg/png/webp, max 20MB each)"),
    dataset_id: str = Form(..., description="Dataset string ID or UUID to upload to"),
    source: str = Form("file", description="Image source: file, webcam, screen_capture, url, drone"),
    telemetry: str = Form(None, description="JSON-encoded telemetry/metadata"),
    user: dict = Depends(require_role(["ADMIN", "OPERATOR", "ANNOTATOR", "QA", "BUYER"])),
    db: AsyncSession = Depends(get_db),
):
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=422, detail=f"Invalid source '{source}'. Must be one of: {', '.join(sorted(VALID_SOURCES))}")
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_FILES} files per upload")

    user_id = UUID(user["sub"])
    tenant_id = get_current_tenant_id()
    telemetry_dict = json.loads(telemetry) if telemetry else None

    # Resolve or create dataset
    ds = await _resolve_or_create_dataset(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    uploaded = []
    skipped = 0
    errors = []

    for f in files:
        trace_id = str(uuid4())
        content = await f.read()
        original_filename = f.filename or "upload"

        logger.info("upload_read_file", trace_id=trace_id, byte_count=len(content), filename=f.filename, source=source)

        if is_video_upload(f.content_type, original_filename, content):
            max_size = MAX_VIDEO_SIZE
        else:
            max_size = MAX_FILE_SIZE

        if len(content) > max_size:
            errors.append({
                "filename": f.filename,
                "error": f"File too large (max {max_size // (1024 * 1024)}MB)",
            })
            continue

        if is_video_upload(f.content_type, original_filename, content):
            video_results, video_errors = await _process_video_upload(
                content=content,
                filename=original_filename,
                source=source,
                user_id=user_id,
                tenant_id=tenant_id,
                dataset_id=ds.id,
                db=db,
                telemetry=telemetry_dict,
                trace_id=trace_id,
            )
            uploaded.extend(video_results)
            errors.extend(video_errors)
            continue

        inferred_type = _infer_mime_type(content)
        if inferred_type and inferred_type not in ALLOWED_MIME_TYPES:
            errors.append({"filename": f.filename, "error": f"Unsupported type: {inferred_type}"})
            continue

        checksum = hashlib.sha256(content).hexdigest()

        # Deduplicate by checksum
        existing_stmt = select(ImageRecord).where(ImageRecord.checksum_sha256 == checksum).limit(1)
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            skipped += 1
            uploaded.append(ImageUploadResponse(
                filename=f.filename or "unknown",
                annotation_id=str(existing.id),
                status="skipped_duplicate",
                checksum=checksum,
                source=source,
            ))
            continue

        content_type = inferred_type or f.content_type or "application/octet-stream"

        try:
            meta = validate_image(content)
            if meta.format not in {"JPEG", "PNG", "WEBP", "TIFF", "BMP"}:
                errors.append({"filename": f.filename, "error": f"Unsupported format: {meta.format}"})
                continue

            record = await process_upload(
                file_bytes=content,
                filename=original_filename,
                content_type=content_type,
                source=source,
                user_id=user_id,
                tenant_id=tenant_id,
                dataset_id=ds.id,
                db=db,
                telemetry=telemetry_dict,
                trace_id=trace_id,
            )

            uploaded.append(ImageUploadResponse(
                filename=original_filename,
                annotation_id=str(record.id),
                status="uploaded",
                checksum=checksum,
                source=source,
            ))
        except ImageValidationError as exc:
            errors.append({"filename": f.filename, "error": str(exc)})
        except Exception as exc:
            logger.error("upload_file_error", trace_id=trace_id, filename=f.filename, error=str(exc), traceback=traceback.format_exc())
            errors.append({"filename": f.filename, "error": f"Upload failed: {exc}"})

    await db.commit()

    from app.services.dataset_sync import sync_dataset_by_identifier

    await sync_dataset_by_identifier(db, ds.dataset_id)
    await db.commit()

    from app.api.metrics import uploads_total

    uploads_total.labels(status="success").inc(
        len([x for x in uploaded if x.status == "uploaded"])
    )
    uploads_total.labels(status="skipped_duplicate").inc(skipped)
    uploads_total.labels(status="error").inc(len(errors))

    logger.info("upload_batch_done", uploaded=len([x for x in uploaded if x.status == "uploaded"]), skipped=skipped, errors=len(errors))

    return BatchUploadResponse(
        dataset_id=ds.dataset_id,
        dataset_name=ds.name,
        uploaded=len([x for x in uploaded if x.status == "uploaded"]),
        skipped=skipped,
        total=len(files),
        images=uploaded,
        errors=errors,
        source=source,
    )


@images_router.post("/url", response_model=BatchUploadResponse, status_code=201)
async def upload_image_from_url(
    dataset_id: str = Form(..., description="Dataset string ID or UUID to upload to"),
    url: str = Form(..., description="URL of the image to fetch"),
    source: str = Form("url", description="Image source label"),
    telemetry: str = Form(None, description="JSON-encoded telemetry"),
    user: dict = Depends(require_role(["ADMIN", "OPERATOR", "ANNOTATOR", "QA", "BUYER"])),
    db: AsyncSession = Depends(get_db),
):
    if source not in VALID_SOURCES:
        raise HTTPException(status_code=422, detail=f"Invalid source '{source}'. Must be one of: {', '.join(sorted(VALID_SOURCES))}")

    user_id = UUID(user["sub"])
    tenant_id = get_current_tenant_id()
    telemetry_dict = json.loads(telemetry) if telemetry else None

    ds = await _resolve_or_create_dataset(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    content, content_type = await _fetch_image_from_url(url)

    inferred_type = _infer_mime_type(content)
    if inferred_type and inferred_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported image type: {inferred_type}")

    checksum = hashlib.sha256(content).hexdigest()

    existing_stmt = select(ImageRecord).where(ImageRecord.checksum_sha256 == checksum).limit(1)
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        await db.commit()
        return BatchUploadResponse(
            dataset_id=ds.dataset_id,
            dataset_name=ds.name,
            uploaded=0,
            skipped=1,
            total=1,
            images=[ImageUploadResponse(
                filename=url.rsplit("/", 1)[-1] or "remote",
                annotation_id=str(existing.id),
                status="skipped_duplicate",
                checksum=checksum,
                source=source,
            )],
            source=source,
        )

    meta = validate_image(content)
    if meta.format not in {"JPEG", "PNG", "WEBP", "TIFF", "BMP"}:
        raise HTTPException(status_code=422, detail=f"Unsupported format: {meta.format}")

    original_filename = url.rsplit("/", 1)[-1] or "remote_image"
    final_content_type = inferred_type or content_type or "application/octet-stream"

    trace_id = str(uuid4())
    record = await process_upload(
        file_bytes=content,
        filename=original_filename,
        content_type=final_content_type,
        source=source,
        user_id=user_id,
        tenant_id=tenant_id,
        dataset_id=ds.id,
        db=db,
        telemetry=telemetry_dict,
        trace_id=trace_id,
    )

    await db.commit()

    from app.services.dataset_sync import sync_dataset_by_identifier

    await sync_dataset_by_identifier(db, ds.dataset_id)
    await db.commit()

    return BatchUploadResponse(
        dataset_id=ds.dataset_id,
        dataset_name=ds.name,
        uploaded=1,
        skipped=0,
        total=1,
        images=[ImageUploadResponse(
            filename=original_filename,
            annotation_id=str(record.id),
            status="uploaded",
            checksum=checksum,
            source=source,
        )],
        source=source,
    )


async def _resolve_or_create_dataset(db: AsyncSession, dataset_id: str) -> Dataset | None:
    """Resolve a dataset by UUID or string ID, creating one if needed."""
    try:
        ds_uuid = UUID(dataset_id)
        stmt = select(Dataset).where(Dataset.id == ds_uuid)
    except ValueError:
        stmt = select(Dataset).where(Dataset.dataset_id == dataset_id)
    ds = (await db.execute(stmt)).scalar_one_or_none()
    if ds is not None:
        return ds

    ds = Dataset(
        dataset_id=dataset_id,
        name=dataset_id,
        version="1.0",
        status=DatasetStatus.BUILDING,
        sample_count=0,
        classes={},
        annotations_per_image=0.0,
        image_width=0,
        image_height=0,
        geographic_coverage={},
        demographic_report={},
        consent_coverage_pct=0.0,
        pii_scrub_verified=False,
        iaa_score=0.0,
        formats=["coco"],
        price_usd=0,
        license_type=LicenseType.PERPETUAL,
    )
    db.add(ds)
    await db.flush()
    return ds


# ── Image Serving ────────────────────────────────────────────

serve_router = APIRouter(prefix="/images", tags=["Image Serving"])


@serve_router.get("/{image_id}")
async def get_image_metadata(
    image_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(ImageRecord, image_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Image not found")
    _check_tenant_access(record)

    return {
        "image_id": str(record.id),
        "storage_key": record.storage_key,
        "thumbnail_key": record.thumbnail_key,
        "filename": record.filename,
        "content_type": record.content_type,
        "size_bytes": record.size_bytes,
        "width": record.width,
        "height": record.height,
        "source": record.source,
        "dataset_id": str(record.dataset_id) if record.dataset_id else None,
        "uploaded_by": str(record.uploaded_by) if record.uploaded_by else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "metadata": record.metadata_,
    }


@serve_router.get("/{image_id}/download")
async def download_image(
    image_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(ImageRecord, image_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Image not found")
    _check_tenant_access(record)

    from app.core.config import settings

    try:
        presigned_url = await get_presigned_get_url(
            settings.MINIO_BUCKET, record.storage_key, expires=3600
        )
        return RedirectResponse(url=presigned_url, status_code=307)
    except Exception as exc:
        logger.error("presigned_url_error", image_id=str(image_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to generate download URL: {exc}")


@serve_router.get("/{image_id}/serve")
async def serve_image(
    image_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(ImageRecord, image_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Image not found")
    _check_tenant_access(record)

    from app.core.config import settings

    try:
        data = await get_object_bytes(settings.MINIO_BUCKET, record.storage_key)
        return StreamingResponse(
            iter([data]),
            media_type=record.content_type,
            headers={
                "Content-Disposition": f'inline; filename="{record.filename}"',
                "Content-Length": str(len(data)),
            },
        )
    except Exception as exc:
        logger.error("serve_image_error", image_id=str(image_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Image serve failed: {exc}")


@serve_router.get("/{image_id}/thumbnail")
async def serve_thumbnail(
    image_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(ImageRecord, image_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Image not found")
    _check_tenant_access(record)

    if record.thumbnail_key is None:
        raise HTTPException(status_code=404, detail="No thumbnail available")

    from app.core.config import settings

    try:
        data = await get_object_bytes(settings.MINIO_BUCKET, record.thumbnail_key)
        return StreamingResponse(
            iter([data]),
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f'inline; filename="thumb_{record.filename}"',
            },
        )
    except Exception as exc:
        logger.error("serve_thumbnail_error", image_id=str(image_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Thumbnail serve failed: {exc}")


# ── Helpers ──────────────────────────────────────────────────

async def _process_video_upload(
    *,
    content: bytes,
    filename: str,
    source: str,
    user_id: UUID,
    tenant_id: UUID | None,
    dataset_id: UUID,
    db: AsyncSession,
    telemetry: dict | None,
    trace_id: str,
) -> tuple[list[ImageUploadResponse], list[dict[str, str]]]:
    uploaded: list[ImageUploadResponse] = []
    errors: list[dict[str, str]] = []

    try:
        probe, frames = extract_video_frames(content, filename)
    except VideoProcessingError as exc:
        errors.append({"filename": filename, "error": str(exc)})
        return uploaded, errors

    base_telemetry = dict(telemetry or {})
    base_telemetry.update(
        {
            "source_video": filename,
            "video_duration_sec": round(probe.duration_sec, 2),
            "video_fps": round(probe.fps, 2),
            "video_codec": probe.codec,
            "video_has_depth_track": probe.has_depth_track,
            "video_device_make": probe.device_make,
            "video_device_model": probe.device_model,
            "video_processing_notes": probe.notes,
        }
    )

    for frame in frames:
        frame_name = f"{filename}#frame_{frame.index:04d}.jpg"
        frame_checksum = hashlib.sha256(frame.jpeg_bytes).hexdigest()

        # Dedup by derived frame identity within the dataset, not raw checksum.
        # Checksum-only dedup collapses distinct temporal samples when OpenCV returns
        # identical JPEG bytes (common with HEVC/MOV) or static scenes.
        existing_stmt = (
            select(ImageRecord)
            .where(
                ImageRecord.dataset_id == dataset_id,
                ImageRecord.filename == frame_name,
            )
            .limit(1)
        )
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            uploaded.append(ImageUploadResponse(
                filename=frame_name,
                annotation_id=str(existing.id),
                status="skipped_duplicate",
                checksum=frame_checksum,
                source=source,
            ))
            continue

        frame_telemetry = {
            **base_telemetry,
            "video_frame_index": frame.index,
            "video_timestamp_sec": round(frame.timestamp_sec, 2),
        }

        try:
            record = await process_upload(
                file_bytes=frame.jpeg_bytes,
                filename=frame_name,
                content_type="image/jpeg",
                source=source,
                user_id=user_id,
                tenant_id=tenant_id,
                dataset_id=dataset_id,
                db=db,
                telemetry=frame_telemetry,
                trace_id=trace_id,
            )
            uploaded.append(ImageUploadResponse(
                filename=frame_name,
                annotation_id=str(record.id),
                status="uploaded",
                checksum=frame_checksum,
                source=source,
            ))
        except Exception as exc:
            logger.error(
                "upload_video_frame_error",
                trace_id=trace_id,
                filename=frame_name,
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            errors.append({"filename": frame_name, "error": f"Frame upload failed: {exc}"})

    return uploaded, errors


ALLOWED_MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",
    b"II": "image/tiff",
    b"MM": "image/tiff",
    b"BM": "image/bmp",
}


def _infer_mime_type(data: bytes) -> str | None:
    for sig, mime in ALLOWED_MAGIC_BYTES.items():
        if data[:len(sig)] == sig:
            return mime
    return None


def _decode_base64_data_url(data_url: str) -> tuple[bytes, str]:
    if not data_url.startswith("data:image/"):
        raise HTTPException(status_code=422, detail="Invalid data URL: must start with data:image/")

    try:
        header, encoded = data_url.split(",", 1)
        content_type = header.split(";")[0].replace("data:", "")
        import base64

        decoded = base64.b64decode(encoded)
        return decoded, content_type
    except (ValueError, IndexError, Exception) as exc:
        raise HTTPException(
            status_code=422, detail=f"Invalid base64 data URL: {exc}"
        )


async def _fetch_image_from_url(url: str) -> tuple[bytes, str]:
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=30.0
        ) as client, client.stream("GET", url) as response:
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                raise HTTPException(
                    status_code=422,
                    detail=f"URL did not return an image (got {content_type})",
                )

            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"Remote image exceeds max size of {MAX_FILE_SIZE // (1024 * 1024)}MB",
                )

            chunks = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="Remote image exceeded 20MB during download",
                    )
                chunks.append(chunk)

            data = b"".join(chunks)
            return data, content_type
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=422, detail="URL fetch timed out after 30s")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=422, detail=f"Failed to fetch URL: {exc}")


def _check_tenant_access(record: ImageRecord) -> None:
    current_tenant = get_current_tenant_id()
    if record.tenant_id and current_tenant and record.tenant_id != current_tenant:
        raise HTTPException(status_code=404, detail="Image not found")
