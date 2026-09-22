"""Helpers for dataset-level batch inference (prelabel / road segmentation)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation
from app.models.road_annotation import RoadAnnotation
from app.services.dataset_sync import resolve_dataset


def _has_detection_labels(ann: Annotation) -> bool:
    if ann.human_labels is not None:
        return True
    detected = ann.detected_objects or {}
    objects = detected.get("objects") if isinstance(detected, dict) else None
    if isinstance(objects, list) and len(objects) > 0:
        return True
    auto = ann.auto_labels or {}
    labels = auto.get("labels") if isinstance(auto, dict) else None
    return isinstance(labels, list) and len(labels) > 0


async def _road_annotation_map(db: AsyncSession, annotation_ids: list[UUID]) -> dict[UUID, RoadAnnotation]:
    if not annotation_ids:
        return {}
    rows = (
        (await db.execute(select(RoadAnnotation).where(RoadAnnotation.annotation_id.in_(annotation_ids))))
        .scalars()
        .all()
    )
    return {ra.annotation_id: ra for ra in rows}


async def resolve_batch_annotation_ids(
    db: AsyncSession,
    dataset_id: str,
    *,
    image_ids: list[UUID] | None = None,
    scope: str = "remaining",
    mode: str = "detection",
    force: bool = False,
) -> tuple[list[UUID], int]:
    """Return annotation IDs to process and how many were skipped."""
    ds = await resolve_dataset(db, dataset_id)
    if ds is None:
        raise ValueError(f"Dataset not found: {dataset_id}")

    stmt = select(Annotation).where(Annotation.dataset_id == ds.id).order_by(Annotation.image_index)
    if image_ids:
        stmt = stmt.where(Annotation.id.in_(image_ids))

    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return [], 0

    road_by_ann: dict[UUID, RoadAnnotation] = {}
    if mode == "road":
        road_by_ann = await _road_annotation_map(db, [a.id for a in rows])

    to_process: list[UUID] = []
    skipped = 0

    for ann in rows:
        if mode == "detection":
            if ann.human_labels is not None:
                skipped += 1
                continue
            if scope == "remaining" and not force and _has_detection_labels(ann):
                skipped += 1
                continue
        elif mode == "road":
            ra = road_by_ann.get(ann.id)
            if ra is not None:
                if ra.reviewed and not force:
                    skipped += 1
                    continue
                if scope == "remaining" and not force:
                    skipped += 1
                    continue
        else:
            raise ValueError(f"Unknown batch mode: {mode}")

        to_process.append(ann.id)

    return to_process, skipped
