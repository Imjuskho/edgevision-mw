"""Phase 3 Celery tasks: dedup analysis and export build."""

from __future__ import annotations

import asyncio

from celery import shared_task
from sqlalchemy import select

from app.core.database import async_session
from app.core.logging import get_logger
from app.models import ExportJob

logger = get_logger("edgevision.studio_tasks")


async def _run_async(coro):
    """Bridge sync Celery → async service."""
    return asyncio.run(coro)


async def _dedup_analyze_async(
    dataset_id: str,
    methods: list[str],
    threshold: float,
):
    from app.services.dedup import analyze, save_groups

    async with async_session() as db:
        clusters = await analyze(db, dataset_id, methods, threshold)
        saved = await save_groups(db, dataset_id, clusters)
        await db.commit()
        logger.info(
            "dedup_complete",
            dataset_id=dataset_id,
            clusters=len(clusters),
            saved=saved,
        )
        return {
            "groups": [
                {
                    "group_id": c.group_id,
                    "similarity": c.similarity,
                    "method": c.method,
                    "images": c.images,
                }
                for c in clusters
            ],
            "saved_groups": saved,
        }


@shared_task(bind=True, name="studio.dedup_analyze")
def dedup_analyze_task(
    self,
    dataset_id: str,
    methods: list | None = None,
    threshold: float = 0.92,
):
    """Run deduplication analysis as a Celery task."""
    methods = methods or ["phash", "clip"]
    try:
        self.update_state(state="PROGRESS", meta={"progress": 10})
        result = _run_async(_dedup_analyze_async(dataset_id, methods, threshold))
        self.update_state(state="PROGRESS", meta={"progress": 100})
        return result
    except Exception as exc:
        logger.error("dedup_failed", dataset_id=dataset_id, error=str(exc))
        raise


async def _export_build_async(
    job_id: str,
    format: str,
    split_ratio: dict,
    augmentations: dict | None,
    stratify: list,
    watermark: bool,
):
    from app.services.export_builder import build_export

    async with async_session() as db:
        result = await build_export(
            db=db,
            job_id=job_id,
            format=format,
            split_ratio=split_ratio,
            augmentations=augmentations,
            stratify=stratify,
            watermark=watermark,
        )
        await db.commit()
        logger.info("export_complete", job_id=job_id, output_path=result)
        return {"output_path": result, "status": "completed"}


@shared_task(bind=True, name="studio.export_build")
def export_build_task(
    self,
    job_id: str,
    format: str,
    split_ratio: dict,
    augmentations: dict | None,
    stratify: list,
    watermark: bool,
):
    """Build dataset export as a Celery task."""
    try:
        self.update_state(state="PROGRESS", meta={"progress": 10})
        result = _run_async(_export_build_async(job_id, format, split_ratio, augmentations, stratify, watermark))
        self.update_state(state="PROGRESS", meta={"progress": 100})
        return result
    except Exception as exc:
        logger.error("export_build_failed", job_id=job_id, error=str(exc))
        _run_async(_mark_export_failed(job_id, str(exc)))
        raise


async def _mark_export_failed(job_id: str, error: str):
    async with async_session() as db:
        stmt = select(ExportJob).where(ExportJob.id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.status = "FAILED"
            job.error_message = error
            await db.commit()
