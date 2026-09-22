"""Perception event persistence and rules configuration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.events import EventRule, default_rules, rules_from_dicts
from app.core.logging import get_logger
from app.models.perception_event import PerceptionEvent
from app.models.workspace_settings import WORKSPACE_SETTINGS_KEY, WorkspaceSettings
from app.services.audit_service import write_audit

logger = get_logger("edgevision.perception_events")

EVENT_RULES_SETTINGS_KEY = "perception_event_rules"


async def _get_workspace_row(db: AsyncSession) -> WorkspaceSettings | None:
    result = await db.execute(
        select(WorkspaceSettings).where(WorkspaceSettings.singleton_key == WORKSPACE_SETTINGS_KEY)
    )
    return result.scalar_one_or_none()


async def get_event_rules(db: AsyncSession) -> list[dict]:
    """Return the effective rules config (workspace overrides merged over defaults)."""
    row = await _get_workspace_row(db)
    raw_rules: list[dict] | None = None
    if row and row.operational_json:
        raw_rules = row.operational_json.get(EVENT_RULES_SETTINGS_KEY)
    if not raw_rules:
        return [rule.to_dict() for rule in default_rules()]
    return [rule.to_dict() for rule in rules_from_dicts(raw_rules)]


async def update_event_rules(
    db: AsyncSession,
    raw_rules: list[dict],
    *,
    actor_id: Any,
    actor_ip: str | None = None,
) -> list[dict]:
    """Replace the workspace rules config (persisted in workspace settings)."""
    if not isinstance(raw_rules, list):
        raise ValueError("rules must be a JSON array")
    if len(raw_rules) > 50:
        raise ValueError("too many rules (max 50)")
    rules = rules_from_dicts(raw_rules)
    if not rules:
        raise ValueError("no valid rules provided")

    serialized = [rule.to_dict() for rule in rules]
    row = await _get_workspace_row(db)
    operational = dict(row.operational_json) if row and row.operational_json else {}
    operational[EVENT_RULES_SETTINGS_KEY] = serialized

    if row:
        row.operational_json = operational
    else:
        db.add(WorkspaceSettings(singleton_key=WORKSPACE_SETTINGS_KEY, operational_json=operational))

    await write_audit(
        db,
        event_type="perception.event_rules_updated",
        severity="INFO",
        actor_id=actor_id,
        actor_type="user",
        resource_type="workspace_settings",
        resource_id=None,
        details={"rules": [rule.to_dict() for rule in rules]},
        ip_address=actor_ip,
    )
    await db.commit()
    return serialized


async def record_perception_event(
    db: AsyncSession,
    *,
    event: dict,
    rule: EventRule,
    storage_keys: list[str] | None = None,
    dataset_id=None,
    tenant_id=None,
    started_at: datetime | None = None,
) -> PerceptionEvent:
    """Persist one triggered perception event."""
    bbox = event.get("bbox") or []
    record = PerceptionEvent(
        event_type=event["event_type"],
        rule_id=rule.rule_id,
        rule_name=rule.name,
        track_id=event.get("track_id"),
        class_name=event.get("class_name"),
        taxonomy_label=event.get("taxonomy_label"),
        confidence=float(event.get("confidence", 0.0)),
        bbox=[float(v) for v in bbox] if bbox else None,
        started_at=started_at,
        triggered_at=datetime.fromtimestamp(float(event["triggered_at"]), tz=UTC),
        duration_seconds=event.get("duration_seconds"),
        clip_frames=len(storage_keys) if storage_keys else 0,
        clip_storage_keys=storage_keys or None,
        auto_save=bool(rule.auto_save),
        dataset_id=dataset_id,
        tenant_id=tenant_id,
        details=dict(event.get("details") or {}),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info(
        "perception_event_recorded",
        event_id=str(record.id),
        event_type=record.event_type,
        rule_id=record.rule_id,
        clip_frames=record.clip_frames,
    )
    return record


async def list_perception_events(
    db: AsyncSession,
    *,
    event_type: str | None = None,
    rule_id: str | None = None,
    track_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """List perception events newest-first with optional filters."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    filters = []
    if event_type:
        filters.append(PerceptionEvent.event_type == event_type)
    if rule_id:
        filters.append(PerceptionEvent.rule_id == rule_id)
    if track_id is not None:
        filters.append(PerceptionEvent.track_id == track_id)
    if since:
        filters.append(PerceptionEvent.triggered_at >= since)
    if until:
        filters.append(PerceptionEvent.triggered_at <= until)

    total = (
        await db.execute(select(sa.func.count()).select_from(PerceptionEvent).where(*filters))
    ).scalar() or 0

    rows = (
        await db.execute(
            select(PerceptionEvent)
            .where(*filters)
            .order_by(PerceptionEvent.triggered_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    return [_event_to_dict(e) for e in rows], int(total)


def _event_to_dict(e: PerceptionEvent) -> dict:
    return {
        "id": str(e.id),
        "event_type": e.event_type,
        "rule_id": e.rule_id,
        "rule_name": e.rule_name,
        "track_id": e.track_id,
        "class_name": e.class_name,
        "taxonomy_label": e.taxonomy_label,
        "confidence": round(e.confidence, 4),
        "bbox": e.bbox,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "triggered_at": e.triggered_at.isoformat() if e.triggered_at else None,
        "duration_seconds": e.duration_seconds,
        "clip_frames": e.clip_frames,
        "clip_storage_keys": e.clip_storage_keys or [],
        "auto_save": e.auto_save,
        "dataset_id": str(e.dataset_id) if e.dataset_id else None,
        "details": e.details or {},
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
