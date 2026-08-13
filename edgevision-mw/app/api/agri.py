from __future__ import annotations

import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, get_minio_client, require_role
from app.core.features import require_role_and_feature
from app.core.logging import get_logger
from app.models.agri_annotation import AgriAnnotation
from app.models.agri_taxonomy import AGRI_TAXONOMY_VERSION, CROP_CLASSES, HEALTH_CLASSES
from app.models.annotation import Annotation
from app.schemas.agri import (
    AgriAnalysisReport,
    AgriAnalyzeRequest,
    AgriAnnotationResponse,
    AgriAnnotationUpdate,
    AgriClassesResponse,
    AgriSegmentationBatchRequest,
    AgriSegmentationBatchResponse,
    AgriSegmentationRequest,
    AgriSegmentationResponse,
    InstanceMask,
)
from app.services.agri_analysis import analyze_dataset_agri_condition

logger = get_logger("edgevision.agri_api")

agri_router = APIRouter(prefix="/agri", tags=["Agriculture Analysis"])


def _instances_to_schema(instances: list) -> list[InstanceMask]:
    result = []
    for inst in instances:
        if hasattr(inst, "class_id"):
            result.append(InstanceMask(
                class_id=inst.class_id,
                class_name=inst.class_name,
                confidence=inst.confidence,
                bbox=inst.bbox,
                mask_rle=inst.mask_rle,
                polygon=inst.polygon,
            ))
        elif isinstance(inst, dict):
            result.append(InstanceMask(
                class_id=inst["class_id"],
                class_name=inst["class_name"],
                confidence=inst["confidence"],
                bbox=inst["bbox"],
                mask_rle=inst.get("mask_rle", ""),
                polygon=inst.get("polygon"),
            ))
    return result


