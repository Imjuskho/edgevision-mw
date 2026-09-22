from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.road_taxonomy import ROAD_SURFACE_TYPES


class InstanceMask(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    class_id: int = Field(..., ge=0, description="Road surface class ID (0-6)")
    class_name: str = Field(..., min_length=1, description="Road surface class name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence score")
    bbox: list[float] = Field(..., min_length=4, max_length=4, description="Normalized bbox [x, y, w, h]")
    mask_rle: str = Field(..., description="RLE-encoded binary mask")
    polygon: list[list[float]] | None = Field(default=None, description="Simplified polygon [[x,y], ...] normalized")

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: list[float]) -> list[float]:
        if not all(0.0 <= x <= 1.0 for x in v):
            raise ValueError("all bbox values must be in range [0.0, 1.0]")
        return v


class RoadSegmentationRequest(BaseModel):
    image_id: UUID = Field(..., description="Annotation/image ID to segment")
    conf_threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence threshold")
    iou_threshold: float = Field(default=0.45, ge=0.0, le=1.0, description="IoU NMS threshold")
    return_polygons: bool = Field(default=True, description="Whether to return polygon simplifications")


class RoadSegmentationResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    image_id: UUID = Field(..., description="Processed image ID")
    instances: list[InstanceMask] = Field(default_factory=list, description="Detected road surface instances")
    surface_type: str = Field(..., description="Overall surface classification (paved/unpaved/mixed)")
    model_version: str = Field(..., description="Model version used")
    latency_ms: float = Field(..., description="Inference time in milliseconds")


class RoadSegmentationBatchRequest(BaseModel):
    dataset_id: str | None = Field(default=None, description="Dataset slug or UUID — resolves target frames")
    image_ids: list[UUID] | None = Field(
        default=None,
        max_length=1000,
        description="Explicit annotation IDs (optional when dataset_id is set)",
    )
    scope: Literal["remaining", "all"] = Field(
        default="remaining",
        description="remaining = unannotated only; all = every frame (still skips reviewed unless force)",
    )
    force: bool = Field(default=False, description="Re-run even when auto labels exist")
    conf_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    iou_threshold: float = Field(default=0.45, ge=0.0, le=1.0)


class RoadSegmentationBatchResponse(BaseModel):
    job_id: UUID = Field(..., description="Async job ID for tracking")
    total_images: int = Field(..., description="Number of images queued")
    skipped: int = Field(default=0, description="Frames skipped (already annotated)")


class RoadAnnotationUpdate(BaseModel):
    instances: list[InstanceMask] | None = None
    surface_type: str | None = None
    reviewed: bool | None = None

    @field_validator("surface_type")
    @classmethod
    def validate_surface_type(cls, v: str | None) -> str | None:
        if v is not None and v not in ROAD_SURFACE_TYPES:
            raise ValueError(f"surface_type must be one of {ROAD_SURFACE_TYPES}")
        return v


class RoadAnnotationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    annotation_id: UUID
    surface_type: str
    instances: list[InstanceMask]
    model_version: str
    auto_generated: bool
    reviewed: bool
    created_at: str
    updated_at: str


class RoadClassesResponse(BaseModel):
    classes: list[dict] = Field(..., description="Road surface taxonomy classes")
    version: str = Field(..., description="Taxonomy version")


class RoadConditionReport(BaseModel):
    dataset_id: UUID = Field(..., description="Analyzed dataset ID")
    total_images: int = Field(..., ge=0, description="Total images analyzed")
    surface_breakdown: dict[str, float] = Field(..., description="Surface type percentage breakdown")
    pothole_count: int = Field(..., ge=0, description="Total potholes detected")
    pothole_density_per_km2: float = Field(default=0.0, ge=0.0, description="Estimated pothole density")
    crack_severity: Literal["low", "medium", "high"] = Field(..., description="Crack severity assessment")
    condition_score: float = Field(..., ge=0.0, le=1.0, description="Overall road condition score (0=worst, 1=best)")
    recommended_action: str | None = Field(default=None, description="Recommended maintenance action")


class SignDetectionResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bbox: list[int] = Field(..., min_length=4, max_length=4, description="Pixel bbox [x1, y1, x2, y2]")
    color_class: str = Field(
        ..., description="Sign color class (red_sign, blue_sign, green_sign, yellow_sign, white_sign)"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence")
    ocr_text: str = Field(default="", description="OCR-extracted text from sign")
    ocr_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="OCR confidence")


