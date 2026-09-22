from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class PerceptionEvent(TimestampMixin, Base):
    """A rule-triggered perception event from live annotation streams."""

    __tablename__ = "perception_events"
    __table_args__ = (
        Index("ix_perception_events_type_created", "event_type", "created_at"),
        Index("ix_perception_events_track", "track_id", "created_at"),
    )

    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(200), nullable=False)
    track_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    class_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    taxonomy_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bbox: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    clip_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clip_storage_keys: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    auto_save: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dataset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
