from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import AppendOnlyMixin, Base, TimestampMixin
from app.models.enums import DatasetStatus, LicenseType


class Dataset(TimestampMixin, Base):
    __tablename__ = "datasets"

    dataset_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[DatasetStatus] = mapped_column(String(20), nullable=False, default=DatasetStatus.BUILDING)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    classes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    annotations_per_image: Mapped[float] = mapped_column(Float, nullable=False)
    image_width: Mapped[int] = mapped_column(Integer, nullable=False)
    image_height: Mapped[int] = mapped_column(Integer, nullable=False)
    geographic_coverage: Mapped[dict] = mapped_column(JSONB, nullable=False)
    demographic_report: Mapped[dict] = mapped_column(JSONB, nullable=False)
    consent_coverage_pct: Mapped[float] = mapped_column(Float, nullable=False)
    pii_scrub_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    iaa_score: Mapped[float] = mapped_column(Float, nullable=False)
    formats: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    buyer_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    license_type: Mapped[LicenseType] = mapped_column(String(20), nullable=False)
    buyer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


class DatasetSubjectMembership(AppendOnlyMixin, Base):
    __tablename__ = "dataset_subject_memberships"

    dataset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("datasets.dataset_id", ondelete="CASCADE"), index=True
    )
    subject_hash: Mapped[str] = mapped_column(String(128), index=True)
    first_seen_batch_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("ingestion_batches.batch_id"), nullable=True
    )
    annotation_count: Mapped[int] = mapped_column(Integer, default=1)
