from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class Quote(TimestampMixin, Base):
    __tablename__ = "quotes"

    buyer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    dataset_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    base_price_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    exclusivity_multiplier: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    geography_premium: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    total_price_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    license_type: Mapped[str] = mapped_column(String(20), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
