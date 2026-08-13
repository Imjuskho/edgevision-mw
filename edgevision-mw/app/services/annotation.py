from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.annotation import Annotation, AnnotationAssignment
from app.models.buyer import User
from app.models.enums import AnnotationStatus
from app.schemas.annotation import (
    AnnotationResponse,
    AnnotatorLeaderboard,
    JobAssignment,
)

logger = get_logger("edgevision.services.annotation")


async def auto_assign_jobs(
    db: AsyncSession, count: int = 10, target_annotator: UUID | None = None
) -> list[JobAssignment]:
    # Use SELECT FOR UPDATE to lock rows and prevent double-assignment
    pending_result = await db.execute(
        select(Annotation)
        .where(Annotation.status == AnnotationStatus.PENDING)
        .where(Annotation.annotator_id.is_(None))
        .order_by(Annotation.created_at.asc())
        .limit(count)
        .with_for_update(skip_locked=True)  # Skip rows locked by other transactions
    )
    pending_annotations = pending_result.scalars().all()
    if not pending_annotations:
        return []

    # Get available annotators, ordered by current workload (least busy first)
    annotator_query = (
        select(User)
        .where(User.role == "ANNOTATOR", User.is_active.is_(True))
        .order_by(User.id)
    )
    if target_annotator:
        annotator_query = annotator_query.where(User.id == target_annotator)

    annotators_result = await db.execute(annotator_query)
    annotators = annotators_result.scalars().all()
    if not annotators:
        return []

    # Get current assignment counts for workload balancing
    from sqlalchemy import func as sqlfunc
    workload_result = await db.execute(
        select(
            AnnotationAssignment.annotator_id,
            sqlfunc.count(AnnotationAssignment.id).label("active_count"),
        )
        .where(AnnotationAssignment.is_active.is_(True))
        .group_by(AnnotationAssignment.annotator_id)
    )
    workload = {row.annotator_id: row.active_count for row in workload_result.all()}

    # Sort annotators by workload (least busy first)
    annotators = sorted(annotators, key=lambda a: workload.get(a.id, 0))

    assignments: list[JobAssignment] = []
    now = datetime.now(UTC)

    for idx, annotation in enumerate(pending_annotations):
        annotator = annotators[idx % len(annotators)]

        assignment = AnnotationAssignment(
            id=uuid4(),
            annotation_id=annotation.id,
            annotator_id=annotator.id,
            assigned_at=now,
            deadline=now + timedelta(hours=48),
            is_active=True,
        )
        db.add(assignment)

        annotation.annotator_id = annotator.id
        annotation.status = AnnotationStatus.HUMAN_REVIEW
        annotation.review_started_at = now

        assignments.append(
            JobAssignment(
                annotation_id=annotation.id,
                annotator_id=annotator.id,
                assigned_at=now,
                deadline=now + timedelta(hours=48),
            )
        )

    await db.commit()
    return assignments


