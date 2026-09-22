# Audit logs are append-only. The updated_at column has been removed.
# Enforcement is via a PostgreSQL BEFORE UPDATE trigger
# (`block_audit_logs_update` in migration 0002_append_only_enforcement),
# not a check constraint. The application layer must only INSERT new rows,
# never UPDATE or DELETE existing ones.

from uuid import UUID

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import AppendOnlyMixin, Base


class AuditLog(AppendOnlyMixin, Base):
    __tablename__ = "audit_logs"

    event_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
