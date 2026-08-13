from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.models.enums import ConsentStatus
from app.models.mixins import StorageKeyMixin


class AnnotationSession(TimestampMixin, Base):
    __tablename__ = "annotation_sessions"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    annotations_created: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )


class AnnotationAction(TimestampMixin, Base):
    __tablename__ = "annotation_actions"

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("annotation_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    annotation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("annotations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    image_index: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ImageEmbedding(StorageKeyMixin, TimestampMixin, Base):
    __tablename__ = "image_embeddings"
    __table_args__ = (
        Index("ix_image_embeddings_path_model", "image_path", "model_name"),
    )

    image_path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    annotation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("annotations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding: Mapped[list | None] = mapped_column(
        Vector(512), nullable=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )


class DuplicateGroup(TimestampMixin, Base):
    __tablename__ = "duplicate_groups"
    __table_args__ = (
        Index("ix_duplicate_groups_status", "status"),
        Index("ix_duplicate_groups_dataset_status", "dataset_id", "status"),
    )

    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    detection_method: Mapped[str] = mapped_column(String(50), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    resolution_action: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )


class DuplicateGroupMember(TimestampMixin, Base):
    __tablename__ = "duplicate_group_members"

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("duplicate_groups.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    annotation_id: Mapped[UUID] = mapped_column(
        ForeignKey("annotations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_kept: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class DatasetHealthSnapshot(TimestampMixin, Base):
    __tablename__ = "dataset_health_snapshots"
    __table_args__ = (
        Index("ix_dataset_health_snapshots_time", "created_at"),
    )

    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    uniqueness_score: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_score: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage_score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    action_items: Mapped[list | None] = mapped_column(JSONB, nullable=True)


class ExportJob(StorageKeyMixin, TimestampMixin, Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        Index("ix_export_jobs_status", "status"),
        Index("ix_export_jobs_user_status", "user_id", "status"),
    )

    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    split_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    augmentation_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    include_images: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    include_annotations: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    include_metadata: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    image_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    download_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConsentZone(TimestampMixin, Base):
    __tablename__ = "consent_zones"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry: Mapped[dict] = mapped_column(JSONB, nullable=False)
    consent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("consent_ledger.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[ConsentStatus] = mapped_column(
        String(20), nullable=False, default=ConsentStatus.ACTIVE
    )
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
