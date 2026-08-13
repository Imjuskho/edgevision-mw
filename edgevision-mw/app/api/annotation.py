from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.logging import get_logger
from app.schemas.annotation import (
    AnnotationResponse,
    AnnotatorLeaderboard,
    JobAssignment,
    JobAssignRequest,
    LabelSubmission,
    ReviewSubmission,
)
from app.services.annotation import (
    auto_assign_jobs,
    get_job_detail,
    get_leaderboard,
    get_pending_jobs,
    submit_labels,
    submit_review,
)

annotation_router = APIRouter(prefix="/jobs", tags=["Annotation"])
logger = get_logger("edgevision.api.annotation")


@annotation_router.post(
    "/assign",
    response_model=list[JobAssignment],
    status_code=status.HTTP_201_CREATED,
)
async def assign_jobs(
    body: JobAssignRequest = JobAssignRequest(),
    user: dict = Depends(require_role(["ADMIN", "QA"])),
    db: AsyncSession = Depends(get_db),
):
    assignments = await auto_assign_jobs(
        db, count=body.count, target_annotator=body.annotator_id
    )
    return assignments


@annotation_router.post(
    "/{job_id}/submit",
    response_model=AnnotationResponse,
)
async def submit(
    job_id: UUID,
    body: LabelSubmission,
    user: dict = Depends(require_role(["ANNOTATOR"])),
    db: AsyncSession = Depends(get_db),
):
    trace_id = str(uuid4())
    annotator_id = UUID(user["sub"])
    logger.info(
        "annotation_submit_start",
        trace_id=trace_id,
        job_id=str(job_id),
        annotator_id=str(annotator_id),
        label_count=len(body.labels) if body.labels else 0,
    )
    try:
        response = await submit_labels(
            db, job_id, annotator_id, body.labels, body.quality_score
        )
        logger.info(
            "annotation_submit_done",
            trace_id=trace_id,
            job_id=str(job_id),
            status=response.status,
        )
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_403_FORBIDDEN
            if "Not authorized" in detail
            else status.HTTP_404_NOT_FOUND
        )
        logger.warning("annotation_submit_failed", trace_id=trace_id, job_id=str(job_id), error=detail)
        raise HTTPException(status_code=code, detail=detail)
    return response


@annotation_router.post(
    "/{job_id}/review",
    response_model=AnnotationResponse,
)
async def review(
    job_id: UUID,
    body: ReviewSubmission,
    category: str = Query(default="object_detection", description="Annotation category for IAA calculation"),
    user: dict = Depends(require_role(["QA", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    try:
        response = await submit_review(
            db, job_id, UUID(user["sub"]), body.review_labels, category=category
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    return response


@annotation_router.get("/leaderboard", response_model=list[AnnotatorLeaderboard])
async def leaderboard(
    start_date: datetime | None = Query(default=None, description="Start date"),
    end_date: datetime | None = Query(default=None, description="End date"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_leaderboard(db, start_date, end_date)


@annotation_router.get("/pending")
async def pending_jobs(
    user: dict = Depends(require_role(["ANNOTATOR"])),
    db: AsyncSession = Depends(get_db),
):
    jobs = await get_pending_jobs(db, UUID(user["sub"]))
    return {"jobs": jobs, "count": len(jobs)}


@annotation_router.get("/{job_id}")
async def job_detail(
    job_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await get_job_detail(db, job_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return detail
