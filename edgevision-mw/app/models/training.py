from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.models.enums import ModelType, TrainingStatus
from app.models.mixins import StorageKeyMixin


class TrainingJob(StorageKeyMixin, TimestampMixin, Base):
    __tablename__ = "training_jobs"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    model_type: Mapped[ModelType] = mapped_column(Enum(ModelType, native_enum=False), nullable=False)
    status: Mapped[TrainingStatus] = mapped_column(Enum(TrainingStatus, native_enum=False), nullable=False, default=TrainingStatus.PENDING)
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    epochs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    learning_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
