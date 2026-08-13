"""Pre-labeling API endpoint.

Provides server-side YOLO-based auto-labeling for uploaded images.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.studio import _get_or_create_studio_batch
from app.core.database import get_db
from app.core.dependencies import get_current_user, get_minio_client
from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.enums import AnnotationStatus
from app.models.image import ImageRecord
from app.services.prelabel import prelabel_image

prelabel_router = APIRouter(prefix="/studio/prelabel", tags=["prelabel"])


class PrelabelRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    confidence_threshold: float = Field(default=0.45, ge=0.1, le=0.95)


class PrelabelDetection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    label: str
    class_name: str
    confidence: float
    bbox: list[float]


class PrelabelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    detections: list[PrelabelDetection]
    count: int


@prelabel_router.post("/image", response_model=PrelabelResponse)
async def prelabel_single_image(
    file: UploadFile = File(...),
    confidence_threshold: float = 0.45,
    user: dict = Depends(get_current_user),
):
    """Run YOLO pre-labeling on a single uploaded image.

    Returns bounding box detections with taxonomy labels and confidence scores.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 20MB")

    detections = prelabel_image(contents, confidence_threshold=confidence_threshold)

    return PrelabelResponse(
        detections=[PrelabelDetection(**d) for d in detections],
        count=len(detections),
    )


@prelabel_router.post("/image/{image_id}/run", response_model=PrelabelResponse)
async def prelabel_existing_image(
    image_id: UUID,
    confidence_threshold: float = 0.45,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Run prelabeling on an uploaded image by ImageRecord id and persist an Annotation.

    This provides an on-demand image prelabel endpoint for studio workflows.
    """
    record = await db.get(ImageRecord, image_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Image not found")

    if record.dataset_id is None:
        raise HTTPException(status_code=400, detail="Image must be assigned to a dataset to create annotations")

    mc = await get_minio_client()
    from app.core.config import settings

    try:
        resp = mc.get_object(settings.MINIO_BUCKET, record.storage_key)
        data = resp.read()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch image from storage: {exc}")

    detections = prelabel_image(data, confidence_threshold=confidence_threshold)

    # Create or get a studio ingestion batch for this dataset and persist an Annotation
    ds = await db.get(Dataset, record.dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    batch = await _get_or_create_studio_batch(db, ds)

    # find next image_index for dataset
    from sqlalchemy import func, select

    max_idx = (await db.execute(select(func.max(Annotation.image_index)).where(Annotation.dataset_id == ds.id))).scalar()
    next_index = (max_idx if max_idx is not None else -1) + 1

    detected_objects = {"objects": detections, "_checksum": record.checksum_sha256 or ""}
    auto_labels = {"labels": detections}

    ann = Annotation(
        id=uuid4(),
        batch_id=batch.id,
        image_index=next_index,
        image_path=record.storage_key,
        thumbnail_path=record.thumbnail_key or record.storage_key,
        detected_objects=detected_objects,
        auto_labels=auto_labels,
        status=AnnotationStatus.PENDING,
        quality_score=0.0,
        dataset_id=ds.id,
    )
    db.add(ann)
    await db.commit()

    return PrelabelResponse(
        detections=[PrelabelDetection(**d) for d in detections],
        count=len(detections),
    )