async def submit_labels(
    db: AsyncSession,
    annotation_id: UUID,
    annotator_id: UUID,
    labels: dict,
    quality_score: float = 1.0,
) -> AnnotationResponse:
    trace_id = str(uuid4())
    logger.info("svc_labels_start", trace_id=trace_id, annotation_id=str(annotation_id), annotator_id=str(annotator_id))

    # FOR UPDATE to prevent concurrent submission races (B1)
    result = await db.execute(
        select(Annotation)
        .where(Annotation.id == annotation_id)
        .with_for_update()
    )
    annotation = result.scalar_one_or_none()
    if annotation is None:
        logger.warning("svc_labels_not_found", trace_id=trace_id, annotation_id=str(annotation_id))
        raise ValueError("Annotation not found")

    logger.info("svc_labels_found", trace_id=trace_id, image_path=annotation.image_path, current_status=annotation.status)

    # Owner check: only the assigned annotator may submit labels
    if annotation.annotator_id != annotator_id:
        logger.warning("svc_labels_unauthorized", trace_id=trace_id, owner=str(annotation.annotator_id), submitter=str(annotator_id))
        raise ValueError("Not authorized: you are not assigned to this annotation")

    # Status guard: only HUMAN_REVIEW annotations accept labels (B1)
    current_status = annotation.status.value if hasattr(annotation.status, "value") else annotation.status
    if current_status != AnnotationStatus.HUMAN_REVIEW.value:
        logger.warning("svc_labels_wrong_status", trace_id=trace_id, actual=current_status, expected=AnnotationStatus.HUMAN_REVIEW.value)
        raise ValueError(
            f"Cannot submit labels on annotation in {current_status} status; "
            f"expected {AnnotationStatus.HUMAN_REVIEW.value}"
        )

    annotation.human_labels = labels
    annotation.quality_score = quality_score
    annotation.status = AnnotationStatus.QA_REVIEW
    await db.commit()
    logger.info("svc_labels_committed", trace_id=trace_id, annotation_id=str(annotation_id), new_status=AnnotationStatus.QA_REVIEW.value)

    await db.refresh(annotation)

    return AnnotationResponse(
        id=annotation.id,
        status=annotation.status.value if hasattr(annotation.status, 'value') else annotation.status,
        iaa_score=annotation.iaa_score,
        quality_score=annotation.quality_score,
        annotator_id=annotation.annotator_id,
        qa_reviewer_id=annotation.qa_reviewer_id,
    )


async def submit_review(
    db: AsyncSession,
    annotation_id: UUID,
    reviewer_id: UUID,
    review_labels: dict,
    category: str = "object_detection",
) -> AnnotationResponse:
    # FOR UPDATE to prevent concurrent review races (B1)
    result = await db.execute(
        select(Annotation)
        .where(Annotation.id == annotation_id)
        .with_for_update()
    )
    annotation = result.scalar_one_or_none()
    if annotation is None:
        raise ValueError("Annotation not found")

    # Status guard: only QA_REVIEW annotations accept reviews (B1)
    current_status = annotation.status.value if hasattr(annotation.status, "value") else annotation.status
    if current_status != AnnotationStatus.QA_REVIEW.value:
        raise ValueError(
            f"Cannot submit review on annotation in {current_status} status; "
            f"expected {AnnotationStatus.QA_REVIEW.value}"
        )

    # Self-assignment protection: reviewer cannot review own annotation (B2)
    if annotation.annotator_id == reviewer_id:
        raise ValueError(
            "QA reviewer cannot review their own annotation"
        )

    annotation.qa_labels = review_labels
    annotation.qa_reviewer_id = reviewer_id

    # Compute IAA server-side instead of trusting caller
    iaa_score = calculate_iaa(
        annotation.human_labels or {},
        review_labels,
        category=category,
    )
    annotation.iaa_score = iaa_score
    annotation.review_completed_at = datetime.now(UTC)

    if iaa_score >= 0.96:
        annotation.status = AnnotationStatus.CERTIFIED
        annotation.is_certified = True
    else:
        annotation.status = AnnotationStatus.REJECTED

    await db.commit()
    await db.refresh(annotation)

    return AnnotationResponse(
        id=annotation.id,
        status=annotation.status.value if hasattr(annotation.status, 'value') else annotation.status,
        iaa_score=annotation.iaa_score,
        quality_score=annotation.quality_score,
        annotator_id=annotation.annotator_id,
        qa_reviewer_id=annotation.qa_reviewer_id,
    )