class SignDetectionResponse(BaseModel):
    image_id: UUID = Field(..., description="Processed image ID")
    signs: list[SignDetectionResult] = Field(default_factory=list, description="Detected signs")
    text_regions: list[dict] = Field(default_factory=list, description="General text regions detected")
    latency_ms: float = Field(..., description="Processing time in milliseconds")


class PoseDetectionResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    keypoints: list[dict] = Field(..., description="Keypoints with name, x, y, confidence")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Mean keypoint confidence")


class PoseDetectionResponse(BaseModel):
    image_id: UUID = Field(..., description="Processed image ID")
    poses: list[PoseDetectionResult] = Field(default_factory=list, description="Detected poses")
    latency_ms: float = Field(..., description="Processing time in milliseconds")


class ColorExtractionResponse(BaseModel):
    image_id: UUID = Field(..., description="Processed image ID")
    dominant_colors: list[dict] = Field(default_factory=list, description="Dominant colors with BGR and percentage")
    color_classes: dict[str, float] = Field(default_factory=dict, description="HSV color class distribution")
    latency_ms: float = Field(..., description="Processing time in milliseconds")


class TrackingRequest(BaseModel):
    image_ids: list[UUID] = Field(..., min_length=2, max_length=200, description="Sequential image IDs to track across")
    conf_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class TrackingResponse(BaseModel):
    tracks: list[dict] = Field(default_factory=list, description="Tracked objects across frames")
    total_tracks: int = Field(..., ge=0, description="Number of tracks found")


class RoadAnalyzeRequest(BaseModel):
    dataset_id: UUID = Field(..., description="Dataset ID to analyze")
    conf_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class RoadSceneRequest(RoadSegmentationRequest):
    camera_height_m: float = Field(default=1.5, gt=0.0, description="Camera mounting height above ground (meters)")
    focal_length_px: float = Field(default=700.0, gt=0.0, description="Vertical focal length (pixels)")
    horizon_fraction: float = Field(
        default=0.35, gt=0.0, lt=1.0, description="Horizon row as a fraction of image height"
    )


class RoadSceneHazard(BaseModel):
    class_id: int = Field(..., ge=0, description="Hazard class ID (pothole=1, crack=2)")
    class_name: str = Field(..., min_length=1, description="Hazard class name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence")
    bbox: list[float] = Field(..., min_length=4, max_length=4, description="Normalized bbox [x, y, w, h]")
    contact_row: int = Field(..., ge=0, description="Bottom (contact) row of the hazard in pixels")
    distance_m: float | None = Field(default=None, description="Metric distance to hazard (meters)")
    distance_quality: str = Field(default="unavailable", description="Distance estimation quality tag")
    mask_quality: str = Field(default="none", description="Mask source for the hazard (rle/bbox_fill)")


class RoadSidewalkRegion(BaseModel):
    side: str = Field(..., description="Side of the frame (left/right)")
    coverage: float = Field(..., ge=0.0, le=1.0, description="Non-drivable coverage of the band")
    method: str = Field(default="geometric_boundary", description="Detection method")


class RoadScene(BaseModel):
    has_road: bool = Field(..., description="Whether a drivable surface was detected")
    drivable_ratio: float = Field(..., ge=0.0, le=1.0, description="Drivable pixel share of the lower frame")
    drivable_class_ids: list[int] = Field(default_factory=list, description="Drivable road surface class IDs")
    hazards: list[RoadSceneHazard] = Field(default_factory=list, description="Non-drivable hazards")
    sidewalk_present: bool = Field(default=False, description="Sidewalk detected via geometric heuristics")
    sidewalk_regions: list[RoadSidewalkRegion] = Field(default_factory=list, description="Sidewalk bands")
    curb_present: bool = Field(default=False, description="Curb detected via geometric heuristics")
    curb_method: str = Field(default="not_detected", description="Curb detection method")
    road_continuous_fraction: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Share of center columns where the road reaches the frame bottom"
    )
    road_edge_distance_m: float | None = Field(
        default=None, description="Forward free-space to the road edge (meters)"
    )
    road_edge_quality: str = Field(default="no_drivable_region", description="Road-edge distance quality tag")
    mask_quality: str = Field(default="none", description="Best available mask source (rle/bbox_fill/none)")
    method: str = Field(default="instance_fusion", description="Analysis method")


class RoadSceneResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    image_id: UUID = Field(..., description="Processed image ID")
    scene: RoadScene = Field(..., description="Semantic road scene analysis")
    surface_type: str = Field(..., description="Overall surface classification (paved/unpaved/mixed)")
    depth_quality: str = Field(..., description="Metric depth quality tag")
    model_version: str = Field(..., description="Model version used")
    latency_ms: float = Field(..., description="Total processing time in milliseconds")
