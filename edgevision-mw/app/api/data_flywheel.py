from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user
from app.core.features import require_role_and_feature

flywheel_router = APIRouter(prefix="/flywheel", tags=["Data Flywheel"])


class EdgeCaseCollectRequest(BaseModel):
    camera_node_id: str = Field(..., description="Edge device node ID")
    frame_timestamp: str = Field(..., description="ISO timestamp of the frame")
    case_type: str = Field(..., description="Type: missed_detection, false_positive, anomaly")
    image_path: str | None = None
    description: str = ""
    detection_data: dict | None = None
    lost_track_id: int | None = None
    last_known_class: str | None = None
    last_confidence: float | None = None


class BatchSendRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list, description="Specific case IDs to send (empty = all pending)")


@flywheel_router.get("/pending")
async def list_pending_edge_cases(
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """List pending edge cases for human labeling."""
    from app.services.data_flywheel import DataFlywheel
    from app.core.database import async_session

    flywheel = DataFlywheel()
    async with async_session() as db:
        candidates = await flywheel.get_labeling_candidates(db, limit=limit)
    return {"items": candidates, "total": len(candidates)}


@flywheel_router.get("/stats")
async def get_flywheel_stats(
    user: dict = Depends(get_current_user),
):
    """Get flywheel statistics."""
    from app.services.data_flywheel import DataFlywheel

    flywheel = DataFlywheel()
    stats = flywheel.get_stats()
    return {
        "total_edge_cases": stats.total_edge_cases,
        "by_type": stats.by_type,
        "by_severity": stats.by_severity,
        "pending_labeling": stats.pending_labeling,
        "in_review": stats.in_review,
        "completed": stats.completed,
    }


@flywheel_router.post("/collect")
async def collect_edge_case(
    request: EdgeCaseCollectRequest,
    user: dict = Depends(require_role_and_feature(["ADMIN", "OPERATOR", "FIELD_TECH"], "training")),
):
    """Collect an edge case (missed detection, false positive, anomaly, etc.)."""
    from app.services.data_flywheel import DataFlywheel

    flywheel = DataFlywheel()

    if request.case_type == "missed_detection":
        case = flywheel.collect_missed_detection(
            camera_node_id=request.camera_node_id,
            frame_timestamp=request.frame_timestamp,
            lost_track_id=request.lost_track_id or 0,
            last_known_class=request.last_known_class or "unknown",
            last_confidence=request.last_confidence or 0.0,
            image_path=request.image_path,
        )
    elif request.case_type == "false_positive":
        case = flywheel.collect_false_positive(
            camera_node_id=request.camera_node_id,
            frame_timestamp=request.frame_timestamp,
            event_id=request.detection_data.get("event_id", "manual") if request.detection_data else "manual",
            rule_id=request.detection_data.get("rule_id", "manual") if request.detection_data else "manual",
            suppression_reason=request.description or "manual_submission",
            detection_data=request.detection_data,
            image_path=request.image_path,
        )
    elif request.case_type == "anomaly":
        case = flywheel.collect_anomaly(
            camera_node_id=request.camera_node_id,
            frame_timestamp=request.frame_timestamp,
            anomaly_score=2.0,
            anomaly_type="manual",
            description=request.description or "Manual edge case submission",
            image_path=request.image_path,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported case type: {request.case_type}")

    return {
        "id": case.id,
        "case_type": case.case_type,
        "severity": case.severity,
        "description": case.description,
        "created_at": case.created_at,
    }


@flywheel_router.post("/batch-send")
async def batch_send_to_labeling(
    request: BatchSendRequest,
    user: dict = Depends(require_role_and_feature(["ADMIN", "OPERATOR"], "training")),
):
    """Send pending edge cases to the labeling queue."""
    from app.services.data_flywheel import DataFlywheel
    from app.core.database import async_session

    flywheel = DataFlywheel()

    if request.case_ids:
        count = flywheel.mark_sent_to_labeling(request.case_ids)
        return {"sent": count, "case_ids": request.case_ids}

    # Flush all pending cases to DB
    async with async_session() as db:
        flushed = await flywheel.flush_to_db(db)

    return {"sent": flushed, "message": f"Flushed {flushed} edge cases to labeling queue"}
