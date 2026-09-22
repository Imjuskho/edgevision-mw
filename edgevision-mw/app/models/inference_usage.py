from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.models.enums import ModelType


class InferenceUsage(TimestampMixin, Base):
    __tablename__ = "inference_usage"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    model_type: Mapped[ModelType] = mapped_column(Enum(ModelType, native_enum=False), nullable=False)
    input_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0.000000"))
    billed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
