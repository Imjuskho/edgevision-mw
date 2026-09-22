from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventRuleIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rule_id: str = Field(..., description="Stable rule identifier")
    rule_type: str = Field(..., description="dwell | presence | confidence_drop | distance")
    name: str = Field(..., description="Human-readable rule name")
    enabled: bool = True
    class_names: list[str] = Field(default_factory=list)
    taxonomy_labels: list[str] = Field(default_factory=list)
    dwell_seconds: float = 5.0
    min_confidence: float = 0.0
    confidence_drop_below: float = 0.3
    confidence_drop_from: float = 0.55
    distance_m_max: float | None = None
    time_of_day: list[str] | None = None
    cooldown_seconds: float = 30.0
    auto_save: bool = True
    pre_frames: int = 6
    post_frames: int = 4
    payload: dict[str, Any] = Field(default_factory=dict)


class EventRulesUpdate(BaseModel):
    rules: list[EventRuleIn] = Field(..., min_length=1, max_length=50)


class PerceptionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    rule_id: str
    rule_name: str
    track_id: int | None = None
    class_name: str | None = None
    taxonomy_label: str | None = None
    confidence: float
    bbox: list[float] | None = None
    started_at: datetime | None = None
    triggered_at: datetime
    duration_seconds: float | None = None
    clip_frames: int = 0
    clip_storage_keys: list[str] = Field(default_factory=list)
    auto_save: bool = False
    dataset_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class PerceptionEventPage(BaseModel):
    items: list[PerceptionEventOut]
    total: int
    limit: int
    offset: int
