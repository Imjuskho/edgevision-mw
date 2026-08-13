from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class AgriAnnotation(TimestampMixin, Base):
    __tablename__ = "agri_annotations"

    annotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("annotations.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    crop_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="maize"
    )
    health_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="healthy"
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
