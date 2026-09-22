from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base, TimestampMixin
from app.core.json_utils import json_safe
from app.models.enums import AnnotationStatus
from app.models.mixins import StorageKeyMixin


class Annotation(StorageKeyMixin, TimestampMixin, Base):
    __tablename__ = "annotations"

    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("ingestion_batches.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    image_index: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_path: Mapped[str] = mapped_column(String(500), nullable=False)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    detected_objects: Mapped[dict] = mapped_column(JSONB, nullable=False)
    auto_labels: Mapped[dict] = mapped_column(JSONB, nullable=False)
    human_labels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    qa_labels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[AnnotationStatus] = mapped_column(String(20), nullable=False, default=AnnotationStatus.PENDING)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    iaa_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    annotator_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    qa_reviewer_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_certified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dataset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)

    @validates("detected_objects", "auto_labels", "human_labels", "qa_labels")
    def _sanitize_jsonb_fields(self, _key: str, value: dict | None) -> dict | None:
        if value is None:
            return None
        return json_safe(value)


class AnnotationAssignment(TimestampMixin, Base):
    __tablename__ = "annotation_assignments"

    annotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("annotations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    annotator_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
