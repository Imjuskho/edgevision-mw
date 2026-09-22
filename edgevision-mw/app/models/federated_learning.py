from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class FLSyncRound(TimestampMixin, Base):
    __tablename__ = "fl_sync_rounds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    model_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    base_model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    aggregated_model_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="COLLECTING")
    num_contributors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_contributors: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    aggregation_method: Mapped[str] = mapped_column(String(50), nullable=False, default="fedavg")
    noise_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)
    learning_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.01)
    global_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    global_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)


class FLWeightUpdate(TimestampMixin, Base):
    __tablename__ = "fl_weight_updates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    round_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fl_sync_rounds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    num_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    local_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    local_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    validation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_outlier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FLModelDistribution(TimestampMixin, Base):
    __tablename__ = "fl_model_distributions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    round_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fl_sync_rounds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bandwidth_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    node_validation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
