from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class OperatorAccount(TimestampMixin, Base):
    __tablename__ = "operator_accounts"

    phone_number: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    village: Mapped[str | None] = mapped_column(String(200), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language_preference: Mapped[str] = mapped_column(String(5), nullable=False, default="ny")
    associated_node_id: Mapped[UUID] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"), index=True, nullable=True
    )
    stipend_balance_mwk: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    last_payout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class OperatorPayout(TimestampMixin, Base):
    __tablename__ = "operator_payouts"

    operator_id: Mapped[UUID] = mapped_column(
        ForeignKey("operator_accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount_mwk: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