@agri_router.post("/segment", response_model=AgriSegmentationResponse)
async def segment_image(
    request: AgriSegmentationRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from app.ai.agri_segmenter import dominant_class_name, get_agri_crop_segmenter, get_agri_health_segmenter

    annotation = await db.get(Annotation, request.image_id)
    if annotation is None:
        raise HTTPException(status_code=404, detail="Image not found")

    import io

    from PIL import Image

    try:
        mc = await get_minio_client()
        response = mc.get_object(settings.MINIO_BUCKET, annotation.image_path)
        pil_image = Image.open(io.BytesIO(response.read()))
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Image fetch failed: {exc}")

    import numpy as np
    image_np = np.array(pil_image)

    device = "gpu" if settings.ENVIRONMENT == "production" else "cpu"

    try:
        crop_segmenter = await get_agri_crop_segmenter(settings.AGRI_CROP_SEG_MODEL_PATH, device, db=db)
        health_segmenter = await get_agri_health_segmenter(settings.AGRI_HEALTH_SEG_MODEL_PATH, device, db=db)

        start = time.perf_counter()
        crop_results = crop_segmenter.segment(image_np, request.conf_threshold, request.iou_threshold)
        health_results = health_segmenter.segment(image_np, request.conf_threshold, request.iou_threshold)
        elapsed_ms = (time.perf_counter() - start) * 1000
    except Exception as exc:
        logger.error("agri_segmentation_failed", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Agri segmentation failed")

    crop_type = dominant_class_name(crop_results, default="maize")
    health_status = dominant_class_name(health_results, default="healthy")

    instances = _instances_to_schema(crop_results) + _instances_to_schema(health_results)

    existing = await db.execute(
        select(AgriAnnotation).where(AgriAnnotation.annotation_id == request.image_id)
    )
    existing_aa = existing.scalar_one_or_none()

    if existing_aa:
        existing_aa.instances = [inst.model_dump() for inst in instances]
        existing_aa.crop_type = crop_type
        existing_aa.health_status = health_status
        existing_aa.model_version = "yolov8n-seg-v1"
        existing_aa.auto_generated = True
    else:
        aa = AgriAnnotation(
            annotation_id=request.image_id,
            crop_type=crop_type,
            health_status=health_status,
            instances=[inst.model_dump() for inst in instances],
            model_version="yolov8n-seg-v1",
            auto_generated=True,
            reviewed=False,
        )
        db.add(aa)

    await db.commit()

    logger.info(
        "agri_segmentation_completed",
        image_id=str(request.image_id),
        instances=len(instances),
        crop_type=crop_type,
        health_status=health_status,
        latency_ms=round(elapsed_ms, 2),
    )

    return AgriSegmentationResponse(
        image_id=request.image_id,
        instances=instances,
        crop_type=crop_type,
        health_status=health_status,
        model_version="yolov8n-seg-v1",
        latency_ms=round(elapsed_ms, 2),
    )


@agri_router.post("/segment/batch", response_model=AgriSegmentationBatchResponse)
async def segment_batch(
    request: AgriSegmentationBatchRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from app.workers.tasks import auto_label_agri_task

    job_id = uuid4()

    auto_label_agri_task.apply_async(
        args=[[str(i) for i in request.image_ids]],
        kwargs={
            "conf_threshold": request.conf_threshold,
            "iou_threshold": request.iou_threshold,
        },
        task_id=str(job_id),
    )

    return AgriSegmentationBatchResponse(
        job_id=job_id,
        total_images=len(request.image_ids),
    )


@agri_router.get("/result/{annotation_id}", response_model=AgriAnnotationResponse)
async def get_agri_result(
    annotation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(AgriAnnotation).where(AgriAnnotation.annotation_id == annotation_id)
    )
    aa = result.scalar_one_or_none()
    if aa is None:
        raise HTTPException(status_code=404, detail="Agri annotation not found")

    instances = _instances_to_schema(aa.instances if isinstance(aa.instances, list) else [])

    return AgriAnnotationResponse(
        id=aa.id,
        annotation_id=aa.annotation_id,
        crop_type=aa.crop_type,
        health_status=aa.health_status,
        instances=instances,
        model_version=aa.model_version,
        auto_generated=aa.auto_generated,
        reviewed=aa.reviewed,
        created_at=aa.created_at.isoformat() if aa.created_at else "",
        updated_at=aa.updated_at.isoformat() if aa.updated_at else "",
    )


@agri_router.patch("/result/{annotation_id}", response_model=AgriAnnotationResponse)
async def update_agri_result(
    annotation_id: UUID,
    update: AgriAnnotationUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role(["ADMIN", "QA", "ANNOTATOR"])),
):
    result = await db.execute(
        select(AgriAnnotation).where(AgriAnnotation.annotation_id == annotation_id)
    )
    aa = result.scalar_one_or_none()
    if aa is None:
        raise HTTPException(status_code=404, detail="Agri annotation not found")

    if update.instances is not None:
        aa.instances = [inst.model_dump() for inst in update.instances]
    if update.crop_type is not None:
        aa.crop_type = update.crop_type
    if update.health_status is not None:
        aa.health_status = update.health_status
    if update.reviewed is not None:
        aa.reviewed = update.reviewed
    aa.auto_generated = False

    await db.commit()
    await db.refresh(aa)

    instances = _instances_to_schema(aa.instances if isinstance(aa.instances, list) else [])

    return AgriAnnotationResponse(
        id=aa.id,
        annotation_id=aa.annotation_id,
        crop_type=aa.crop_type,
        health_status=aa.health_status,
        instances=instances,
        model_version=aa.model_version,
        auto_generated=aa.auto_generated,
        reviewed=aa.reviewed,
        created_at=aa.created_at.isoformat() if aa.created_at else "",
        updated_at=aa.updated_at.isoformat() if aa.updated_at else "",
    )


@agri_router.get("/classes", response_model=AgriClassesResponse)
async def get_agri_classes():
    crop_classes = [
        {"id": cid, "name": cdef["name"], "color": cdef["color"], "description": cdef["description"], "category": "crop"}
        for cid, cdef in CROP_CLASSES.items()
    ]
    health_classes = [
        {"id": cid + 100, "name": cdef["name"], "color": cdef["color"], "description": cdef["description"], "category": "health"}
        for cid, cdef in HEALTH_CLASSES.items()
    ]
    return AgriClassesResponse(
        classes=crop_classes + health_classes,
        version=AGRI_TAXONOMY_VERSION,
    )


@agri_router.post("/analyze", response_model=AgriAnalysisReport)
async def analyze_agri_condition(
    request: AgriAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role_and_feature(["ADMIN", "QA"], "agriAnalysis")),
):
    try:
        report = await analyze_dataset_agri_condition(db, request.dataset_id)
        return report
    except Exception as exc:
        logger.error("agri_analysis_failed", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Agri condition analysis failed")
