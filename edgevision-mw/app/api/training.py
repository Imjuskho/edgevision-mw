from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.features import require_role_and_feature
from app.models.enums import TrainingStatus
from app.models.training import TrainingJob
from app.schemas.training import (
    TrainingJobResponse,
    TrainingListResponse,
    TrainingStartRequest,
)
from app.workers.celery_app import celery_app

training_router = APIRouter(prefix="/studio/training", tags=["Training"])


def _map_job(job: TrainingJob) -> TrainingJobResponse:
    return TrainingJobResponse(
        id=job.id,
        user_id=job.user_id,
        dataset_id=job.dataset_id,
        model_name=job.model_name,
        model_type=job.model_type,
        status=job.status,
        progress_pct=job.progress_pct,
        accuracy=job.accuracy,
        epochs=job.epochs,
        batch_size=job.batch_size,
        learning_rate=job.learning_rate,
        config_json=job.config_json,
        artifact_path=job.artifact_path,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@training_router.post("/start", response_model=TrainingJobResponse, status_code=status.HTTP_201_CREATED)
async def start_training(
    body: TrainingStartRequest,
    user: dict = Depends(require_role_and_feature(["ADMIN", "OPERATOR"], "training")),
    db: AsyncSession = Depends(get_db),
):
    job = TrainingJob(
        user_id=UUID(user["sub"]),
        dataset_id=body.dataset_id,
        model_name=body.model_name,
        model_type=body.model_type,
        status=TrainingStatus.PENDING,
        progress_pct=0,
        accuracy=None,
        epochs=body.epochs,
        batch_size=body.batch_size,
        learning_rate=body.learning_rate,
        config_json=body.config_json,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    celery_app.send_task("workers.run_training", args=[str(job.id)])

    return _map_job(job)


@training_router.get("/", response_model=TrainingListResponse)
async def list_training_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    dataset_id: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TrainingJob)
    if dataset_id:
        stmt = stmt.where(TrainingJob.dataset_id == dataset_id)
    stmt = stmt.order_by(TrainingJob.created_at.desc())
    total = (await db.execute(stmt)).scalars().all()
    total_count = len(total)
    offset = (page - 1) * page_size
    rows = (await db.execute(stmt.offset(offset).limit(page_size))).scalars().all()
    return TrainingListResponse.create([_map_job(j) for j in rows], total_count, page, page_size)


@training_router.get("/{job_id}", response_model=TrainingJobResponse)
async def get_training_job(
    job_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(TrainingJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training job not found")
    return _map_job(job)


@training_router.post("/{job_id}/cancel", response_model=TrainingJobResponse)
async def cancel_training_job(
    job_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(TrainingJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training job not found")

    if job.status not in {TrainingStatus.PENDING, TrainingStatus.RUNNING}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending or running jobs can be cancelled",
        )

    job.status = TrainingStatus.FAILED
    job.error_message = "Cancelled by user"
    job.completed_at = datetime.now()
    await db.commit()
    await db.refresh(job)
    return _map_job(job)
