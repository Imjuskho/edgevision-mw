from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import PaginatedResponse

# ---------------------------------------------------------------------------
# Trajectory Prediction
# ---------------------------------------------------------------------------


class TrackPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    x: float = Field(..., description="X position in metres")
    y: float = Field(..., description="Y position in metres")
    z: float = Field(default=0.0, description="Z position in metres")


class TrackState(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    track_id: int = Field(..., description="Tracker-assigned track ID")
    x: float = Field(..., description="Current X position")
    y: float = Field(..., description="Current Y position")
    z: float = Field(default=0.0, description="Current Z position")
    vx: float = Field(default=0.0, description="Velocity X (m/s)")
    vy: float = Field(default=0.0, description="Velocity Y (m/s)")
    vz: float = Field(default=0.0, description="Velocity Z (m/s)")
    class_name: str | None = Field(default=None, description="Object class name")
    confidence: float = Field(default=0.0, description="Detection confidence")


class TrajectoryPredictRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    track_state: TrackState = Field(..., description="Current track state")
    track_history: list[dict] = Field(
        default_factory=list,
        description="Recent track history (last N frames)",
    )
    prediction_horizons: list[float] | None = Field(
        default=None,
        description="Seconds ahead to predict (default: [0.5, 1.0, 2.0, 3.0, 5.0])",
    )
    road_mask: dict | None = Field(default=None, description="Road segmentation mask")
    lane_boundaries: list[dict] | None = Field(default=None, description="Lane boundary segments")


class PredictedPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    time_ahead: float = Field(..., description="Seconds into the future")
    position: TrackPoint = Field(..., description="Predicted position")
    method: str = Field(..., description="Prediction method used")
    confidence: float = Field(..., description="Confidence in this prediction")


class RoadIntersectionInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    will_intersect: bool = Field(..., description="Whether trajectory will cross road")
    time_to_intersection: float | None = Field(default=None, description="Seconds until intersection")
    confidence: float = Field(default=0.0, description="Intersection confidence")


class TrajectoryPredictResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Prediction record ID")
    track_id: int = Field(..., description="Track ID")
    frame_timestamp: datetime = Field(..., description="Frame timestamp")
    current_position: TrackPoint = Field(..., description="Current position")
    heading_rad: float = Field(..., description="Heading in radians")
    predictions: list[PredictedPoint] = Field(..., description="Predicted positions")
    road_intersection: RoadIntersectionInfo = Field(..., description="Road intersection info")
    prediction_method: str = Field(..., description="Primary prediction method")
    created_at: datetime = Field(..., description="Record creation time")


class PredictionListResponse(PaginatedResponse[TrajectoryPredictResponse]):
    model_config = ConfigDict(from_attributes=True)


class PredictionAccuracyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    track_id: int = Field(..., description="Track ID")
    num_predictions: int = Field(..., description="Number of past predictions")
    horizon_accuracy: dict = Field(default_factory=dict, description="Error stats per horizon")


# ---------------------------------------------------------------------------
# Anomaly Detection
# ---------------------------------------------------------------------------


class AnomalyDetectRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    camera_node_id: str = Field(..., description="Camera node identifier")
    detections: list[dict] = Field(default_factory=list, description="YOLO detections for the frame")
    road_result: dict | None = Field(default=None, description="Road segmentation result")
    depth_stats: dict | None = Field(default=None, description="Depth statistics")
    bounding_box: dict | None = Field(default=None, description="Scene bounding box")


class AnomalyEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Anomaly event ID")
    camera_node_id: str = Field(..., description="Camera node identifier")
    frame_timestamp: datetime = Field(..., description="Frame timestamp")
    anomaly_score: float = Field(..., description="Anomaly score (higher = more anomalous)")
    anomaly_type: str = Field(..., description="Anomaly category")
    description: str | None = Field(default=None, description="Natural language description")
    embedding_distance: float | None = Field(default=None, description="Distance from baseline")
    bounding_box: dict | None = Field(default=None, description="Bounding box of anomaly")
    is_confirmed: bool = Field(..., description="Whether anomaly is confirmed")
    resolved: bool = Field(..., description="Whether anomaly has been resolved")
    resolution_note: str | None = Field(default=None, description="Resolution note")
    feedback_for_labeling: bool = Field(..., description="Flagged for human review")
    created_at: datetime = Field(..., description="Record creation time")


class AnomalyListResponse(PaginatedResponse[AnomalyEventResponse]):
    model_config = ConfigDict(from_attributes=True)


class AnomalyResolveRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resolution_note: str = Field(..., min_length=1, description="Resolution description")


class AnomalyResolveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Anomaly event ID")
    resolved: bool = Field(..., description="Whether resolved")
    resolution_note: str | None = Field(default=None, description="Resolution note")


class SendToLabelingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Anomaly event ID")
    is_confirmed: bool = Field(..., description="Confirmed for labeling")
    feedback_for_labeling: bool = Field(..., description="Queued for human review")


# ---------------------------------------------------------------------------
# Scene Reconstruction
# ---------------------------------------------------------------------------


class Detection3D(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    track_id: int | None = Field(default=None, description="Track ID")
    class_name: str = Field(..., description="Object class")
    confidence: float = Field(default=0.0, description="Detection confidence")
    bbox: list[float] = Field(default_factory=list, description="2D bounding box [x,y,w,h]")
    centroid: dict = Field(default_factory=dict, description="Centroid {x,y}")


class DepthMapInput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    depth_values: list[float] = Field(default_factory=list, description="Flattened depth values")
    width: int = Field(default=640, description="Depth map width")
    height: int = Field(default=480, description="Depth map height")
    focal_length: float | None = Field(default=None, description="Camera focal length")


class ReconstructionCreateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    camera_node_id: str = Field(..., description="Camera node identifier")
    detections: list[Detection3D] = Field(default_factory=list, description="3D-capable detections")
    depth_map: DepthMapInput = Field(default_factory=DepthMapInput, description="Depth map data")
    road_result: dict = Field(default_factory=dict, description="Road segmentation result")


class SceneBounds(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float


class ChangeEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str = Field(..., description="Change event type")
    description: str = Field(..., description="Human-readable description")
    timestamp: str | None = Field(default=None, description="ISO timestamp")


class ReconstructionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Reconstruction ID")
    camera_node_id: str = Field(..., description="Camera node identifier")
    timestamp: datetime = Field(..., description="Reconstruction timestamp")
    num_gaussians: int = Field(..., description="Number of Gaussians")
    num_keyframes: int = Field(..., description="Number of keyframes")
    scene_bounds: SceneBounds = Field(..., description="Scene bounding volume")
    dominant_classes: list[dict] | None = Field(default=None, description="Dominant object classes")
    static_objects: list[dict] | None = Field(default=None, description="Static objects")
    dynamic_objects: list[dict] | None = Field(default=None, description="Dynamic objects")
    change_events: list[ChangeEvent] | None = Field(default=None, description="Detected changes")
    reconstruction_quality: float = Field(..., description="Quality score 0-1")
    created_at: datetime = Field(..., description="Record creation time")


class ReconstructionListResponse(PaginatedResponse[ReconstructionResponse]):
    model_config = ConfigDict(from_attributes=True)


class SpatialQueryRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    camera_node_id: str = Field(..., description="Camera node identifier")
    query_type: str = Field(
        ...,
        description="Spatial query type: objects_near_road, parking_areas, vegetation_growth, sightline_blockage",
    )
    params: dict = Field(default_factory=dict, description="Query parameters")


class SpatialQueryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    query_type: str = Field(..., description="Query type executed")
    results: list[dict] = Field(default_factory=list, description="Query results")
    trend: str | None = Field(default=None, description="Trend (for vegetation_growth)")
    history: list[dict] | None = Field(default=None, description="Historical data")
    blocked_objects: list[dict] | None = Field(default=None, description="Blocked sightline objects")
    message: str | None = Field(default=None, description="Status message")


class SceneSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    camera_node_id: str = Field(..., description="Camera node identifier")
    has_reconstruction: bool = Field(..., description="Whether a reconstruction exists")
    reconstruction_id: str | None = Field(default=None, description="Latest reconstruction ID")
    timestamp: str | None = Field(default=None, description="Latest reconstruction timestamp")
    static_count: int = Field(..., description="Number of static objects")
    dynamic_count: int = Field(..., description="Number of dynamic objects")
    total_objects: int = Field(default=0, description="Total objects")
    dominant_classes: list[dict] = Field(default_factory=list, description="Dominant classes")
    recent_changes: list[dict] = Field(default_factory=list, description="Recent change events")
    scene_bounds: dict | None = Field(default=None, description="Scene bounding volume")
    reconstruction_quality: float = Field(default=0.0, description="Quality score")
    total_snapshots: int = Field(default=0, description="Total reconstruction snapshots")