async def get_leaderboard(
    db: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[AnnotatorLeaderboard]:
    if start_date is None:
        start_date = datetime.now(UTC) - timedelta(days=7)
    if end_date is None:
        end_date = datetime.now(UTC)

    result = await db.execute(
        select(
            Annotation.annotator_id,
            User.full_name,
            func.count(Annotation.id).label("total_annotated"),
            func.avg(Annotation.quality_score).label("avg_quality"),
            func.avg(Annotation.iaa_score).label("avg_iaa"),
            func.count(Annotation.id).label("weekly_count"),
        )
        .join(User, Annotation.annotator_id == User.id)
        .where(
            Annotation.annotator_id.isnot(None),
            Annotation.review_completed_at >= start_date,
            Annotation.review_completed_at <= end_date,
        )
        .group_by(Annotation.annotator_id, User.full_name)
        .order_by(func.avg(Annotation.iaa_score).desc().nullslast())
    )
    rows = result.all()

    return [
        AnnotatorLeaderboard(
            annotator_id=row.annotator_id,
            full_name=row.full_name,
            total_annotated=row.total_annotated,
            avg_quality_score=round(float(row.avg_quality or 0), 3),
            iaa_score=round(float(row.avg_iaa or 0), 3),
            weekly_count=row.weekly_count,
        )
        for row in rows
    ]


def calculate_iaa(original_labels: dict, review_labels: dict, category: str = "object_detection") -> float:
    """Calculate inter-annotator agreement.

    For object detection: uses IoU-based agreement on bounding boxes.
    For biometric/classification: uses Cohen's Kappa.
    """
    if not original_labels or not review_labels:
        return 0.0

    if category in ("biometric", "medical", "classification"):
        return _cohens_kappa(original_labels, review_labels)
    return _iou_agreement(original_labels, review_labels)


def _cohens_kappa(labels_a: dict, labels_b: dict) -> float:
    """Cohen's Kappa for categorical agreement."""
    all_keys = set(labels_a.keys()) | set(labels_b.keys())
    if not all_keys:
        return 0.0

    # Count agreements and disagreements
    n = len(all_keys)
    agreements = sum(1 for k in all_keys if labels_a.get(k) == labels_b.get(k))
    po = agreements / n  # observed agreement

    # Calculate expected agreement by chance
    categories_a = {}
    categories_b = {}
    for k in all_keys:
        va = str(labels_a.get(k, ""))
        vb = str(labels_b.get(k, ""))
        categories_a[va] = categories_a.get(va, 0) + 1
        categories_b[vb] = categories_b.get(vb, 0) + 1

    pe = sum((categories_a.get(c, 0) / n) * (categories_b.get(c, 0) / n)
             for c in set(categories_a.keys()) | set(categories_b.keys()))

    if pe == 1.0:
        return 1.0

    kappa = (po - pe) / (1 - pe)
    return round(max(0.0, min(1.0, kappa)), 4)


def _iou_agreement(labels_a: dict, labels_b: dict) -> float:
    """IoU-based agreement for bounding box detection."""
    if not labels_a or not labels_b:
        return 0.0

    # Try to extract bbox from labels
    bboxes_a = []
    bboxes_b = []

    for _key, val in labels_a.items():
        if isinstance(val, dict) and "bbox" in val:
            bboxes_a.append(val["bbox"])
        elif isinstance(val, list) and len(val) == 4:
            bboxes_a.append(val)

    for _key, val in labels_b.items():
        if isinstance(val, dict) and "bbox" in val:
            bboxes_b.append(val["bbox"])
        elif isinstance(val, list) and len(val) == 4:
            bboxes_b.append(val)

    if not bboxes_a and not bboxes_b:
        # Fall back to key-value comparison
        all_keys = set(labels_a.keys()) | set(labels_b.keys())
        if not all_keys:
            return 0.0
        matches = sum(1 for k in all_keys if labels_a.get(k) == labels_b.get(k))
        return round(matches / len(all_keys), 4)

    if not bboxes_a or not bboxes_b:
        return 0.0

    # Compute mean IoU across matched boxes
    total_iou = 0.0
    matched = 0
    for ba in bboxes_a:
        best_iou = 0.0
        for bb in bboxes_b:
            iou = _compute_iou(ba, bb)
            best_iou = max(best_iou, iou)
        total_iou += best_iou
        matched += 1

    return round(total_iou / max(matched, 1), 4)


def _compute_iou(box_a: list[float], box_b: list[float]) -> float:
    """Compute Intersection over Union for two [x, y, w, h] boxes."""
    if len(box_a) != 4 or len(box_b) != 4:
        return 0.0

    # Convert from [x, y, w, h] to [x1, y1, x2, y2]
    a_x1, a_y1 = box_a[0], box_a[1]
    a_x2, a_y2 = box_a[0] + box_a[2], box_a[1] + box_a[3]
    b_x1, b_y1 = box_b[0], box_b[1]
    b_x2, b_y2 = box_b[0] + box_b[2], box_b[1] + box_b[3]

    # Intersection
    inter_x1 = max(a_x1, b_x1)
    inter_y1 = max(a_y1, b_y1)
    inter_x2 = min(a_x2, b_x2)
    inter_y2 = min(a_y2, b_y2)

    inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)

    # Union
    area_a = max(0, a_x2 - a_x1) * max(0, a_y2 - a_y1)
    area_b = max(0, b_x2 - b_x1) * max(0, b_y2 - b_y1)
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0

    return inter_area / union_area


