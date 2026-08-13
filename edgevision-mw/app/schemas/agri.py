from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.agri_taxonomy import CROP_TYPES, HEALTH_STATUS_TYPES


class InstanceMask(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    class_id: int = Field(..., ge=0, description="Class ID (crop or health)")
    class_name: str = Field(..., min_length=1, description="Class name")
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


class AgriSegmentationRequest(BaseModel):
    image_id: UUID = Field(..., description="Annotation/image ID to segment")
    conf_threshold: float = Field(default=0.35, ge=0.0, le=1.0, description="Confidence threshold")
    iou_threshold: float = Field(default=0.45, ge=0.0, le=1.0, description="IoU NMS threshold")
    return_polygons: bool = Field(default=True, description="Whether to return polygon simplifications")


class AgriSegmentationResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    image_id: UUID = Field(..., description="Processed image ID")
    instances: list[InstanceMask] = Field(default_factory=list, description="Detected crop/health instances")
    crop_type: str = Field(..., description="Dominant crop type classification")
    health_status: str = Field(..., description="Dominant health status classification")
    model_version: str = Field(..., description="Model version used")
    latency_ms: float = Field(..., description="Inference time in milliseconds")


class AgriSegmentationBatchRequest(BaseModel):
    image_ids: list[UUID] = Field(..., min_length=1, max_length=50, description="Image IDs to segment")
    conf_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    iou_threshold: float = Field(default=0.45, ge=0.0, le=1.0)


class AgriSegmentationBatchResponse(BaseModel):
    job_id: UUID = Field(..., description="Async job ID for tracking")
    total_images: int = Field(..., description="Number of images queued")


class AgriAnnotationUpdate(BaseModel):
    instances: list[InstanceMask] | None = None
    crop_type: str | None = None
    health_status: str | None = None
    reviewed: bool | None = None

    @field_validator("crop_type")
    @classmethod
    def validate_crop_type(cls, v: str | None) -> str | None:
        if v is not None and v not in CROP_TYPES:
            raise ValueError(f"crop_type must be one of {CROP_TYPES}")
        return v

    @field_validator("health_status")
    @classmethod
    def validate_health_status(cls, v: str | None) -> str | None:
        if v is not None and v not in HEALTH_STATUS_TYPES:
            raise ValueError(f"health_status must be one of {HEALTH_STATUS_TYPES}")
        return v


class AgriAnnotationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    annotation_id: UUID
    crop_type: str
    health_status: str
    instances: list[InstanceMask]
    model_version: str
    auto_generated: bool
    reviewed: bool
    created_at: str
    updated_at: str


class AgriClassesResponse(BaseModel):
    classes: list[dict] = Field(..., description="Agri taxonomy classes (crops + health)")
    version: str = Field(..., description="Taxonomy version")


class AgriAnalysisReport(BaseModel):
    dataset_id: UUID = Field(..., description="Analyzed dataset ID")
    total_images: int = Field(..., ge=0, description="Total images analyzed")
    crop_breakdown: dict[str, float] = Field(..., description="Crop type percentage breakdown")
    health_breakdown: dict[str, float] = Field(..., description="Health condition percentage breakdown")
    health_score: float = Field(..., ge=0.0, le=1.0, description="Overall crop health score (0=worst, 1=best)")
    weed_pressure: Literal["low", "medium", "high"] = Field(..., description="Weed infestation pressure level")
    pest_risk: Literal["low", "medium", "high"] = Field(..., description="Pest infestation risk level")
    recommended_action: str | None = Field(default=None, description="Recommended agronomic action")


class AgriAnalyzeRequest(BaseModel):
    dataset_id: UUID = Field(..., description="Dataset ID to analyze")
    conf_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
