from uuid import UUID

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class Heartbeat(TimestampMixin, Base):
    __tablename__ = "heartbeats"

    node_id: Mapped[UUID] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True, nullable=False)
    battery_voltage: Mapped[float] = mapped_column(Float, nullable=False)
    solar_input_watts: Mapped[float] = mapped_column(Float, nullable=False)
    cpu_temp_celsius: Mapped[float] = mapped_column(Float, nullable=False)
    gpu_utilization: Mapped[float] = mapped_column(Float, nullable=False)
    storage_used_gb: Mapped[float] = mapped_column(Float, nullable=False)
    storage_total_gb: Mapped[float] = mapped_column(Float, nullable=False)
    lte_rssi_dbm: Mapped[float] = mapped_column(Float, nullable=False)
    camera_status: Mapped[str] = mapped_column(String(20), nullable=False)
    clock_drift_ms: Mapped[float] = mapped_column(Float, nullable=False)
    events_captured: Mapped[int] = mapped_column(Integer, nullable=False)
    events_uploaded: Mapped[int] = mapped_column(Integer, nullable=False)
    bandwidth_mbps: Mapped[float] = mapped_column(Float, nullable=False)
    raw_diagnostics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
