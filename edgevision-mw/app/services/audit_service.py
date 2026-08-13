from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.buyer import User


async def write_audit(
    db: AsyncSession,
    *,
    event_type: str,
    severity: str,
    actor_id: UUID | None,
    actor_type: str,
    resource_type: str,
    resource_id: UUID | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        AuditLog(
            event_type=event_type,
            severity=severity,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
        )
    )


async def list_audit_logs(
    db: AsyncSession,
    *,
    event_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    filters = []
    if event_type:
        filters.append(AuditLog.event_type == event_type)

    count_stmt = select(func.count()).select_from(AuditLog)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = select(AuditLog)
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()

    actor_ids = {r.actor_id for r in rows if r.actor_id}
    actors: dict[UUID, str] = {}
    if actor_ids:
        user_rows = (await db.execute(select(User).where(User.id.in_(actor_ids)))).scalars().all()
        actors = {u.id: u.email for u in user_rows}

    items = [
        {
            "id": str(r.id),
            "event_type": r.event_type,
            "severity": r.severity,
            "actor_id": str(r.actor_id) if r.actor_id else None,
            "actor_email": actors.get(r.actor_id) if r.actor_id else None,
            "actor_type": r.actor_type,
            "resource_type": r.resource_type,
            "resource_id": str(r.resource_id) if r.resource_id else None,
            "details": r.details,
            "ip_address": r.ip_address,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return items, total
