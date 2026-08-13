# Consent ledger is append-only at the database level.
# A PostgreSQL trigger (added via Alembic migration) blocks UPDATE and DELETE
# on this table. The application layer must never UPDATE or DELETE rows here.
# Consent withdrawal is recorded as a new row with status=WITHDRAWN.

from datetime import datetime

from sqlalchemy import DateTime, LargeBinary, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import AppendOnlyMixin, Base
from app.models.enums import ConsentStatus


class ConsentLedger(AppendOnlyMixin, Base):
    __tablename__ = "consent_ledger"

    subject_hash: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    tx_hash: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    purposes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False
    )
    media_types: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False
    )
    geography_restrictions: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False
    )
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expiry: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    guardian_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    signature_bytes: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )
    status: Mapped[ConsentStatus] = mapped_column(
        String(20), nullable=False, default=ConsentStatus.ACTIVE
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hard_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
