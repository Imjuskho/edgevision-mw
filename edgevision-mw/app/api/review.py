from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.annotation import Annotation
from app.models.assignment import DatasetAssignment
from app.models.buyer import User
from app.models.dataset import Dataset
from app.models.enums import AnnotationStatus
from app.schemas.review import (
    IAAMetrics,
    LiveReviewBulkRequest,
    LiveReviewItem,
    LiveReviewQueueResponse,
    ReviewDecision,
    ReviewDecisionResponse,
    ReviewJobDetail,
    ReviewQueueItem,
    ReviewQueueResponse,
)
from app.services.audit_service import write_audit

review_router = APIRouter(prefix="/review", tags=["QA Review"])


def _is_live_capture(ann: Annotation) -> bool:
    detected = ann.detected_objects if isinstance(ann.detected_objects, dict) else {}
    source = detected.get("source", "")
    if source in ("live_camera", "screen", "drone"):
        return True
    auto = ann.auto_labels or {}
    if auto.get("source") in ("live_camera", "screen", "drone"):
        return True
    if detected.get("live_capture"):
        return True
    return "live-captures" in (ann.image_path or "")


def _live_orientation(ann: Annotation) -> str:
    detected = ann.detected_objects if isinstance(ann.detected_objects, dict) else {}
    return str(detected.get("orientation", "normal"))


def _live_depth_available(ann: Annotation) -> bool:
    detected = ann.detected_objects if isinstance(ann.detected_objects, dict) else {}
    if detected.get("depth_available"):
        return True
    objects = detected.get("objects", [])
    return any(isinstance(o, dict) and o.get("bbox_3d", {}).get("depth_available") for o in objects)


