from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.models.enums import ExportStatus, LicenseType


class Export(TimestampMixin, Base):
    __tablename__ = "exports"

    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    buyer_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    license_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    license_type: Mapped[LicenseType] = mapped_column(
        String(20), nullable=False
    )
    status: Mapped[ExportStatus] = mapped_column(
        String(20), nullable=False, default=ExportStatus.PENDING
    )
    price_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_ref: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    delivery_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    delivery_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    watermark_fingerprint: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    formats_delivered: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False
    )
    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    usage_rights: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ExportLog(TimestampMixin, Base):
    __tablename__ = "export_logs"

    export_id: Mapped[UUID] = mapped_column(
        ForeignKey("exports.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
