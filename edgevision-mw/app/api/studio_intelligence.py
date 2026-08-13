from __future__ import annotations

from uuid import UUID

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.studio import _resolve_dataset
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.features import require_role_and_feature
from app.models import (
    ExportJob,
)
from app.services.dedup import resolve_groups
from app.services.export_builder import generate_preview
from app.services.health_score import (
    get_capture_recommendations,
    get_class_distribution,
    get_health_history,
)
from app.workers.celery_app import celery_app

studio_intelligence_router = APIRouter(prefix="/studio", tags=["studio-intelligence"])


# ─── Request Models ─────────────────────────────────────────────────────────


class DedupAnalyzeRequest(BaseModel):
    dataset_id: str
    methods: list[str] = Field(default=["phash", "clip"])
    threshold: float = Field(default=0.92, ge=0.8, le=1.0)


class DedupResolveRequest(BaseModel):
    dataset_id: str
    resolutions: list[dict]


class ExportPreviewRequest(BaseModel):
    dataset_id: str
    format: str = Field(..., pattern=r"^(coco|yolo|pascal_voc)$")
    augmentations: dict | None = None
    sample_size: int = Field(default=10, ge=1, le=50)


class ExportBuildRequest(BaseModel):
    dataset_id: str
    format: str = Field(..., pattern=r"^(coco|yolo|pascal_voc)$")
    split_ratio: dict[str, float]
    augmentations: dict | None = None
    stratify: list[str] = Field(default_factory=list)
    watermark: bool = True


# ─── Health Endpoints ───────────────────────────────────────────────────────

# NOTE: /datasets/{dataset_id}/health is handled by the original studio_router
# in app/api/studio.py which returns HealthScoreResponse.
# The Phase 3 4-dimension health scoring is available via compute_health_score()
# in app/services/health_score.py for programmatic use.


@studio_intelligence_router.get("/datasets/{dataset_id}/health-history")
async def dataset_health_history(
    dataset_id: str,
    days: int = Query(default=30, ge=1, le=365),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _resolve_dataset(db, dataset_id)
    return await get_health_history(db, ds.dataset_id, days)


@studio_intelligence_router.get("/datasets/{dataset_id}/class-distribution")
async def dataset_class_distribution(
    dataset_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _resolve_dataset(db, dataset_id)
    return await get_class_distribution(db, ds.dataset_id)


@studio_intelligence_router.get("/datasets/{dataset_id}/capture-recommendations")
async def dataset_capture_recommendations(
    dataset_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _resolve_dataset(db, dataset_id)
    return await get_capture_recommendations(db, ds.dataset_id)


# ─── Dedup Endpoints ────────────────────────────────────────────────────────


@studio_intelligence_router.post("/dedup/analyze")
async def dedup_analyze(
    body: DedupAnalyzeRequest,
    user: dict = Depends(require_role_and_feature(["ADMIN", "OPERATOR"], "dedup")),
    db: AsyncSession = Depends(get_db),
):
    ds = await _resolve_dataset(db, body.dataset_id)

    task = celery_app.send_task(
        "studio.dedup_analyze",
        args=[ds.dataset_id, body.methods, body.threshold],
    )
    return {"job_id": task.id, "status": "PENDING"}


@studio_intelligence_router.get("/dedup/results/{job_id}")
async def dedup_results(
    job_id: UUID,
    user: dict = Depends(get_current_user),
):
    result = AsyncResult(str(job_id), app=celery_app)

    if result.state == "PENDING":
        return {"job_id": str(job_id), "status": "PENDING", "result": None}
    if result.state == "FAILURE":
        return {"job_id": str(job_id), "status": "FAILED", "error": str(result.info)}
    if result.state == "SUCCESS":
        return {"job_id": str(job_id), "status": "COMPLETED", "result": result.result}
    return {"job_id": str(job_id), "status": result.state, "result": None}


@studio_intelligence_router.post("/dedup/resolve")
async def dedup_resolve(
    body: DedupResolveRequest,
    user: dict = Depends(require_role_and_feature(["ADMIN", "OPERATOR"], "dedup")),
    db: AsyncSession = Depends(get_db),
):
    ds = await _resolve_dataset(db, body.dataset_id)

    resolutions = {r["group_id"]: r["action"] for r in body.resolutions}
    await resolve_groups(db, ds.dataset_id, resolutions)
    return {"status": "resolved", "dataset_id": body.dataset_id}


# ─── Export Endpoints ───────────────────────────────────────────────────────


@studio_intelligence_router.post("/export/preview")
async def export_preview(
    body: ExportPreviewRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _resolve_dataset(db, body.dataset_id)

    return await generate_preview(
        db,
        ds.dataset_id,
        body.format,
        body.augmentations,
        body.sample_size,
    )


@studio_intelligence_router.post("/export/build")
async def export_build(
    body: ExportBuildRequest,
    user: dict = Depends(require_role_and_feature(["ADMIN", "OPERATOR"], "export")),
    db: AsyncSession = Depends(get_db),
):
    ds = await _resolve_dataset(db, body.dataset_id)

    job = ExportJob(
        dataset_id=ds.id,
        user_id=UUID(user["sub"]),
        status="PENDING",
        format=body.format,
        split_config=body.split_ratio,
        augmentation_config=body.augmentations,
        include_images=True,
        include_annotations=True,
        include_metadata=True,
        progress_pct=0.0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    celery_app.send_task(
        "studio.export_build",
        args=[
            str(job.id),
            ds.dataset_id,
            body.format,
            body.split_ratio,
            body.augmentations,
            body.stratify,
            body.watermark,
        ],
    )

    return {"job_id": str(job.id), "status": "PENDING"}


@studio_intelligence_router.get("/exports/{job_id}")
async def get_export_status(
    job_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(ExportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found")
    if job.user_id != UUID(user["sub"]):
        raise HTTPException(status_code=403, detail="Not your export job")

    return {
        "job_id": str(job.id),
        "status": job.status,
        "format": job.format,
        "progress_pct": job.progress_pct,
        "download_url": job.download_url,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@studio_intelligence_router.get("/exports")
async def list_exports(
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ExportJob)
        .where(ExportJob.user_id == UUID(user["sub"]))
        .order_by(ExportJob.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "job_id": str(j.id),
            "dataset_id": str(j.dataset_id),
            "status": j.status,
            "format": j.format,
            "progress_pct": j.progress_pct,
            "download_url": j.download_url,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in rows
    ]
