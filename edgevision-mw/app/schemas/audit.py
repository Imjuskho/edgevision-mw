from __future__ import annotations

from pydantic import BaseModel, Field


class AuditLogItem(BaseModel):
    id: str
    event_type: str
    severity: str
    actor_id: str | None = None
    actor_email: str | None = None
    actor_type: str
    resource_type: str
    resource_id: str | None = None
    details: dict | None = None
    ip_address: str | None = None
    created_at: str | None = None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
    limit: int
    offset: int


class AuditLogQuery(BaseModel):
    event_type: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
