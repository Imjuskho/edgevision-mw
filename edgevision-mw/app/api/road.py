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
from app.models.annotation import Annotation
from app.models.road_annotation import RoadAnnotation
from app.models.road_taxonomy import ROAD_SURFACE_CLASSES, ROAD_TAXONOMY_VERSION
from app.schemas.road import (
    ColorExtractionResponse,
    InstanceMask,
    PoseDetectionResponse,
    RoadAnalyzeRequest,
    RoadAnnotationResponse,
    RoadAnnotationUpdate,
    RoadClassesResponse,
    RoadConditionReport,
    RoadSegmentationBatchRequest,
    RoadSegmentationBatchResponse,
    RoadSegmentationRequest,
    RoadSegmentationResponse,
    SignDetectionResponse,
    TrackingRequest,
    TrackingResponse,
)
from app.services.road_analysis import analyze_dataset_road_condition

logger = get_logger("edgevision.road_api")

road_router = APIRouter(prefix="/road", tags=["Road Segmentation"])


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


@road_router.post("/segment", response_model=RoadSegmentationResponse)
async def segment_image(
    request: RoadSegmentationRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from app.ai.road_segmenter import classify_surface_type, get_road_segmenter

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

    try:
        segmenter = await get_road_segmenter(settings.ROAD_SEG_MODEL_PATH, "gpu" if settings.ENVIRONMENT == "production" else "cpu", db=db)
        if not segmenter.is_loaded():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Road segmentation model not available. "
                    "Train a road model with scripts/train_road_seg.py and set ROAD_SEG_MODEL_PATH "
                    "to models/road_seg/best.onnx. COCO-pretrained models are rejected."
                ),
            )
        start = time.perf_counter()
        results = segmenter.segment(image_np, request.conf_threshold, request.iou_threshold)
        elapsed_ms = (time.perf_counter() - start) * 1000
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("road_segmentation_failed", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Road segmentation failed")

    surface_type = classify_surface_type(results) if results else "unpaved"
    instances = _instances_to_schema(results)

    existing = await db.execute(
        select(RoadAnnotation).where(RoadAnnotation.annotation_id == request.image_id)
    )
    existing_ra = existing.scalar_one_or_none()

    if existing_ra:
        existing_ra.instances = [inst.model_dump() for inst in instances]
        existing_ra.surface_type = surface_type
        existing_ra.model_version = "yolov8n-seg-v2-corrected"
        existing_ra.auto_generated = True
    else:
        ra = RoadAnnotation(
            annotation_id=request.image_id,
            surface_type=surface_type,
            instances=[inst.model_dump() for inst in instances],
            model_version="yolov8n-seg-v2-corrected",
            auto_generated=True,
            reviewed=False,
        )
        db.add(ra)

    await db.commit()

    logger.info(
        "road_segmentation_completed",
        image_id=str(request.image_id),
        instances=len(instances),
        surface_type=surface_type,
        latency_ms=round(elapsed_ms, 2),
    )

    return RoadSegmentationResponse(
        image_id=request.image_id,
        instances=instances,
        surface_type=surface_type,
        model_version="yolov8n-seg-v2-corrected",
        latency_ms=round(elapsed_ms, 2),
    )


@road_router.post("/segment/batch", response_model=RoadSegmentationBatchResponse)
async def segment_batch(
    request: RoadSegmentationBatchRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from app.ai.road_segmenter import get_road_segmenter
    from app.services.batch_inference import resolve_batch_annotation_ids
    from app.workers.tasks import auto_label_road_task

    if not request.dataset_id and not request.image_ids:
        raise HTTPException(
            status_code=400,
            detail="Provide dataset_id or image_ids",
        )

    segmenter = await get_road_segmenter(
        settings.ROAD_SEG_MODEL_PATH,
        "gpu" if settings.ENVIRONMENT == "production" else "cpu",
        db=db,
    )
    if not segmenter.is_loaded():
        raise HTTPException(
            status_code=503,
            detail=(
                "Road segmentation model not available. "
                "Train a road model with scripts/train_road_seg.py and set ROAD_SEG_MODEL_PATH "
                "to models/road_seg/best.onnx. COCO-pretrained models are rejected."
            ),
        )

    if request.dataset_id:
        image_ids, skipped = await resolve_batch_annotation_ids(
            db,
            request.dataset_id,
            image_ids=request.image_ids,
            scope=request.scope,
            mode="road",
            force=request.force,
        )
    else:
        image_ids = list(request.image_ids or [])
        skipped = 0

    if not image_ids:
        raise HTTPException(
            status_code=400,
            detail="No unannotated images to process. All frames already have road annotations.",
        )

    job_id = uuid4()

    auto_label_road_task.apply_async(
        args=[[str(i) for i in image_ids]],
        kwargs={
            "conf_threshold": request.conf_threshold,
            "iou_threshold": request.iou_threshold,
            "force": request.force,
        },
        task_id=str(job_id),
    )

    return RoadSegmentationBatchResponse(
        job_id=job_id,
        total_images=len(image_ids),
        skipped=skipped,
    )


@road_router.post("/signs", response_model=SignDetectionResponse)
async def detect_signs(
    request: RoadSegmentationRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from app.ai.text_detection import detect_and_ocr, detect_signs

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

    start = time.perf_counter()
    signs = detect_signs(image_np)
    text_regions = detect_and_ocr(image_np)
    elapsed_ms = (time.perf_counter() - start) * 1000

    from app.schemas.road import SignDetectionResult

    return SignDetectionResponse(
        image_id=request.image_id,
        signs=[SignDetectionResult(**s) for s in signs],
        text_regions=text_regions,
        latency_ms=round(elapsed_ms, 2),
    )


@road_router.post("/color", response_model=ColorExtractionResponse)
async def extract_colors(
    request: RoadSegmentationRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from app.ai.color_extraction import extract_color_features

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

    start = time.perf_counter()
    features = extract_color_features(image_np)
    elapsed_ms = (time.perf_counter() - start) * 1000

    return ColorExtractionResponse(
        image_id=request.image_id,
        dominant_colors=features["dominant_colors"],
        color_classes=features["color_classes"],
        latency_ms=round(elapsed_ms, 2),
    )


@road_router.post("/pose", response_model=PoseDetectionResponse)
async def detect_poses(
    request: RoadSegmentationRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from app.ai.pose_detector import detect_poses as run_pose_detection

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

    start = time.perf_counter()
    poses = run_pose_detection(image_np, request.conf_threshold)
    elapsed_ms = (time.perf_counter() - start) * 1000

    from app.schemas.road import PoseDetectionResult

    return PoseDetectionResponse(
        image_id=request.image_id,
        poses=[PoseDetectionResult(**p) for p in poses],
        latency_ms=round(elapsed_ms, 2),
    )


@road_router.post("/track", response_model=TrackingResponse)
async def track_objects(
    request: TrackingRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    import io

    from PIL import Image

    from app.ai.object_tracker import ByteTrack
    from app.ai.yolo_detector import YOLODetector

    detector = YOLODetector()
    tracker = ByteTrack(track_high_thresh=request.conf_threshold)

    all_tracks = []
    for image_id in request.image_ids:
        annotation = await db.get(Annotation, image_id)
        if annotation is None:
            continue
        try:
            mc = await get_minio_client()
            resp = mc.get_object(settings.MINIO_BUCKET, annotation.image_path)
            pil_image = Image.open(io.BytesIO(resp.read()))
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
        except Exception:
            continue

        import numpy as np
        image_np = np.array(pil_image)
        detections = detector.detect(image_np, conf_threshold=request.conf_threshold)
        frame_tracks = tracker.update(
            [{"bbox": [d.x1, d.y1, d.x2, d.y2], "confidence": d.confidence, "class_name": d.class_name} for d in detections]
        )
        for t in frame_tracks:
            t["frame_id"] = str(image_id)
        all_tracks.extend(frame_tracks)

    return TrackingResponse(
        tracks=all_tracks,
        total_tracks=len(all_tracks),
    )


@road_router.get("/result/{annotation_id}", response_model=RoadAnnotationResponse)
async def get_road_result(
    annotation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(RoadAnnotation).where(RoadAnnotation.annotation_id == annotation_id)
    )
    ra = result.scalar_one_or_none()
    if ra is None:
        raise HTTPException(status_code=404, detail="Road annotation not found")

    instances = _instances_to_schema(ra.instances if isinstance(ra.instances, list) else [])

    return RoadAnnotationResponse(
        id=ra.id,
        annotation_id=ra.annotation_id,
        surface_type=ra.surface_type,
        instances=instances,
        model_version=ra.model_version,
        auto_generated=ra.auto_generated,
        reviewed=ra.reviewed,
        created_at=ra.created_at.isoformat() if ra.created_at else "",
        updated_at=ra.updated_at.isoformat() if ra.updated_at else "",
    )


@road_router.patch("/result/{annotation_id}", response_model=RoadAnnotationResponse)
async def update_road_result(
    annotation_id: UUID,
    update: RoadAnnotationUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role(["ADMIN", "QA", "ANNOTATOR"])),
):
    result = await db.execute(
        select(RoadAnnotation).where(RoadAnnotation.annotation_id == annotation_id)
    )
    ra = result.scalar_one_or_none()
    if ra is None:
        raise HTTPException(status_code=404, detail="Road annotation not found")

    if update.instances is not None:
        ra.instances = [inst.model_dump() for inst in update.instances]
    if update.surface_type is not None:
        ra.surface_type = update.surface_type
    if update.reviewed is not None:
        ra.reviewed = update.reviewed
    ra.auto_generated = False

    await db.commit()
    await db.refresh(ra)

    instances = _instances_to_schema(ra.instances if isinstance(ra.instances, list) else [])

    return RoadAnnotationResponse(
        id=ra.id,
        annotation_id=ra.annotation_id,
        surface_type=ra.surface_type,
        instances=instances,
        model_version=ra.model_version,
        auto_generated=ra.auto_generated,
        reviewed=ra.reviewed,
        created_at=ra.created_at.isoformat() if ra.created_at else "",
        updated_at=ra.updated_at.isoformat() if ra.updated_at else "",
    )


@road_router.get("/classes", response_model=RoadClassesResponse)
async def get_road_classes():
    classes = [
        {"id": cid, "name": cdef["name"], "color": cdef["color"], "description": cdef["description"]}
        for cid, cdef in ROAD_SURFACE_CLASSES.items()
    ]
    return RoadClassesResponse(classes=classes, version=ROAD_TAXONOMY_VERSION)


@road_router.post("/analyze", response_model=RoadConditionReport)
async def analyze_road_condition(
    request: RoadAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role_and_feature(["ADMIN", "QA"], "roadAnalysis")),
):
    try:
        report = await analyze_dataset_road_condition(db, request.dataset_id)
        return report
    except Exception as exc:
        logger.error("road_analysis_failed", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Road condition analysis failed")
