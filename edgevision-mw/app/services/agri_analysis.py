from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agri_annotation import AgriAnnotation
from app.models.annotation import Annotation
from app.schemas.agri import AgriAnalysisReport


async def analyze_dataset_agri_condition(
    db: AsyncSession,
    dataset_id: UUID,
) -> AgriAnalysisReport:
    result = await db.execute(
        select(AgriAnnotation)
        .join(Annotation, Annotation.id == AgriAnnotation.annotation_id)
        .where(Annotation.dataset_id == dataset_id)
    )
    annotations = result.scalars().all()

    total_images = len(annotations)
    crop_counts: dict[str, int] = {}
    health_counts: dict[str, int] = {}
    weed_images = 0
    pest_images = 0
    healthy_count = 0

    for aa in annotations:
        ct = aa.crop_type or "maize"
        crop_counts[ct] = crop_counts.get(ct, 0) + 1

        hs = aa.health_status or "healthy"
        health_counts[hs] = health_counts.get(hs, 0) + 1

        if hs == "healthy":
            healthy_count += 1
        if hs == "weed_infestation":
            weed_images += 1
        if hs == "pest_infested":
            pest_images += 1

    total = total_images or 1
    crop_breakdown = {k: round(v / total, 4) for k, v in crop_counts.items()}
    health_breakdown = {k: round(v / total, 4) for k, v in health_counts.items()}

    healthy_ratio = healthy_count / total
    severe_conditions = sum(
        health_counts.get(h, 0) for h in ("diseased", "pest_infested", "water_logged", "drought_stressed")
    )
    severe_penalty = severe_conditions / total * 0.5
    health_score = max(0.0, min(1.0, healthy_ratio - severe_penalty))

    weed_ratio = weed_images / total if total > 0 else 0
    if weed_ratio > 0.3:
        weed_pressure = "high"
    elif weed_ratio > 0.1:
        weed_pressure = "medium"
    else:
        weed_pressure = "low"

    pest_ratio = pest_images / total if total > 0 else 0
    if pest_ratio > 0.25:
        pest_risk = "high"
    elif pest_ratio > 0.08:
        pest_risk = "medium"
    else:
        pest_risk = "low"

    recommended_action = None
    if health_score < 0.3:
        recommended_action = "Crop failure risk critical — immediate intervention required; consider irrigation, pest control, and soil amendment"
    elif health_score < 0.6:
        if weed_pressure == "high" and pest_risk == "high":
            recommended_action = (
                "Integrated pest and weed management needed — apply herbicides and pesticides, monitor crop recovery"
            )
        elif weed_pressure == "high":
            recommended_action = "Weed control recommended — manual weeding or herbicide application advised"
        elif pest_risk == "high":
            recommended_action = (
                "Pest control recommended — apply appropriate pesticides and monitor for further spread"
            )
        else:
            recommended_action = (
                "Moderate crop stress detected — irrigation likely needed, consider nutrient supplementation"
            )
    elif health_score < 0.8 and (weed_images > 0 or pest_images > 0):
        recommended_action = "Spot treatment needed for detected weed or pest hotspots"

    return AgriAnalysisReport(
        dataset_id=dataset_id,
        total_images=total_images,
        crop_breakdown=crop_breakdown,
        health_breakdown=health_breakdown,
        health_score=round(health_score, 4),
        weed_pressure=weed_pressure,
        pest_risk=pest_risk,
        recommended_action=recommended_action,
    )
