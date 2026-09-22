"""Pre-labeling API endpoint.

Provides server-side YOLO-based auto-labeling for uploaded images.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from celery.result import AsyncResult
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
from app.services.batch_inference import resolve_batch_annotation_ids
from app.services.prelabel import prelabel_image
from app.workers.celery_app import celery_app

prelabel_router = APIRouter(prefix="/studio/prelabel", tags=["prelabel"])


class PrelabelRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    confidence_threshold: float = Field(default=0.45, ge=0.1, le=0.95)


class PrelabelBatchRequest(BaseModel):
    dataset_id: str = Field(..., description="Dataset slug or UUID")
    image_ids: list[UUID] | None = Field(
        default=None,
        max_length=1000,
        description="Optional subset of annotation IDs",
    )
    scope: Literal["remaining", "all"] = Field(default="remaining")
    force: bool = Field(default=False)
    confidence_threshold: float = Field(default=0.45, ge=0.1, le=0.95)


class BatchJobResponse(BaseModel):
    job_id: UUID
    total_images: int
    skipped: int = 0


class BatchJobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    progress: dict | None = None
    result: dict | None = None
    error: str | None = None


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

    max_idx = (
        await db.execute(select(func.max(Annotation.image_index)).where(Annotation.dataset_id == ds.id))
    ).scalar()
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


@prelabel_router.post("/batch", response_model=BatchJobResponse)
async def prelabel_batch(
    request: PrelabelBatchRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Run YOLO pre-labeling on all remaining unannotated frames in a dataset."""
    from app.workers.tasks import auto_label_annotations_task

    annotation_ids, skipped = await resolve_batch_annotation_ids(
        db,
        request.dataset_id,
        image_ids=request.image_ids,
        scope=request.scope,
        mode="detection",
        force=request.force,
    )

    if not annotation_ids:
        raise HTTPException(
            status_code=400,
            detail="No unannotated images to process. All frames already have labels.",
        )

    job_id = uuid4()
    auto_label_annotations_task.apply_async(
        args=[[str(i) for i in annotation_ids]],
        kwargs={
            "force": request.force,
            "confidence_threshold": request.confidence_threshold,
        },
        task_id=str(job_id),
    )

    return BatchJobResponse(
        job_id=job_id,
        total_images=len(annotation_ids),
        skipped=skipped,
    )


@prelabel_router.get("/jobs/{job_id}", response_model=BatchJobStatusResponse)
async def get_batch_job_status(
    job_id: UUID,
    user: dict = Depends(get_current_user),
):
    """Poll Celery batch job status (prelabel or road segmentation)."""
    result = AsyncResult(str(job_id), app=celery_app)
    meta = result.info if isinstance(result.info, dict) else None

    if result.state == "PENDING":
        return BatchJobStatusResponse(job_id=job_id, status="PENDING")
    if result.state == "PROGRESS":
        return BatchJobStatusResponse(
            job_id=job_id,
            status="RUNNING",
            progress=meta,
        )
    if result.state == "FAILURE":
        err = str(result.info) if result.info else "Job failed"
        return BatchJobStatusResponse(job_id=job_id, status="FAILED", error=err)
    if result.state == "SUCCESS":
        payload = result.result if isinstance(result.result, dict) else {"result": result.result}
        return BatchJobStatusResponse(job_id=job_id, status="COMPLETED", result=payload)
    return BatchJobStatusResponse(job_id=job_id, status=result.state, progress=meta)
