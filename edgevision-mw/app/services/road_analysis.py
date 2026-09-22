from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation
from app.models.road_annotation import RoadAnnotation
from app.schemas.road import RoadConditionReport


async def analyze_dataset_road_condition(
    db: AsyncSession,
    dataset_id: UUID,
) -> RoadConditionReport:
    result = await db.execute(
        select(RoadAnnotation)
        .join(Annotation, Annotation.id == RoadAnnotation.annotation_id)
        .where(Annotation.dataset_id == dataset_id)
    )
    annotations = result.scalars().all()

    total_images = len(annotations)
    surface_counts: dict[str, int] = {}
    total_potholes = 0
    total_crack_images = 0

    for ra in annotations:
        st = ra.surface_type or "unpaved"
        surface_counts[st] = surface_counts.get(st, 0) + 1

        if ra.instances:
            for inst in ra.instances if isinstance(ra.instances, list) else []:
                class_id = inst.get("class_id") if isinstance(inst, dict) else getattr(inst, "class_id", None)
                if class_id == 1:
                    total_potholes += 1
                elif class_id == 2:
                    total_crack_images += 1

    total = sum(surface_counts.values()) or 1
    surface_breakdown = {k: round(v / total, 4) for k, v in surface_counts.items()}

    crack_ratio = total_crack_images / total if total > 0 else 0
    if crack_ratio > 0.3:
        crack_severity = "high"
    elif crack_ratio > 0.1:
        crack_severity = "medium"
    else:
        crack_severity = "low"

    good_road_pct = surface_breakdown.get("paved", 0)
    pothole_penalty = min(total_potholes * 0.05, 0.5)
    crack_penalty = crack_ratio * 0.3
    condition_score = max(0.0, min(1.0, good_road_pct - pothole_penalty - crack_penalty))

    recommended_action = None
    if condition_score < 0.3:
        recommended_action = "Major road rehabilitation required — resurfacing recommended"
    elif condition_score < 0.6:
        recommended_action = "Maintenance required — pothole patching and crack sealing advised"
    elif condition_score < 0.8 and total_potholes > 0:
        recommended_action = "Spot repairs needed for detected potholes"

    return RoadConditionReport(
        dataset_id=dataset_id,
        total_images=total_images,
        surface_breakdown=surface_breakdown,
        pothole_count=total_potholes,
        pothole_density_per_km2=round(total_potholes / max(total_images * 0.01, 1), 2),
        crack_severity=crack_severity,
        condition_score=round(condition_score, 4),
        recommended_action=recommended_action,
    )
