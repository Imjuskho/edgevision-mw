from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.models.enums import ModelFormat, ModelType
from app.models.mixins import StorageKeyMixin


class DeployedModel(StorageKeyMixin, TimestampMixin, Base):
    """A model registry entry — a trained artifact promoted from a completed
    TrainingJob and available for inference. Exactly one DeployedModel per
    model_type may have is_active=True at a time (enforced by a partial
    unique index; see alembic/versions/0013_add_deployed_models.py).
    """

    __tablename__ = "deployed_models"

    training_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    model_type: Mapped[ModelType] = mapped_column(
        Enum(ModelType, native_enum=False), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(100), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)
    format: Mapped[ModelFormat] = mapped_column(
        String(20), nullable=False, default=ModelFormat.ULTRALYTICS
    )
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deployed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
