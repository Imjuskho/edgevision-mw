from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session, db_circuit_breaker
from app.core.dependencies import get_redis

health_router = APIRouter(tags=["Health"])


@health_router.get("/health/celery")
async def celery_health(redis=Depends(get_redis)):
    """Check that Celery workers and beat are alive via Redis heartbeat keys."""
    stale_threshold = timedelta(seconds=settings.CELERY_TASK_HEARTBEAT_TTL * 2)
    now = datetime.now(UTC)

    beat_alive = False
    workers: dict[str, str] = {}
    tasks: dict[str, str] = {}

    try:
        beat_key = "heartbeat:celery_beat"
        beat_ts = await redis.get(beat_key)
        if beat_ts:
            try:
                beat_time = datetime.fromisoformat(beat_ts)
                beat_alive = (now - beat_time) < stale_threshold
            except ValueError:
                beat_alive = False
    except Exception:
        pass

    try:
        worker_keys = await redis.keys("heartbeat:worker:*")
        for wk in sorted(worker_keys):
            raw = await redis.get(wk)
            if raw:
                try:
                    wt = datetime.fromisoformat(raw)
                    wname = wk.split(":", 2)[-1]
                    workers[wname] = "alive" if (now - wt) < stale_threshold else "stale"
                except ValueError:
                    workers[wk] = "unknown"
    except Exception:
        pass

    try:
        task_keys = await redis.keys("heartbeat:task:*")
        for tk in sorted(task_keys):
            raw = await redis.get(tk)
            if raw:
                try:
                    tt = datetime.fromisoformat(raw)
                    tname = tk.split(":", 2)[-1]
                    tasks[tname] = "alive" if (now - tt) < stale_threshold else "stale"
                except ValueError:
                    tasks[tk] = "unknown"
    except Exception:
        pass

    all_alive = beat_alive and any(v == "alive" for v in workers.values()) and any(v == "alive" for v in tasks.values())
    degraded = not all_alive

    return {
        "status": "degraded" if degraded and (beat_alive or workers) else "ok" if all_alive else "unhealthy",
        "beat": {
            "alive": beat_alive,
        },
        "workers": workers,
        "tasks": tasks,
        "stale_threshold_seconds": int(stale_threshold.total_seconds()),
    }


@health_router.get("/health/db")
async def db_health():
    """Check PostgreSQL connectivity and connection pool stats."""
    cb_available = db_circuit_breaker.is_available()
    pool_stats = {}
    db_ok = False
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    try:
        pool = db_circuit_breaker._failure_count  # simple proxy
        pool_stats = {
            "circuit_breaker_failures": pool,
        }
    except Exception:
        pass

    if db_ok:
        status = "ok"
    elif cb_available:
        status = "degraded"
    else:
        status = "unhealthy"

    return {
        "status": status,
        "database": "connected" if db_ok else "disconnected",
        "circuit_breaker": "closed" if cb_available else "open",
        "pool_stats": pool_stats,
    }
