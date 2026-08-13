from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ModelType, TrainingStatus
from app.schemas.common import PaginatedResponse


class TrainingStartRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str = Field(..., description="Dataset identifier")
    model_name: str = Field(..., description="Model name")
    model_type: ModelType = Field(..., description="Training model type")
    epochs: int = Field(default=50, ge=1, description="Number of training epochs")
    batch_size: int = Field(default=16, ge=1, description="Batch size")
    learning_rate: float = Field(default=0.001, gt=0, description="Learning rate")
    config_json: dict[str, object] = Field(default_factory=dict, description="Optional training config")


class TrainingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    dataset_id: str
    model_name: str
    model_type: ModelType
    status: TrainingStatus
    progress_pct: int
    accuracy: float | None
    epochs: int
    batch_size: int
    learning_rate: float
    config_json: dict[str, object]
    artifact_path: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TrainingListResponse(PaginatedResponse[TrainingJobResponse]):
    model_config = ConfigDict(from_attributes=True)
