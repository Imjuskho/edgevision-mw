import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.core.dependencies import close_connections, init_connections
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, request_id_var, setup_logging
from app.core.sentry import init_sentry


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_sentry()
    logger = get_logger("edgevision.startup")
    await init_db()
    await init_connections()

    try:
        from app.core.dependencies import get_minio_client
        minio_client = await get_minio_client()
        bucket = settings.MINIO_BUCKET
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
            logger.info("minio_bucket_created", bucket=bucket)
    except Exception as exc:
        logger.warning("minio_bucket_check_failed", error=str(exc))

    try:
        from app.ai.mask_utils import pycocotools_available

        if not pycocotools_available():
            logger.warning("mask_rle_unavailable", reason="pycocotools_not_installed")
    except Exception as exc:
        logger.warning("mask_rle_check_failed", error=str(exc))

    logger.info("app_started", version=settings.VERSION)
    yield
    await close_connections()
    logger.info("app_stopped")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="EdgeVision-MW Control Plane — fleet management, data ingestion, annotation, catalog, compliance, and billing.",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Fleet", "description": "Edge device registration, heartbeat, telemetry, and commands."},
        {"name": "Ingestion", "description": "Batch upload, validation, and processing of captured data."},
        {"name": "Annotation", "description": "Job assignment, label submission, QA review, and inter-annotator agreement."},
        {"name": "Catalog", "description": "Dataset search, build, manifest generation, and pricing quotes."},
        {"name": "Compliance", "description": "Consent recording, withdrawal, verification, PII detection, and audit."},
        {"name": "Billing", "description": "Dataset export, payment escrow, delivery, and revenue breakdown."},
        {"name": "Auth", "description": "User registration, login, JWT tokens, and API key management."},
        {"name": "Studio", "description": "AI-first annotation studio — sessions, images, annotations, and sync."},
        {"name": "Studio Intelligence", "description": "Dataset health, class distribution, dedup analysis, and export build."},
        {"name": "Model Registry", "description": "Deploy trained model artifacts and manage which one is active per model type."},
        {"name": "Metrics", "description": "Prometheus metrics endpoint for monitoring and alerting."},
        {"name": "Agriculture Analysis", "description": "Crop type and health instance segmentation and field condition analysis."},
    ],
)

register_exception_handlers(app)

_cors_origins = [
    o.strip()
    for o in settings.CORS_ORIGINS.split(",")
    if o.strip()
] or ["http://localhost:3000", "http://localhost:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    rid = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    request_id_var.set(rid)
    request.state.request_id = rid
    request.state.user_id = None

    try:
        import uuid as _uuid

        from app.core.tenant import set_current_tenant_id
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            from app.core.security import decode_access_token
            token = auth_header.removeprefix("Bearer ")
            payload = decode_access_token(token)
            sub = payload.get("sub")
            if sub:
                set_current_tenant_id(_uuid.UUID(sub))
    except Exception:
        pass

    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000, 2)

    try:
        from app.api.metrics import http_request_duration_seconds, http_requests_total
        endpoint = request.url.path
        method = request.method
        status = str(response.status_code)
        http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration_ms / 1000.0)
    except Exception:
        pass

    logger = get_logger("edgevision.request")
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
    )

    response.headers["X-Request-ID"] = rid
    response.headers["X-Correlation-Id"] = rid
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    from app.core.rate_limit import check_rate_limit

    limit_response = await check_rate_limit(request)
    if limit_response is not None:
        return limit_response
    return await call_next(request)


from app.api import (  # noqa: E402
    admin_router,
    agri_router,
    analytics_router,
    annotation_router,
    annotations_live_router,
    assignment_router,
    billing_router,
    catalog_router,
    clip_router,
    compliance_router,
    fleet_router,
    health_router,
    image_upload_router,
    ingestion_router,
    metrics_router,
    model_registry_router,
    prelabel_router,
    review_router,
    road_router,
    serve_router,
    studio_ai_router,
    studio_intelligence_router,
    studio_router,
    studio_sync_router,
    training_router,
    ws_annotation_router,
)
from app.auth.router import auth_router  # noqa: E402

app.include_router(metrics_router)
app.include_router(health_router)
app.include_router(admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(analytics_router, prefix=settings.API_V1_PREFIX)
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(fleet_router, prefix=settings.API_V1_PREFIX)
app.include_router(ingestion_router, prefix=settings.API_V1_PREFIX)
app.include_router(annotation_router, prefix=settings.API_V1_PREFIX)
app.include_router(assignment_router, prefix=settings.API_V1_PREFIX)
app.include_router(catalog_router, prefix=settings.API_V1_PREFIX)
app.include_router(clip_router, prefix=settings.API_V1_PREFIX)
app.include_router(compliance_router, prefix=settings.API_V1_PREFIX)
app.include_router(billing_router, prefix=settings.API_V1_PREFIX)
app.include_router(image_upload_router, prefix=settings.API_V1_PREFIX)
app.include_router(serve_router, prefix=settings.API_V1_PREFIX)
app.include_router(ingestion_router, prefix=settings.API_V1_PREFIX)
app.include_router(prelabel_router, prefix=settings.API_V1_PREFIX)
app.include_router(review_router, prefix=settings.API_V1_PREFIX)
app.include_router(agri_router, prefix=settings.API_V1_PREFIX)
app.include_router(road_router, prefix=settings.API_V1_PREFIX)
app.include_router(studio_router, prefix=settings.API_V1_PREFIX)
app.include_router(studio_ai_router, prefix=settings.API_V1_PREFIX)
app.include_router(studio_intelligence_router, prefix=settings.API_V1_PREFIX)
app.include_router(studio_sync_router, prefix=settings.API_V1_PREFIX)
app.include_router(training_router, prefix=settings.API_V1_PREFIX)
app.include_router(annotations_live_router, prefix=settings.API_V1_PREFIX)
app.include_router(ws_annotation_router)
app.include_router(model_registry_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health_check():
    checks = {"postgres": False, "redis": False, "minio": False}

    # Postgres
    try:
        from sqlalchemy import text

        from app.core.database import async_session
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        pass

    # Redis
    try:
        from app.core.dependencies import _redis_client
        if _redis_client is not None:
            await _redis_client.ping()
            checks["redis"] = True
    except Exception:
        pass

    # MinIO
    try:
        from app.core.dependencies import _minio_client
        if _minio_client is not None:
            _minio_client.bucket_exists(settings.MINIO_BUCKET)
            checks["minio"] = True
    except Exception:
        pass

    healthy = all(checks.values())
    return {
        "status": "ok" if healthy else "degraded",
        "version": settings.VERSION,
        "checks": checks,
    }
