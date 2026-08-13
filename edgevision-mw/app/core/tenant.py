from __future__ import annotations

import contextvars
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

current_tenant_id: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "current_tenant_id", default=None
)


def set_current_tenant_id(tenant_id: UUID | None) -> None:
    current_tenant_id.set(tenant_id)


def get_current_tenant_id() -> UUID | None:
    return current_tenant_id.get()


class TenantScoped:
    """SQLAlchemy mixin that adds a tenant_id FK column for multi-tenant isolation.

    When attached to a model, every row is scoped to a tenant (User). The
    tenant_id defaults to the current tenant context var, which is set by
    middleware from the authenticated user.
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[UUID | None]:
        return mapped_column(
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        )

    @property
    def tenant_id_val(self) -> UUID | None:
        return getattr(self, "tenant_id", None)
