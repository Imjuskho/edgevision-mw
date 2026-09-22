from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class SyntheticGenerationJob(TimestampMixin, Base):
    __tablename__ = "synthetic_generation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False, default="conditional_diffusion")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    target_count: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    generated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    conditions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manifest_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    validation_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SyntheticFrame(TimestampMixin, Base):
    __tablename__ = "synthetic_frames"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("synthetic_generation_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    segmentation_mask_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    depth_map_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bounding_boxes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    class_labels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    weather_condition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    time_of_day: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lighting_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_realistic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    validation_score: Mapped[float | None] = mapped_column(Float, nullable=True)


class SyntheticValidation(TimestampMixin, Base):
    __tablename__ = "synthetic_validations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("synthetic_generation_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    validation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    real_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    synthetic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    difference: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
