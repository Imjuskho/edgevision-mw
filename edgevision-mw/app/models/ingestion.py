from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.models.enums import BatchStatus
from app.models.mixins import StorageKeyMixin


class IngestionBatch(StorageKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_batches"

    batch_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    node_id: Mapped[UUID] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    hub_id: Mapped[str] = mapped_column(String(20), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    node_signature: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    compression_codec: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[BatchStatus] = mapped_column(String(20), nullable=False, default=BatchStatus.PENDING)
    validation_errors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quality_scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
