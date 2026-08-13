from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.annotation import Annotation
from app.models.assignment import DatasetAssignment
from app.models.buyer import User
from app.models.dataset import Dataset
from app.schemas.assignment import (
    AssignmentClaim,
    AssignmentCreate,
    AssignmentListResponse,
    AssignmentResponse,
    QueueItem,
    QueueResponse,
)

assignment_router = APIRouter(prefix="/assignments", tags=["Assignment"])


@assignment_router.post(
    "",
    response_model=AssignmentListResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignments(
    body: AssignmentCreate,
    user: dict = Depends(require_role(["ADMIN", "QA"])),
    db: AsyncSession = Depends(get_db),
):
    ds = await _resolve_dataset(db, body.dataset_id)

    annotator_ids = []
    for aid in body.annotator_ids:
        try:
            uid = UUID(aid)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid annotator ID: {aid}")
        annotator = await db.get(User, uid)
        if annotator is None:
            raise HTTPException(status_code=404, detail=f"Annotator not found: {aid}")
        annotator_ids.append(uid)

    total_images_stmt = select(func.count()).where(Annotation.dataset_id == ds.id)
    total_images = (await db.execute(total_images_stmt)).scalar() or 0

    if total_images == 0:
        raise HTTPException(status_code=400, detail="Dataset has no images to assign")

    per_annotator = total_images // len(annotator_ids)
    remainder = total_images % len(annotator_ids)

    created = []
    for idx, aid in enumerate(annotator_ids):
        count = per_annotator + (1 if idx < remainder else 0)

        existing_stmt = select(DatasetAssignment).where(
            DatasetAssignment.dataset_id == ds.id,
            DatasetAssignment.annotator_id == aid,
            DatasetAssignment.status.in_(["ASSIGNED", "IN_PROGRESS"]),
        ).limit(1)
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()

        if existing:
            existing.deadline = body.deadline
            existing.priority = body.priority
            existing.total_images = count
            await db.flush()
            created.append(existing)
        else:
            assignment = DatasetAssignment(
                dataset_id=ds.id,
                annotator_id=aid,
                assigned_by=UUID(user["sub"]),
                status="ASSIGNED",
                deadline=body.deadline,
                priority=body.priority,
                total_images=count,
                completed_images=0,
            )
            db.add(assignment)
            await db.flush()
            created.append(assignment)

    await db.commit()

    results = []
    for a in created:
        await db.refresh(a)
        results.append(await _format_assignment(db, a))

    return AssignmentListResponse(assignments=results, total=len(results))


@assignment_router.get("", response_model=AssignmentListResponse)
async def list_assignments(
    dataset_id: str | None = None,
    annotator_id: str | None = None,
    status_filter: str | None = None,
    user: dict = Depends(require_role(["ADMIN", "QA"])),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DatasetAssignment)

    if dataset_id:
        ds = await _resolve_dataset(db, dataset_id)
        stmt = stmt.where(DatasetAssignment.dataset_id == ds.id)

    if annotator_id:
        try:
            uid = UUID(annotator_id)
            stmt = stmt.where(DatasetAssignment.annotator_id == uid)
        except ValueError:
            pass

    if status_filter:
        stmt = stmt.where(DatasetAssignment.status == status_filter)

    stmt = stmt.order_by(DatasetAssignment.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()

    results = []
    for a in rows:
        results.append(await _format_assignment(db, a))

    return AssignmentListResponse(assignments=results, total=len(results))


@assignment_router.get("/queue", response_model=QueueResponse)
async def annotator_queue(
    user: dict = Depends(require_role(["ANNOTATOR", "ADMIN", "OPERATOR", "QA", "BUYER"])),
    db: AsyncSession = Depends(get_db),
):
    annotator_id = UUID(user["sub"])

    stmt = (
        select(DatasetAssignment)
        .where(
            DatasetAssignment.annotator_id == annotator_id,
            DatasetAssignment.status.in_(["ASSIGNED", "IN_PROGRESS"]),
        )
        .order_by(DatasetAssignment.priority.desc(), DatasetAssignment.deadline.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    items = []
    for a in rows:
        ds = await db.get(Dataset, a.dataset_id)
        if ds is None:
            continue

        labeled_stmt = select(func.count()).where(
            Annotation.dataset_id == a.dataset_id,
            Annotation.human_labels.isnot(None),
        )
        labeled_count = (await db.execute(labeled_stmt)).scalar() or 0

        is_overdue = (
            a.deadline is not None
            and a.deadline < datetime.now(UTC)
            and a.status != "COMPLETED"
        )

        items.append(QueueItem(
            assignment_id=a.id,
            dataset_id=ds.dataset_id,
            dataset_name=ds.name,
            status=a.status,
            deadline=a.deadline,
            priority=a.priority,
            total_images=a.total_images,
            completed_images=labeled_count,
            progress_pct=round((labeled_count / a.total_images * 100) if a.total_images > 0 else 0, 1),
            is_overdue=is_overdue,
            image_count_available=a.total_images - labeled_count,
        ))

    return QueueResponse(items=items, total=len(items))


@assignment_router.post("/claim")
async def claim_assignment(
    body: AssignmentClaim,
    user: dict = Depends(require_role(["ANNOTATOR"])),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(DatasetAssignment, body.assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment.annotator_id != UUID(user["sub"]):
        raise HTTPException(status_code=403, detail="Not your assignment")
    if assignment.status not in ("ASSIGNED",):
        raise HTTPException(status_code=400, detail=f"Cannot claim assignment in status: {assignment.status}")

    assignment.status = "IN_PROGRESS"
    await db.commit()

    return {"status": "IN_PROGRESS", "message": "Assignment claimed. You can now start annotating."}


@assignment_router.post("/submit")
async def submit_assignment(
    body: AssignmentClaim,
    user: dict = Depends(require_role(["ANNOTATOR"])),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(DatasetAssignment, body.assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment.annotator_id != UUID(user["sub"]):
        raise HTTPException(status_code=403, detail="Not your assignment")
    if assignment.status not in ("ASSIGNED", "IN_PROGRESS"):
        raise HTTPException(status_code=400, detail=f"Cannot submit assignment in status: {assignment.status}")

    assignment.status = "SUBMITTED"
    await db.commit()

    return {"status": "SUBMITTED", "message": "Assignment submitted for QA review."}


async def _resolve_dataset(db: AsyncSession, identifier: str) -> Dataset:
    try:
        uid = UUID(identifier)
        ds = await db.get(Dataset, uid)
        if ds is not None:
            return ds
    except ValueError:
        pass
    stmt = select(Dataset).where(Dataset.dataset_id == identifier).limit(1)
    ds = (await db.execute(stmt)).scalar_one_or_none()
    if ds is None:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {identifier}")
    return ds


async def _format_assignment(db: AsyncSession, a: DatasetAssignment) -> AssignmentResponse:
    ds = await db.get(Dataset, a.dataset_id)
    annotator = await db.get(User, a.annotator_id)

    labeled_stmt = select(func.count()).where(
        Annotation.dataset_id == a.dataset_id,
        Annotation.human_labels.isnot(None),
    )
    labeled_count = (await db.execute(labeled_stmt)).scalar() or 0

    is_overdue = (
        a.deadline is not None
        and a.deadline < datetime.now(UTC)
        and a.status != "COMPLETED"
    )

    return AssignmentResponse(
        id=a.id,
        dataset_id=ds.dataset_id if ds else str(a.dataset_id),
        dataset_name=ds.name if ds else "Unknown",
        annotator_id=str(a.annotator_id),
        annotator_name=annotator.email if annotator else "Unknown",
        status=a.status,
        deadline=a.deadline,
        priority=a.priority,
        total_images=a.total_images,
        completed_images=labeled_count,
        progress_pct=round((labeled_count / a.total_images * 100) if a.total_images > 0 else 0, 1),
        is_overdue=is_overdue,
        created_at=a.created_at,
    )
