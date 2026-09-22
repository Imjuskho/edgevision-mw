from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.logging import get_logger
from app.schemas.frontier_capabilities import (
    AnomalyDetectRequest,
    AnomalyEventResponse,
    AnomalyListResponse,
    AnomalyResolveRequest,
    AnomalyResolveResponse,
    PredictionAccuracyResponse,
    PredictionListResponse,
    ReconstructionCreateRequest,
    ReconstructionListResponse,
    ReconstructionResponse,
    SceneSummaryResponse,
    SendToLabelingResponse,
    SpatialQueryRequest,
    SpatialQueryResponse,
    TrajectoryPredictRequest,
    TrajectoryPredictResponse,
)

logger = get_logger("edgevision.frontier")

frontier_router = APIRouter(prefix="/frontier", tags=["Frontier Capabilities"])


# ---------------------------------------------------------------------------
# Trajectory Prediction
# ---------------------------------------------------------------------------


@frontier_router.post(
    "/predict",
    response_model=TrajectoryPredictResponse,
    status_code=status.HTTP_201_CREATED,
)
async def predict_trajectory_endpoint(
    body: TrajectoryPredictRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Predict future trajectory for a tracked object."""
    from app.services.trajectory_prediction import (
        check_road_intersection,
        predict_trajectory,
        store_trajectory_prediction,
    )

    now = datetime.now(UTC)

    track_state = body.track_state
    current_state = {
        "x": track_state.x,
        "y": track_state.y,
        "z": track_state.z,
        "vx": track_state.vx,
        "vy": track_state.vy,
        "vz": track_state.vz,
        "class_name": track_state.class_name,
    }

    # Build history including current state
    history = list(body.track_history)
    history.append(
        {
            **current_state,
            "timestamp": now.isoformat(),
        }
    )

    predictions = predict_trajectory(history, body.prediction_horizons)
    road_intersection = check_road_intersection(
        [p["position"] for p in predictions],
        body.road_mask,
        body.lane_boundaries,
    )

    record = await store_trajectory_prediction(
        db=db,
        track_id=track_state.track_id,
        frame_timestamp=now,
        current_state=current_state,
        predictions=predictions,
        road_intersection=road_intersection,
    )

    from app.schemas.frontier_capabilities import PredictedPoint, RoadIntersectionInfo, TrackPoint

    predicted_points = [
        PredictedPoint(
            time_ahead=p["time_ahead"],
            position=TrackPoint(**p["position"]),
            method=p["method"],
            confidence=p["confidence"],
        )
        for p in predictions
    ]

    will_intersect, tti, conf = road_intersection
    return TrajectoryPredictResponse(
        id=record.id,
        track_id=record.track_id,
        frame_timestamp=record.frame_timestamp,
        current_position=TrackPoint(**record.current_position),
        heading_rad=record.heading_rad,
        predictions=predicted_points,
        road_intersection=RoadIntersectionInfo(
            will_intersect=will_intersect,
            time_to_intersection=tti,
            confidence=conf,
        ),
        prediction_method=record.prediction_method,
        created_at=record.created_at,
    )


@frontier_router.get("/predictions", response_model=PredictionListResponse)
async def list_predictions(
    camera_node_id: str = Query(..., description="Camera node ID"),
    minutes: int = Query(default=5, ge=1, le=60, description="Lookback window in minutes"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List recent trajectory predictions for a camera."""
    from app.services.trajectory_prediction import get_recent_predictions

    records = await get_recent_predictions(db, camera_node_id, minutes)
    total = len(records)
    offset = (page - 1) * page_size
    page_records = records[offset : offset + page_size]

    items = [
        TrajectoryPredictResponse(
            id=r.id,
            track_id=r.track_id,
            frame_timestamp=r.frame_timestamp,
            current_position=r.current_position,
            heading_rad=r.heading_rad,
            predictions=[
                {"time_ahead": t, "position": p, "method": r.prediction_method, "confidence": 0.8}
                for t, p in zip(r.predicted_times, r.predicted_positions, strict=False)
            ],
            road_intersection={
                "will_intersect": r.will_intersect_road,
                "time_to_intersection": r.time_to_road_intersection,
                "confidence": r.intersection_confidence,
            },
            prediction_method=r.prediction_method,
            created_at=r.created_at,
        )
        for r in page_records
    ]

    import math

    pages = math.ceil(total / page_size) if page_size > 0 else 0
    return PredictionListResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@frontier_router.get("/predictions/accuracy", response_model=PredictionAccuracyResponse)
async def get_prediction_accuracy_endpoint(
    track_id: int = Query(..., description="Track ID to evaluate"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get prediction accuracy statistics for a track."""
    from app.services.trajectory_prediction import get_prediction_accuracy

    result = await get_prediction_accuracy(db, track_id)
    return PredictionAccuracyResponse(**result)


# ---------------------------------------------------------------------------
# Anomaly Detection
# ---------------------------------------------------------------------------


@frontier_router.post(
    "/detect",
    response_model=AnomalyEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def detect_anomaly_endpoint(
    body: AnomalyDetectRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run open-set anomaly detection on the latest frame."""
    from app.services.anomaly_detection import (
        detect_anomaly,
        store_anomaly,
        update_scene_baseline,
    )

    # Build embedding from provided features
    embedding: dict = {
        "object_counts": len(body.detections),
        "class_distribution": {},
        "road_ratio": float((body.road_result or {}).get("drivable_area_ratio", 0.0)),
        "avg_confidence": 0.0,
    }

    total_conf = 0.0
    for det in body.detections:
        cls = det.get("class_name", det.get("label", "unknown"))
        embedding["class_distribution"][cls] = embedding["class_distribution"].get(cls, 0) + 1
        conf = float(det.get("confidence", 0.0))
        total_conf += conf

    if body.detections:
        embedding["avg_confidence"] = total_conf / len(body.detections)

    if body.depth_stats:
        embedding["depth_histogram"] = body.depth_stats.get("histogram", {"near": 0, "mid": 0, "far": 0})

    # Update baseline
    update_scene_baseline(body.camera_node_id, embedding)

    # Detect anomaly
    result = detect_anomaly(body.camera_node_id, embedding)

    if result is None:
        # Return a "no anomaly" response
        from app.schemas.frontier_capabilities import AnomalyEventResponse as AER

        return AER(
            id="",
            camera_node_id=body.camera_node_id,
            frame_timestamp=datetime.now(UTC),
            anomaly_score=0.0,
            anomaly_type="normal",
            description="No anomaly detected",
            embedding_distance=None,
            bounding_box=None,
            is_confirmed=False,
            resolved=False,
            resolution_note=None,
            feedback_for_labeling=False,
            created_at=datetime.now(UTC),
        )

    # Store anomaly
    record = await store_anomaly(
        db=db,
        camera_node_id=body.camera_node_id,
        timestamp=datetime.now(UTC),
        anomaly_score=result["anomaly_score"],
        anomaly_type=result["anomaly_type"],
        description=result["description"],
        features=result,
        bounding_box=body.bounding_box,
    )

    return AnomalyEventResponse(
        id=record.id,
        camera_node_id=record.camera_node_id,
        frame_timestamp=record.frame_timestamp,
        anomaly_score=record.anomaly_score,
        anomaly_type=record.anomaly_type,
        description=record.description,
        embedding_distance=record.embedding_distance,
        bounding_box=record.bounding_box,
        is_confirmed=record.is_confirmed,
        resolved=record.resolved,
        resolution_note=record.resolution_note,
        feedback_for_labeling=record.feedback_for_labeling,
        created_at=record.created_at,
    )


@frontier_router.get("/anomalies", response_model=AnomalyListResponse)
async def list_anomalies(
    camera_node_id: str | None = Query(default=None, description="Filter by camera node"),
    limit: int = Query(default=50, ge=1, le=200),
    unresolved_only: bool = Query(default=True, description="Only unresolved anomalies"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List anomaly events."""
    from app.services.anomaly_detection import get_anomalies

    records = await get_anomalies(db, camera_node_id, limit, unresolved_only)
    total = len(records)
    offset = (page - 1) * page_size
    page_records = records[offset : offset + page_size]

    items = [
        AnomalyEventResponse(
            id=r.id,
            camera_node_id=r.camera_node_id,
            frame_timestamp=r.frame_timestamp,
            anomaly_score=r.anomaly_score,
            anomaly_type=r.anomaly_type,
            description=r.description,
            embedding_distance=r.embedding_distance,
            bounding_box=r.bounding_box,
            is_confirmed=r.is_confirmed,
            resolved=r.resolved,
            resolution_note=r.resolution_note,
            feedback_for_labeling=r.feedback_for_labeling,
            created_at=r.created_at,
        )
        for r in page_records
    ]

    import math

    pages = math.ceil(total / page_size) if page_size > 0 else 0
    return AnomalyListResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@frontier_router.post("/anomalies/{anomaly_id}/resolve", response_model=AnomalyResolveResponse)
async def resolve_anomaly_endpoint(
    anomaly_id: str,
    body: AnomalyResolveRequest,
    user: dict = Depends(require_role(["ADMIN", "QA", "OPERATOR"])),
    db: AsyncSession = Depends(get_db),
):
    """Resolve an anomaly event."""
    from app.services.anomaly_detection import resolve_anomaly

    record = await resolve_anomaly(db, anomaly_id, body.resolution_note)
    return AnomalyResolveResponse(
        id=record.id,
        resolved=record.resolved,
        resolution_note=record.resolution_note,
    )


@frontier_router.post(
    "/anomalies/{anomaly_id}/send-to-labeling",
    response_model=SendToLabelingResponse,
)
async def send_to_labeling_endpoint(
    anomaly_id: str,
    user: dict = Depends(require_role(["ADMIN", "QA"])),
    db: AsyncSession = Depends(get_db),
):
    """Flag an anomaly for human review / labeling."""
    from app.services.anomaly_detection import send_to_labeling_queue

    record = await send_to_labeling_queue(db, anomaly_id)
    return SendToLabelingResponse(
        id=record.id,
        is_confirmed=record.is_confirmed,
        feedback_for_labeling=record.feedback_for_labeling,
    )


# ---------------------------------------------------------------------------
# Scene Reconstruction
# ---------------------------------------------------------------------------


@frontier_router.post(
    "/reconstruct",
    response_model=ReconstructionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reconstruction_endpoint(
    body: ReconstructionCreateRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a 3D scene reconstruction snapshot."""
    from app.services.scene_reconstruction import create_reconstruction_snapshot

    detections = [d.model_dump() for d in body.detections]
    depth_map = body.depth_map.model_dump()
    record = await create_reconstruction_snapshot(
        db=db,
        camera_node_id=body.camera_node_id,
        detections=detections,
        depth_map=depth_map,
        road_result=body.road_result,
    )

    return ReconstructionResponse(
        id=record.id,
        camera_node_id=record.camera_node_id,
        timestamp=record.timestamp,
        num_gaussians=record.num_gaussians,
        num_keyframes=record.num_keyframes,
        scene_bounds=record.scene_bounds,
        dominant_classes=record.dominant_classes,
        static_objects=record.static_objects,
        dynamic_objects=record.dynamic_objects,
        change_events=record.change_events,
        reconstruction_quality=record.reconstruction_quality,
        created_at=record.created_at,
    )


@frontier_router.get("/reconstructions", response_model=ReconstructionListResponse)
async def list_reconstructions(
    camera_node_id: str = Query(..., description="Camera node ID"),
    limit: int = Query(default=20, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List recent scene reconstructions."""
    from app.services.scene_reconstruction import get_reconstruction_history

    records = await get_reconstruction_history(db, camera_node_id, limit)
    total = len(records)
    offset = (page - 1) * page_size
    page_records = records[offset : offset + page_size]

    items = [
        ReconstructionResponse(
            id=r.id,
            camera_node_id=r.camera_node_id,
            timestamp=r.timestamp,
            num_gaussians=r.num_gaussians,
            num_keyframes=r.num_keyframes,
            scene_bounds=r.scene_bounds,
            dominant_classes=r.dominant_classes,
            static_objects=r.static_objects,
            dynamic_objects=r.dynamic_objects,
            change_events=r.change_events,
            reconstruction_quality=r.reconstruction_quality,
            created_at=r.created_at,
        )
        for r in page_records
    ]

    import math

    pages = math.ceil(total / page_size) if page_size > 0 else 0
    return ReconstructionListResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@frontier_router.get("/reconstructions/history", response_model=list[ReconstructionResponse])
async def get_reconstruction_history_endpoint(
    camera_node_id: str = Query(..., description="Camera node ID"),
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get reconstruction history for a camera."""
    from app.services.scene_reconstruction import get_reconstruction_history

    records = await get_reconstruction_history(db, camera_node_id, limit)
    return [
        ReconstructionResponse(
            id=r.id,
            camera_node_id=r.camera_node_id,
            timestamp=r.timestamp,
            num_gaussians=r.num_gaussians,
            num_keyframes=r.num_keyframes,
            scene_bounds=r.scene_bounds,
            dominant_classes=r.dominant_classes,
            static_objects=r.static_objects,
            dynamic_objects=r.dynamic_objects,
            change_events=r.change_events,
            reconstruction_quality=r.reconstruction_quality,
            created_at=r.created_at,
        )
        for r in records
    ]


@frontier_router.post("/query", response_model=SpatialQueryResponse)
async def spatial_query_endpoint(
    body: SpatialQueryRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute spatial queries against scene reconstructions."""
    from app.services.scene_reconstruction import query_spatial

    result = await query_spatial(db, body.camera_node_id, body.query_type, body.params)
    return SpatialQueryResponse(**result)


@frontier_router.get("/summary", response_model=SceneSummaryResponse)
async def get_scene_summary_endpoint(
    camera_node_id: str = Query(..., description="Camera node ID"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current scene summary for a camera."""
    from app.services.scene_reconstruction import get_scene_summary

    result = await get_scene_summary(db, camera_node_id)
    return SceneSummaryResponse(**result)
