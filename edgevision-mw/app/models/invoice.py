from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"

    buyer_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    subscription_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subscription_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    node_count: Mapped[int] = mapped_column(nullable=False)
    unit_price_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    subtotal_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    subtotal_mwk: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    tax_mwk: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_mwk: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    line_items: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
