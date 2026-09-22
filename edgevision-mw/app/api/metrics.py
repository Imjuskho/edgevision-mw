"""Prometheus metrics endpoint.

Exposes /metrics with HTTP request metrics, Celery task counts,
annotation counts, and dataset health gauges.
"""

from __future__ import annotations

import time
from contextlib import contextmanager

from fastapi import APIRouter, Depends, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from app.core.database import get_db

metrics_router = APIRouter(tags=["metrics"])

# ─── Registry ─────────────────────────────────────────────────────────────

registry = CollectorRegistry()

# ─── HTTP Metrics ─────────────────────────────────────────────────────────

http_requests_total = Counter(
    "edgevision_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "edgevision_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=registry,
)

# ─── Business Metrics ─────────────────────────────────────────────────────

annotations_total = Counter(
    "edgevision_annotations_total",
    "Total annotations created",
    ["status", "label"],
    registry=registry,
)

uploads_total = Counter(
    "edgevision_uploads_total",
    "Total image uploads",
    ["status"],
    registry=registry,
)

datasets_total = Gauge(
    "edgevision_datasets_total",
    "Total datasets",
    registry=registry,
)

active_sessions = Gauge(
    "edgevision_active_sessions",
    "Active annotation sessions",
    registry=registry,
)

celery_tasks_total = Counter(
    "edgevision_celery_tasks_total",
    "Total Celery tasks executed",
    ["task_name", "status"],
    registry=registry,
)

# ─── Inference Metrics ──────────────────────────────────────────────────

inference_requests_total = Counter(
    "edgevision_inference_requests_total",
    "Total inference requests",
    ["model_type", "status"],
    registry=registry,
)

inference_duration_seconds = Histogram(
    "edgevision_inference_duration_seconds",
    "Inference duration in seconds",
    ["model_type"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    registry=registry,
)

# ─── Live WebSocket Annotation Metrics ────────────────────────────────────

ws_annotate_frames_total = Counter(
    "edgevision_ws_annotate_frames_total",
    "Live annotation WebSocket frames processed",
    ["model_type", "status"],
    registry=registry,
)

ws_annotate_dropped_total = Counter(
    "edgevision_ws_annotate_dropped_total",
    "Live annotation frames dropped due to backpressure",
    ["model_type", "reason"],
    registry=registry,
)

ws_annotate_duration_seconds = Histogram(
    "edgevision_ws_annotate_duration_seconds",
    "Live annotation end-to-end frame processing duration",
    ["model_type"],
    buckets=[0.05, 0.1, 0.25, 0.5, 0.8, 1.0, 2.0, 5.0],
    registry=registry,
)

ws_annotate_events_total = Counter(
    "edgevision_ws_annotate_events_total",
    "Perception events triggered/saved over live annotation WebSockets",
    ["model_type", "event_type", "status"],
    registry=registry,
)

depth_inference_ms = Histogram(
    "edgevision_depth_inference_seconds",
    "Monocular depth ONNX inference duration",
    buckets=[0.01, 0.025, 0.05, 0.08, 0.1, 0.25, 0.5, 1.0],
    registry=registry,
)

# ─── Infrastructure Gauges ──────────────────────────────────────────────

celery_task_queue_depth = Gauge(
    "edgevision_celery_task_queue_depth",
    "Celery task queue depth by queue name",
    ["queue_name"],
    registry=registry,
)

minio_storage_bytes = Gauge(
    "edgevision_minio_storage_bytes",
    "MinIO storage usage in bytes",
    ["bucket_name"],
    registry=registry,
)

# ─── Middleware Helpers ────────────────────────────────────────────────────


@contextmanager
def track_request(method: str, endpoint: str):
    """Context manager to track HTTP request metrics."""
    start = time.monotonic()
    status = "200"
    try:
        yield lambda s: setattr(_state, "status", str(s))
    except Exception:
        status = "500"
        raise
    finally:
        duration = time.monotonic() - start
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)
        http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()


_state = type("_State", (), {"status": "200"})()


# ─── Endpoint ─────────────────────────────────────────────────────────────


async def refresh_business_gauges(db) -> None:
    """Refresh DB/Redis/MinIO-derived business gauges before a scrape.

    Individual subsystems are guarded so an infrastructure failure never
    breaks the /metrics endpoint.
    """
    from sqlalchemy import func
    from sqlalchemy import select as _select

    try:
        from app.models.dataset import Dataset
        from app.models.studio import AnnotationSession

        ds_count = (await db.execute(_select(func.count()).select_from(Dataset))).scalar() or 0
        datasets_total.set(ds_count)

        active_count = (
            await db.execute(
                _select(func.count()).select_from(AnnotationSession).where(AnnotationSession.is_active.is_(True))
            )
        ).scalar() or 0
        active_sessions.set(active_count)
    except Exception:
        pass

    try:
        from app.core.dependencies import get_redis

        redis_client = await get_redis()
        for queue_name in ("celery", "dedup", "export", "training"):
            try:
                depth = await redis_client.llen(queue_name)
            except Exception:
                depth = 0
            celery_task_queue_depth.labels(queue_name=queue_name).set(depth or 0)
    except Exception:
        pass

    try:
        from app.core.dependencies import get_minio_client

        mc = await get_minio_client()
        buckets = mc.list_buckets()
        for bucket in buckets:
            bucket_name = bucket.name
            try:
                total_bytes = 0
                for obj in mc.list_objects(bucket_name, recursive=True):
                    total_bytes += obj.size or 0
                minio_storage_bytes.labels(bucket_name=bucket_name).set(total_bytes)
            except Exception:
                pass
    except Exception:
        pass


@metrics_router.get("/metrics")
async def metrics(db=Depends(get_db)):
    """Prometheus metrics endpoint."""
    await refresh_business_gauges(db)
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST,
    )
