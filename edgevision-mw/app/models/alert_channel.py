"""Alert delivery channels for perception-event push alerting."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin

WEBHOOK = "webhook"
SMS = "sms"
PUSH = "push"
VALID_CHANNEL_TYPES = frozenset({WEBHOOK, SMS, PUSH})


class AlertChannel(TimestampMixin, Base):
    """A configured outbound delivery channel for perception alerts."""

    __tablename__ = "alert_channels"
    __table_args__ = (
        Index("ix_alert_channels_tenant_enabled", "tenant_id", "enabled"),
    )

    channel_type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
