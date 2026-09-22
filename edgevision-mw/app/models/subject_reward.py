from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class SubjectReward(TimestampMixin, Base):
    __tablename__ = "subject_rewards"

    subject_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    total_airtime_mwk: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    pending_airtime_mwk: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    last_payout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payout_method: Mapped[str] = mapped_column(String(20), nullable=False, default="airtime")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
