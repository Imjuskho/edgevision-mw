from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FLRoundCreate(BaseModel):
    model_type: str = Field(..., description="Model type to federate")
    target_contributors: int = Field(default=3, description="Min contributors before aggregation")
    noise_multiplier: float = Field(default=0.1, description="Differential privacy noise")


class FLWeightUpdateSubmit(BaseModel):
    round_id: str | None = Field(default=None, description="Round ID (auto-assigns to latest COLLECTING if None)")
    node_id: str = Field(..., description="Node identifier")
    num_samples: int = Field(default=0)
    local_loss: float | None = None
    local_accuracy: float | None = None
    artifact_path: str | None = None


class FLRoundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    model_type: str
    status: str
    num_contributors: int
    target_contributors: int
    global_loss: float | None = None
    global_accuracy: float | None = None
    aggregated_model_version: str | None = None


class FLWeightUpdateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    round_id: str
    node_id: str
    num_samples: int
    status: str
    local_loss: float | None = None
    local_accuracy: float | None = None


class FLRoundListResponse(BaseModel):
    items: list[FLRoundResponse]
    total: int


class FLOverviewResponse(BaseModel):
    total_rounds: int
    active_rounds: int
    total_contributors: int
