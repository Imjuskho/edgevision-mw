"""B2B Perception API — clean SDK boundary for external consumers.

Provides REST endpoints for:
- Frame processing via the PerceptionSDK
- Edge-case submission
- Model evaluation
- Dataset export formats
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user
from app.core.features import require_feature

b2b_router = APIRouter(prefix="/api/v1/b2b", tags=["B2B Perception"])

class FrameProcessRequest(BaseModel):
    enable_detection: bool = True
    enable_segmentation: bool = True
    enable_depth: bool = True
    enable_tracking: bool = True
    enable_events: bool = False
    enable_road_analysis: bool = False
    confidence_threshold: float = 0.45
    target_classes: list[str] | None = None
    image_base64: str | None = Field(
        default=None,
        description="Base64-encoded image bytes. If omitted, the SDK receives an empty frame.",
    )

class FrameProcessResponse(BaseModel):
    frame_id: str
    timestamp: str
    detections_count: int
    detections: list[dict]
    segmentation: dict | None = None
    depth_available: bool = False
    events: list[dict] = []
    processing_ms: float = 0.0
    note: str | None = Field(default=None, description="Informational note about the processing")

class EdgeCaseSubmitRequest(BaseModel):
    case_type: str
    camera_node_id: str
    frame_timestamp: str
    image_path: str | None = None
    detection_data: dict | None = None
    description: str = ""

class EvalRunRequest(BaseModel):
    model_version: str
    predictions: list[dict]
    ground_truths: list[dict]
    iou_threshold: float = 0.5

class ExportRequest(BaseModel):
    dataset_id: str = Field(..., description="Dataset ID to export")
    format: str = "coco"  # "coco", "cityscapes", "kitti"
    dataset_name: str = "edgevision_dataset"
    include_depth: bool = True
    include_segmentation: bool = True

@b2b_router.post("/process", response_model=FrameProcessResponse)
async def process_frame(
    request: FrameProcessRequest,
    user: dict = Depends(require_feature("training")),
):
    """Process a frame through the perception pipeline."""
    from app.services.perception_sdk import PerceptionSDK, PerceptionConfig
    
    sdk = PerceptionSDK()
    config = PerceptionConfig(
        enable_detection=request.enable_detection,
        enable_segmentation=request.enable_segmentation,
        enable_depth=request.enable_depth,
        enable_tracking=request.enable_tracking,
        enable_events=request.enable_events,
        enable_road_analysis=request.enable_road_analysis,
        confidence_threshold=request.confidence_threshold,
        target_classes=request.target_classes,
    )
    
    import base64
    import logging

    _logger = logging.getLogger(__name__)

    frame_bytes: bytes = b""
    image_note: str | None = None

    if request.image_base64:
        try:
            frame_bytes = base64.b64decode(request.image_base64)
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid base64 in image_base64 field")
    else:
        _logger.warning("B2B frame process called without image data")
        image_note = "No image provided — SDK received an empty frame"

    result = sdk.process_frame(frame_bytes, config)

    response = FrameProcessResponse(
        frame_id=result.frame_id,
        timestamp=result.timestamp,
        detections_count=len(result.detections),
        detections=result.detections,
        segmentation=result.segmentation,
        depth_available=result.depth_map_available,
        events=result.events,
        processing_ms=result.metadata.get("processing_ms", 0),
        note=image_note,
    )
    return response

@b2b_router.get("/capabilities")
async def get_capabilities(user: dict = Depends(get_current_user)):
    """Get SDK capabilities."""
    from app.services.perception_sdk import PerceptionSDK
    return PerceptionSDK().get_capabilities()

@b2b_router.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)):
    """Get pipeline statistics."""
    from app.services.perception_sdk import PerceptionSDK
    return PerceptionSDK().get_stats()

@b2b_router.post("/edge-cases")
async def submit_edge_case(
    request: EdgeCaseSubmitRequest,
    user: dict = Depends(require_feature("training")),
):
    """Submit an edge case for the labeling queue."""
    from app.services.data_flywheel import DataFlywheel
    flywheel = DataFlywheel()
    
    if request.case_type == "missed_detection":
        case = flywheel.collect_missed_detection(
            camera_node_id=request.camera_node_id,
            frame_timestamp=request.frame_timestamp,
            lost_track_id=0,
            last_known_class="unknown",
            last_confidence=0.0,
            image_path=request.image_path,
        )
    elif request.case_type == "anomaly":
        case = flywheel.collect_anomaly(
            camera_node_id=request.camera_node_id,
            frame_timestamp=request.frame_timestamp,
            anomaly_score=2.0,
            anomaly_type="manual",
            description=request.description,
            image_path=request.image_path,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported case type: {request.case_type}")
    
    return {"case_id": case.id, "status": "submitted"}

@b2b_router.post("/evaluate")
async def run_evaluation(
    request: EvalRunRequest,
    user: dict = Depends(require_feature("training")),
):
    """Run model evaluation against ground truth."""
    from app.services.evaluation_harness import run_evaluation
    result = run_evaluation(
        predictions=request.predictions,
        ground_truths=request.ground_truths,
        model_version=request.model_version,
        iou_threshold=request.iou_threshold,
    )
    return {
        "model_version": result.model_version,
        "mAP50": result.mAP50,
        "precision": result.precision,
        "recall": result.recall,
        "f1_score": result.f1_score,
        "per_class_ap": result.per_class_ap,
        "regression_detected": result.regression_detected,
        "passed": result.passed,
    }

@b2b_router.post("/export")
async def export_dataset(
    request: ExportRequest,
    user: dict = Depends(require_feature("training")),
):
    """Export dataset in standardized format.

    Looks up the dataset, computes real metadata from the database, and
    dispatches the async export pipeline via Celery.
    """
    from collections import Counter

    from fastapi import HTTPException
    from sqlalchemy import func, select

    from app.core.database import async_session
    from app.models.annotation import Annotation
    from app.models.dataset import Dataset
    from app.models.enums import ExportStatus
    from app.models.export import Export, ExportLog
    from app.services.standardized_exports import get_export_metadata
    from app.workers.tasks import export_dataset_task

    async with async_session() as db:
        ds_result = await db.execute(
            select(Dataset).where(Dataset.dataset_id == request.dataset_id)
        )
        dataset = ds_result.scalar_one_or_none()
        if dataset is None:
            raise HTTPException(status_code=404, detail=f"Dataset {request.dataset_id} not found")

        # Count images in dataset
        count_result = await db.execute(
            select(func.count(Annotation.id)).where(Annotation.dataset_id == dataset.id)
        )
        sample_count = count_result.scalar() or 0

        # Build real class distribution from annotation labels
        anns_result = await db.execute(
            select(Annotation).where(Annotation.dataset_id == dataset.id)
        )
        class_counter: Counter = Counter()
        for ann in anns_result.scalars().all():
            for label in (ann.human_labels or ann.auto_labels or {}).get("labels", []):
                if isinstance(label, dict):
                    class_counter[label.get("class_name", "unknown")] += 1
        class_distribution = dict(class_counter)

        # Create Export record
        import hashlib
        import secrets
        from datetime import UTC, datetime, timedelta

        license_key = hashlib.sha256(secrets.token_bytes(32)).hexdigest()[:64]
        export_rec = Export(
            dataset_id=dataset.id,
            buyer_id=user["sub"],
            license_key=license_key,
            license_type=dataset.license_type,
            status=ExportStatus.PENDING,
            price_usd=dataset.price_usd,
            watermark_fingerprint=license_key[:16],
            formats_delivered=[request.format],
            initiated_at=datetime.now(UTC),
            usage_rights={"license_type": str(dataset.license_type)},
        )
        db.add(export_rec)
        await db.commit()
        await db.refresh(export_rec)

        # Dispatch async export pipeline
        export_dataset_task.delay(str(export_rec.id))

        metadata = get_export_metadata(
            dataset_id=request.dataset_id,
            format_type=request.format,
            sample_count=sample_count,
            class_distribution=class_distribution,
        )

        return {
            "export_id": str(export_rec.id),
            "dataset_id": request.dataset_id,
            "status": "PENDING",
            "estimated_completion_seconds": sample_count * 2,
            "metadata": metadata,
        }
