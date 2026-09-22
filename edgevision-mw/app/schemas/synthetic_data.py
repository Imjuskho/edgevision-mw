from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SyntheticJobCreate(BaseModel):
    dataset_id: str = Field(..., description="Dataset ID to base generation on")
    target_count: int = Field(default=100, ge=1, le=10000)
    config: dict | None = None


class SyntheticJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    dataset_id: str
    status: str
    target_count: int
    generated_count: int
    validation_score: float | None = None


class SyntheticJobListResponse(BaseModel):
    items: list[SyntheticJobResponse]
    total: int


class SyntheticFrameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    job_id: str
    frame_index: int
    image_path: str
    weather_condition: str | None = None
    time_of_day: str | None = None
    lighting_score: float | None = None
    is_realistic: bool = False


class SyntheticValidationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    job_id: str
    validation_type: str
    passed: bool
    real_score: float | None = None
    synthetic_score: float | None = None
