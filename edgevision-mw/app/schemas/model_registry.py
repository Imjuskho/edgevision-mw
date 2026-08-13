from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ModelFormat, ModelType
from app.schemas.common import PaginatedResponse


class DeployModelRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    training_job_id: UUID = Field(
        ..., description="Completed training job whose artifact should be promoted to the model registry"
    )
    notes: str | None = Field(default=None, max_length=500, description="Optional deployment notes")


class DeployedModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    training_job_id: UUID
    model_name: str
    model_type: ModelType
    version: str
    dataset_id: str
    artifact_path: str
    format: ModelFormat = ModelFormat.ULTRALYTICS
    accuracy: float | None
    is_active: bool
    deployed_by: UUID | None
    deployed_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class DeployedModelListResponse(PaginatedResponse[DeployedModelResponse]):
    model_config = ConfigDict(from_attributes=True)
