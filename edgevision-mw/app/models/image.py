from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.core.tenant import TenantScoped
from app.models.mixins import StorageKeyMixin


class ImageRecord(StorageKeyMixin, TimestampMixin, TenantScoped, Base):
    __tablename__ = "image_records"

    storage_key: Mapped[str] = mapped_column(
        String(500), nullable=False, index=True
    )
    thumbnail_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    filename: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    content_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    width: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    height: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="file"
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    exif: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    dataset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    uploaded_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
