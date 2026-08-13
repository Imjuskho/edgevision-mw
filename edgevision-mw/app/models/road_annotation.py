from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base, TimestampMixin
from app.core.json_utils import json_safe


class RoadAnnotation(TimestampMixin, Base):
    __tablename__ = "road_annotations"

    annotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("annotations.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    surface_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unpaved"
    )
    instances: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    model_version: Mapped[str] = mapped_column(
        String(50), nullable=False, default="yolov8n-seg-v1"
    )
    auto_generated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    reviewed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    @validates("instances")
    def _sanitize_instances(self, key: str, value: Any) -> Any:
        if value is None:
            return value
        return json_safe(value)
