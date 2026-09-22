from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, LargeBinary, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.models.enums import NodeCategory, NodeStatus, PIIMode


class Node(TimestampMixin, Base):
    __tablename__ = "nodes"

    node_id: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    district: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[NodeCategory] = mapped_column(String(20), nullable=False)
    hardware_profile: Mapped[dict] = mapped_column(JSONB, nullable=False)
    network_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    capture_schedule: Mapped[str] = mapped_column(String(50), nullable=False)
    interest_classes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    pii_mode: Mapped[PIIMode] = mapped_column(String(20), nullable=False)
    firmware_version: Mapped[str] = mapped_column(String(20), nullable=False)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[NodeStatus] = mapped_column(String(20), nullable=False, default=NodeStatus.ONLINE)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