@review_router.get("/queue", response_model=ReviewQueueResponse)
async def review_queue(
    scope: str = "jobs",
    user: dict = Depends(require_role(["QA", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    if scope not in ("live", "jobs", "all"):
        raise HTTPException(status_code=400, detail="scope must be live, jobs, or all")

    if scope in ("jobs", "all"):
        stmt = (
            select(DatasetAssignment)
            .where(DatasetAssignment.status == "SUBMITTED")
            .order_by(DatasetAssignment.priority.desc(), DatasetAssignment.deadline.asc())
        )
        rows = (await db.execute(stmt)).scalars().all()
    else:
        rows = []

    items = []
    for a in rows:
        ds = await db.get(Dataset, a.dataset_id)
        annotator = await db.get(User, a.annotator_id)

        labeled_stmt = select(func.count()).where(
            Annotation.dataset_id == a.dataset_id,
            Annotation.human_labels.isnot(None),
        )
        labeled_count = (await db.execute(labeled_stmt)).scalar() or 0

        items.append(ReviewQueueItem(
            assignment_id=a.id,
            dataset_id=ds.dataset_id if ds else str(a.dataset_id),
            dataset_name=ds.name if ds else "Unknown",
            annotator_id=str(a.annotator_id),
            annotator_name=annotator.email if annotator else "Unknown",
            total_images=a.total_images,
            completed_images=labeled_count,
            submitted_at=a.updated_at,
            deadline=a.deadline,
            priority=a.priority,
        ))

    return ReviewQueueResponse(items=items, total=len(items))


@review_router.get("/live/queue", response_model=LiveReviewQueueResponse)
async def live_review_queue(
    user: dict = Depends(require_role(["QA", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
):
    """Pending live-capture frames awaiting single-reviewer QA (no IAA)."""
    stmt = (
        select(Annotation)
        .where(Annotation.status == AnnotationStatus.PENDING)
        .order_by(Annotation.created_at.desc())
        .limit(limit)
    )
    annotations = (await db.execute(stmt)).scalars().all()

    items: list[LiveReviewItem] = []
    for ann in annotations:
        if not _is_live_capture(ann):
            continue
        detected = ann.detected_objects if isinstance(ann.detected_objects, dict) else {}
        objects = detected.get("objects", [])
        items.append(LiveReviewItem(
            annotation_id=str(ann.id),
            image_path=ann.image_path,
            thumbnail_url=f"/api/v1/annotations/{ann.id}/thumbnail",
            status=ann.status.value if hasattr(ann.status, "value") else str(ann.status),
            orientation=_live_orientation(ann),
            depth_available=_live_depth_available(ann),
            annotation_count=len(objects) if isinstance(objects, list) else 0,
            created_at=ann.created_at,
            live_capture=True,
        ))

    return LiveReviewQueueResponse(items=items, total=len(items))


@review_router.post("/live/approve")
async def approve_live_bulk(
    body: LiveReviewBulkRequest,
    request: Request,
    user: dict = Depends(require_role(["QA", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-approve live captures — single reviewer, no IAA required."""
    approved = 0
    client_ip = request.client.host if request.client else None
    for ann_id_str in body.annotation_ids:
        ann_id = UUID(ann_id_str)
        ann = await db.get(Annotation, ann_id)
        if ann is None or not _is_live_capture(ann):
            continue
        ann.is_certified = True
        ann.status = AnnotationStatus.CERTIFIED
        ann.qa_reviewer_id = UUID(user["sub"])
        ann.review_completed_at = datetime.now(UTC)
        approved += 1
        await write_audit(
            db,
            event_type="review.live_approved",
            severity="INFO",
            actor_id=UUID(user["sub"]),
            actor_type="user",
            resource_type="annotation",
            resource_id=ann.id,
            details={"live_capture": True},
            ip_address=client_ip,
        )
    await db.commit()
    return {"status": "CERTIFIED", "approved_count": approved}


@review_router.post("/live/reject")
async def reject_live_bulk(
    body: LiveReviewBulkRequest,
    request: Request,
    user: dict = Depends(require_role(["QA", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-reject live captures."""
    rejected = 0
    client_ip = request.client.host if request.client else None
    for ann_id_str in body.annotation_ids:
        ann_id = UUID(ann_id_str)
        ann = await db.get(Annotation, ann_id)
        if ann is None or not _is_live_capture(ann):
            continue
        ann.status = AnnotationStatus.REJECTED
        ann.qa_reviewer_id = UUID(user["sub"])
        ann.review_completed_at = datetime.now(UTC)
        rejected += 1
        await write_audit(
            db,
            event_type="review.live_rejected",
            severity="WARN",
            actor_id=UUID(user["sub"]),
            actor_type="user",
            resource_type="annotation",
            resource_id=ann.id,
            details={"live_capture": True, "reason": body.reason},
            ip_address=client_ip,
        )
    await db.commit()
    return {"status": "REJECTED", "rejected_count": rejected}


@review_router.get("/jobs/{assignment_id}", response_model=ReviewJobDetail)
async def review_job_detail(
    assignment_id: UUID,
    user: dict = Depends(require_role(["QA", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(DatasetAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    ds = await db.get(Dataset, assignment.dataset_id)
    annotator = await db.get(User, assignment.annotator_id)

    stmt = (
        select(Annotation)
        .where(Annotation.dataset_id == assignment.dataset_id)
        .order_by(Annotation.image_index)
    )
    annotations = (await db.execute(stmt)).scalars().all()

    images = []
    for a in annotations:
        labels_data = a.human_labels or {}
        boxes = labels_data.get("boxes", []) if isinstance(labels_data, dict) else []
        images.append({
            "id": str(a.id),
            "image_path": a.image_path,
            "index": a.image_index,
            "status": a.status.value if hasattr(a.status, "value") else str(a.status),
            "is_certified": a.is_certified,
            "annotations": [
                {
                    "label": b.get("label", ""),
                    "confidence": b.get("confidence", 1.0),
                    "x": b.get("x", 0),
                    "y": b.get("y", 0),
                    "width": b.get("width", 0),
                    "height": b.get("height", 0),
                }
                for b in boxes
            ],
            "has_human_labels": a.human_labels is not None,
        })

    return ReviewJobDetail(
        assignment_id=assignment.id,
        dataset_id=ds.dataset_id if ds else str(assignment.dataset_id),
        dataset_name=ds.name if ds else "Unknown",
        annotator_id=str(assignment.annotator_id),
        annotator_name=annotator.email if annotator else "Unknown",
        total_images=assignment.total_images,
        completed_images=sum(1 for img in images if img["has_human_labels"]),
        images=images,
        deadline=assignment.deadline,
        priority=assignment.priority,
    )


@review_router.post("/jobs/{assignment_id}/certify", response_model=ReviewDecisionResponse)
async def certify_job(
    assignment_id: UUID,
    request: Request,
    user: dict = Depends(require_role(["QA", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(DatasetAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment.status != "SUBMITTED":
        raise HTTPException(status_code=400, detail=f"Assignment status is {assignment.status}, not SUBMITTED")

    stmt = select(Annotation).where(Annotation.dataset_id == assignment.dataset_id)
    annotations = (await db.execute(stmt)).scalars().all()

    certified_count = 0
    for a in annotations:
        if a.human_labels is not None:
            a.is_certified = True
            a.status = AnnotationStatus.CERTIFIED
            a.qa_reviewer_id = UUID(user["sub"])
            a.review_completed_at = datetime.now(UTC)
            certified_count += 1

    assignment.status = "CERTIFIED"
    assignment.completed_images = certified_count
    client_ip = request.client.host if request.client else None
    await write_audit(
        db,
        event_type="review.job_certified",
        severity="INFO",
        actor_id=UUID(user["sub"]),
        actor_type="user",
        resource_type="assignment",
        resource_id=assignment.id,
        details={"certified_count": certified_count, "dataset_id": str(assignment.dataset_id)},
        ip_address=client_ip,
    )
    await db.commit()

    return ReviewDecisionResponse(
        assignment_id=str(assignment.id),
        status="CERTIFIED",
        message=f"Assignment certified. {certified_count} annotations approved.",
    )


@review_router.post("/jobs/{assignment_id}/reject", response_model=ReviewDecisionResponse)
async def reject_job(
    assignment_id: UUID,
    body: ReviewDecision,
    request: Request,
    user: dict = Depends(require_role(["QA", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(DatasetAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment.status != "SUBMITTED":
        raise HTTPException(status_code=400, detail=f"Assignment status is {assignment.status}, not SUBMITTED")

    stmt = select(Annotation).where(Annotation.dataset_id == assignment.dataset_id)
    annotations = (await db.execute(stmt)).scalars().all()

    rejected_count = 0
    for a in annotations:
        if a.human_labels is not None:
            a.status = AnnotationStatus.REJECTED
            a.qa_reviewer_id = UUID(user["sub"])
            a.review_completed_at = datetime.now(UTC)
            rejected_count += 1

    assignment.status = "ASSIGNED"
    assignment.rejection_reason = body.reason
    assignment.completed_images = 0
    client_ip = request.client.host if request.client else None
    await write_audit(
        db,
        event_type="review.job_rejected",
        severity="WARN",
        actor_id=UUID(user["sub"]),
        actor_type="user",
        resource_type="assignment",
        resource_id=assignment.id,
        details={"rejected_count": rejected_count, "reason": body.reason},
        ip_address=client_ip,
    )
    await db.commit()

    return ReviewDecisionResponse(
        assignment_id=str(assignment.id),
        status="ASSIGNED",
        message=f"Assignment rejected. {rejected_count} annotations returned. Reason: {body.reason or 'None'}",
    )


@review_router.get("/jobs/{assignment_id}/iaa", response_model=IAAMetrics)
async def get_iaa_metrics(
    assignment_id: UUID,
    user: dict = Depends(require_role(["QA", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(DatasetAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    stmt = select(Annotation).where(Annotation.dataset_id == assignment.dataset_id)
    annotations = (await db.execute(stmt)).scalars().all()

    total = len(annotations)
    with_labels = sum(1 for a in annotations if a.human_labels is not None)
    certified = sum(1 for a in annotations if a.is_certified)
    rejected = sum(1 for a in annotations if a.status == AnnotationStatus.REJECTED)

    completeness = (with_labels / total * 100) if total > 0 else 0.0
    accuracy = (certified / with_labels * 100) if with_labels > 0 else 0.0
    overall = (completeness * 0.6 + accuracy * 0.4) if total > 0 else 0.0

    return IAAMetrics(
        assignment_id=str(assignment.id),
        total_annotations=total,
        annotations_with_labels=with_labels,
        annotations_certified=certified,
        annotations_rejected=rejected,
        completeness_pct=round(completeness, 2),
        accuracy_pct=round(accuracy, 2),
        overall_iaa=round(overall, 2),
    )


@review_router.post("/jobs/{assignment_id}/annotations/{annotation_id}/approve")
async def approve_annotation(
    assignment_id: UUID,
    annotation_id: UUID,
    request: Request,
    user: dict = Depends(require_role(["QA", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(DatasetAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    annotation = await db.get(Annotation, annotation_id)
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    if annotation.dataset_id != assignment.dataset_id:
        raise HTTPException(status_code=400, detail="Annotation not in this assignment's dataset")

    annotation.is_certified = True
    annotation.status = AnnotationStatus.CERTIFIED
    annotation.qa_reviewer_id = UUID(user["sub"])
    annotation.review_completed_at = datetime.now(UTC)
    client_ip = request.client.host if request.client else None
    await write_audit(
        db,
        event_type="review.annotation_approved",
        severity="INFO",
        actor_id=UUID(user["sub"]),
        actor_type="user",
        resource_type="annotation",
        resource_id=annotation.id,
        details={"assignment_id": str(assignment_id)},
        ip_address=client_ip,
    )
    await db.commit()

    return {"status": "CERTIFIED", "annotation_id": str(annotation.id)}


@review_router.post("/jobs/{assignment_id}/annotations/{annotation_id}/reject")
async def reject_annotation(
    assignment_id: UUID,
    annotation_id: UUID,
    request: Request,
    user: dict = Depends(require_role(["QA", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(DatasetAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    annotation = await db.get(Annotation, annotation_id)
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    if annotation.dataset_id != assignment.dataset_id:
        raise HTTPException(status_code=400, detail="Annotation not in this assignment's dataset")

    annotation.status = AnnotationStatus.REJECTED
    annotation.qa_reviewer_id = UUID(user["sub"])
    annotation.review_completed_at = datetime.now(UTC)
    client_ip = request.client.host if request.client else None
    await write_audit(
        db,
        event_type="review.annotation_rejected",
        severity="WARN",
        actor_id=UUID(user["sub"]),
        actor_type="user",
        resource_type="annotation",
        resource_id=annotation.id,
        details={"assignment_id": str(assignment_id)},
        ip_address=client_ip,
    )
    await db.commit()

    return {"status": "REJECTED", "annotation_id": str(annotation.id)}
