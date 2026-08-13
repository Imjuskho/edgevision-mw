from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExperimentEventIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    experiment_id: str = Field(..., min_length=1, max_length=100)
    variant_id: str = Field(..., min_length=1, max_length=100)
    user_id: str | None = Field(None, description="Optional user UUID")
    event_type: Literal["exposed", "converted", "dismissed"]
    metadata: dict | None = Field(None)
    timestamp: str | None = Field(None, description="ISO 8601 event timestamp")

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str | None) -> str | None:
        if v is not None:
            UUID(v)
        return v


class ExperimentEventBatch(BaseModel):
    events: list[ExperimentEventIn] = Field(..., min_length=1, max_length=500)


class ExperimentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    experiment_id: str
    variant_id: str
    event_type: str
    user_id: UUID | None
    metadata: dict | None
    occurred_at: datetime
