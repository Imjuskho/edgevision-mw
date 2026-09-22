from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.logging import get_logger
from app.models.experiment import ExperimentEvent
from app.schemas.analytics import (
    ExperimentEventBatch,
    ExperimentEventOut,
)

logger = get_logger("edgevision.api.analytics")

analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _parse_timestamp(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


@analytics_router.post("/experiments", status_code=201)
async def ingest_experiment_events(
    body: ExperimentEventBatch,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingest A/B experiment events flushed from the frontend."""
    events = []
    for ev in body.events:
        user_id = UUID(ev.user_id) if ev.user_id else None
        if user_id is None:
            try:
                user_id = UUID(user["sub"])
            except (KeyError, ValueError):
                user_id = None
        events.append(
            ExperimentEvent(
                user_id=user_id,
                experiment_id=ev.experiment_id,
                variant_id=ev.variant_id,
                event_type=ev.event_type,
                metadata_json=ev.metadata,
                occurred_at=_parse_timestamp(ev.timestamp),
            )
        )

    db.add_all(events)
    await db.commit()

    logger.info(
        "experiment_events_ingested",
        count=len(events),
        actor_id=str(user.get("sub", "")),
    )
    return {"received": len(events), "status": "ok"}


@analytics_router.get("/experiments", response_model=list[ExperimentEventOut])
async def list_experiment_events(
    limit: int = 100,
    experiment_id: str | None = None,
    user: dict = Depends(require_role(["ADMIN", "OPERATOR"])),
    db: AsyncSession = Depends(get_db),
):
    """List experiment events (admin/operator) with optional filtering."""
    stmt = select(ExperimentEvent)
    if experiment_id:
        stmt = stmt.where(ExperimentEvent.experiment_id == experiment_id)
    stmt = stmt.order_by(ExperimentEvent.occurred_at.desc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        ExperimentEventOut(
            id=e.id,
            experiment_id=e.experiment_id,
            variant_id=e.variant_id,
            event_type=e.event_type,
            user_id=e.user_id,
            metadata=e.metadata_json,
            occurred_at=e.occurred_at,
        )
        for e in rows
    ]


@analytics_router.get("/experiments/summary")
async def experiment_summary(
    user: dict = Depends(require_role(["ADMIN", "OPERATOR"])),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate exposure/conversion counts per experiment-variant pair."""
    from sqlalchemy import func

    stmt = (
        select(
            ExperimentEvent.experiment_id,
            ExperimentEvent.variant_id,
            ExperimentEvent.event_type,
            func.count().label("count"),
        )
        .group_by(
            ExperimentEvent.experiment_id,
            ExperimentEvent.variant_id,
            ExperimentEvent.event_type,
        )
        .order_by(ExperimentEvent.experiment_id, ExperimentEvent.variant_id)
    )
    rows = (await db.execute(stmt)).all()

    summary: dict[str, dict] = {}
    for experiment_id, variant_id, event_type, count in rows:
        entry = summary.setdefault(experiment_id, {"variants": {}})
        variant = entry["variants"].setdefault(variant_id, {"exposed": 0, "converted": 0, "dismissed": 0})
        variant[event_type] = int(count)

    return {"experiments": summary}