async def get_pending_jobs(
    db: AsyncSession, annotator_id: UUID
) -> list[dict]:
    result = await db.execute(
        select(Annotation)
        .where(
            Annotation.annotator_id == annotator_id,
            Annotation.status.in_([
                AnnotationStatus.HUMAN_REVIEW,
                AnnotationStatus.AUTO_LABELED,
            ]),
        )
        .order_by(Annotation.created_at.asc())
    )
    annotations = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "batch_id": str(a.batch_id),
            "image_path": a.image_path,
            "status": a.status.value if hasattr(a.status, "value") else a.status,
            "auto_labels": a.auto_labels,
            "created_at": a.created_at.isoformat(),
        }
        for a in annotations
    ]


async def get_job_detail(db: AsyncSession, annotation_id: UUID) -> dict | None:
    result = await db.execute(
        select(Annotation).where(Annotation.id == annotation_id)
    )
    annotation = result.scalar_one_or_none()
    if annotation is None:
        return None
    return {
        "id": str(annotation.id),
        "batch_id": str(annotation.batch_id),
        "image_path": annotation.image_path,
        "detected_objects": annotation.detected_objects,
        "auto_labels": annotation.auto_labels,
        "human_labels": annotation.human_labels,
        "qa_labels": annotation.qa_labels,
        "status": annotation.status.value if hasattr(annotation.status, "value") else annotation.status,
        "quality_score": annotation.quality_score,
        "iaa_score": annotation.iaa_score,
        "annotator_id": str(annotation.annotator_id) if annotation.annotator_id else None,
        "qa_reviewer_id": str(annotation.qa_reviewer_id) if annotation.qa_reviewer_id else None,
        "is_certified": annotation.is_certified,
        "created_at": annotation.created_at.isoformat(),
    }


async def reassign_rejected(
    db: AsyncSession, annotation_id: UUID
) -> AnnotationResponse:
    """Reset a REJECTED annotation back to PENDING for rework (H9)."""
    result = await db.execute(
        select(Annotation)
        .where(Annotation.id == annotation_id)
        .with_for_update()
    )
    annotation = result.scalar_one_or_none()
    if annotation is None:
        raise ValueError("Annotation not found")

    current_status = annotation.status.value if hasattr(annotation.status, "value") else annotation.status
    if current_status != AnnotationStatus.REJECTED.value:
        raise ValueError(
            f"Cannot reassign annotation in {current_status} status; "
            f"expected {AnnotationStatus.REJECTED.value}"
        )

    annotation.status = AnnotationStatus.PENDING
    annotation.human_labels = None
    annotation.qa_labels = None
    annotation.qa_reviewer_id = None
    annotation.annotator_id = None
    annotation.iaa_score = None
    annotation.is_certified = False
    annotation.review_started_at = None
    annotation.review_completed_at = None
    await db.commit()
    await db.refresh(annotation)

    return AnnotationResponse(
        id=annotation.id,
        status=annotation.status.value if hasattr(annotation.status, 'value') else annotation.status,
        iaa_score=annotation.iaa_score,
        quality_score=annotation.quality_score,
        annotator_id=annotation.annotator_id,
        qa_reviewer_id=annotation.qa_reviewer_id,
    )
