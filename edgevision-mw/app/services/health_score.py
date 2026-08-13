from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.ingestion import IngestionBatch
from app.models.node import Node
from app.models.studio import DatasetHealthSnapshot, ImageEmbedding


@dataclass
class HealthScore:
    overall: int
    uniqueness: int
    balance: int
    coverage: int
    confidence: int
    action_items: list[dict] = field(default_factory=list)


def hamming_distance(hash1: str, hash2: str) -> int:
    if len(hash1) != len(hash2):
        raise ValueError("Hash strings must be equal length")
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2, strict=False))


def _cosine_distance_matrix(embeddings: list[list[float]]) -> list[float]:
    n = len(embeddings)
    if n < 2:
        return []
    distances = []
    for i in range(n):
        for j in range(i + 1, n):
            dot = sum(a * b for a, b in zip(embeddings[i], embeddings[j], strict=False))
            norm_a = math.sqrt(sum(a * a for a in embeddings[i]))
            norm_b = math.sqrt(sum(b * b for b in embeddings[j]))
            if norm_a == 0 or norm_b == 0:
                distances.append(1.0)
            else:
                cosine_sim = dot / (norm_a * norm_b)
                distances.append(1.0 - cosine_sim)
    return distances


def _gini_coefficient(counts: list[int]) -> float:
    if not counts or sum(counts) == 0:
        return 0.0
    sorted_counts = sorted(counts)
    n = len(sorted_counts)
    total = sum(sorted_counts)
    cumulative = 0.0
    for i, c in enumerate(sorted_counts):
        cumulative += (2 * (i + 1) - n - 1) * c
    return cumulative / (n * total)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> int:
    return max(low, min(high, value))


async def _compute_uniqueness(db: AsyncSession, dataset_pk) -> tuple[int, list[dict]]:
    action_items: list[dict] = []

    result = await db.execute(
        select(ImageEmbedding.embedding, ImageEmbedding.annotation_id)
        .join(Annotation, ImageEmbedding.annotation_id == Annotation.id)
        .where(Annotation.dataset_id == dataset_pk)
        .where(ImageEmbedding.embedding.isnot(None))
    )
    rows = result.all()

    if len(rows) < 2:
        action_items.append(
            {
                "severity": "info",
                "message": "Insufficient embeddings for uniqueness analysis",
                "recommendation": (
                    "Generate embeddings for at least 2 images to enable "
                    "diversity scoring"
                ),
            }
        )
        return 50, action_items

    embeddings = [list(row[0]) for row in rows]
    distances = _cosine_distance_matrix(embeddings)

    if not distances:
        return 50, action_items

    mean_dist = sum(distances) / len(distances)
    variance = sum((d - mean_dist) ** 2 for d in distances) / len(distances)
    std_dev = math.sqrt(variance)

    score = int(_clamp(mean_dist * 100 + std_dev * 50))
    if mean_dist < 0.1:
        action_items.append(
            {
                "severity": "high",
                "message": "High visual redundancy detected in dataset",
                "recommendation": (
                    "Capture additional diverse imagery to reduce near-duplicate "
                    "content"
                ),
            }
        )
    elif mean_dist < 0.2:
        action_items.append(
            {
                "severity": "medium",
                "message": "Moderate visual similarity across images",
                "recommendation": (
                    "Consider capturing from varied angles and lighting conditions"
                ),
            }
        )
    return score, action_items


async def _compute_balance(db: AsyncSession, dataset_pk) -> tuple[int, list[dict]]:
    action_items: list[dict] = []

    result = await db.execute(
        select(Annotation.auto_labels, Annotation.human_labels).where(
            Annotation.dataset_id == dataset_pk
        )
    )
    rows = result.all()

    if not rows:
        action_items.append(
            {
                "severity": "info",
                "message": "No annotations found for balance analysis",
                "recommendation": "Complete annotation of dataset samples",
            }
        )
        return 50, action_items

    class_counter: Counter = Counter()
    for auto_labels, human_labels in rows:
        labels = human_labels if human_labels else auto_labels
        if labels and isinstance(labels, dict):
            cls = labels.get("class")
            if cls:
                class_counter[str(cls)] += 1
        elif auto_labels and isinstance(auto_labels, dict):
            cls = auto_labels.get("class")
            if cls:
                class_counter[str(cls)] += 1

    if not class_counter:
        action_items.append(
            {
                "severity": "medium",
                "message": "No class labels found in annotation data",
                "recommendation": "Verify label extraction from auto_labels/human_labels",
            }
        )
        return 50, action_items

    counts = list(class_counter.values())
    gini = _gini_coefficient(counts)
    score = int(_clamp((1.0 - gini) * 100))

    total = sum(counts)
    for cls, count in class_counter.items():
        pct = (count / total) * 100
        if pct < 5.0:
            action_items.append(
                {
                    "severity": "high",
                    "message": f"Class '{cls}' is severely underrepresented ({pct:.1f}%)",
                    "recommendation": (
                        f"Capture more '{cls}' samples — target at least 5% of dataset"
                    ),
                }
            )
        elif pct < 10.0:
            action_items.append(
                {
                    "severity": "medium",
                    "message": f"Class '{cls}' is underrepresented ({pct:.1f}%)",
                    "recommendation": (
                        f"Increase '{cls}' capture frequency across nodes"
                    ),
                }
            )

    if len(class_counter) < 3:
        action_items.append(
            {
                "severity": "medium",
                "message": f"Only {len(class_counter)} unique classes detected",
                "recommendation": "Expand class coverage through targeted capture missions",
            }
        )

    return score, action_items


async def _compute_coverage(db: AsyncSession, dataset_pk) -> tuple[int, list[dict]]:
    action_items: list[dict] = []
    geo_score = 0
    temporal_score = 0

    result = await db.execute(
        select(Annotation.gps_lat, Annotation.gps_lon).where(
            Annotation.dataset_id == dataset_pk
        )
    )
    gps_rows = result.all()
    grid_cells: set[tuple[int, int]] = set()
    for lat, lon in gps_rows:
        if lat is not None and lon is not None:
            grid_cells.add((int(lat * 100), int(lon * 100)))

    if not grid_cells:
        action_items.append(
            {
                "severity": "medium",
                "message": "No GPS data available for geographic coverage analysis",
                "recommendation": "Enable GPS tagging on capture devices",
            }
        )
        geo_score = 0
    else:
        if len(grid_cells) >= 10:
            geo_score = 100
        elif len(grid_cells) >= 5:
            geo_score = 70
            action_items.append(
                {
                    "severity": "low",
                    "message": f"Moderate geographic spread ({len(grid_cells)} grid cells)",
                    "recommendation": "Expand capture to more geographic locations",
                }
            )
        else:
            geo_score = int(len(grid_cells) * 14)
            action_items.append(
                {
                    "severity": "high",
                    "message": f"Limited geographic spread ({len(grid_cells)} grid cells)",
                    "recommendation": (
                        "Deploy capture missions to at least 5 distinct locations"
                    ),
                }
            )

    batch_result = await db.execute(
        select(IngestionBatch.id)
        .join(Annotation, IngestionBatch.id == Annotation.batch_id)
        .where(Annotation.dataset_id == dataset_pk)
        .where(IngestionBatch.created_at.isnot(None))
    )
    batch_ids = [row[0] for row in batch_result.all()]

    if batch_ids:
        time_result = await db.execute(
            select(IngestionBatch.created_at)
            .where(IngestionBatch.id.in_(batch_ids))
            .order_by(IngestionBatch.created_at)
        )
        timestamps = [row[0] for row in time_result.all() if row[0] is not None]

        if len(timestamps) >= 2:
            span = (timestamps[-1] - timestamps[0]).total_seconds()
            days = span / 86400
            if days >= 30:
                temporal_score = 100
            elif days >= 7:
                temporal_score = 70
                action_items.append(
                    {
                        "severity": "low",
                        "message": f"Temporal spread is {days:.0f} days",
                        "recommendation": (
                            "Extend capture period to at least 30 days for "
                            "temporal diversity"
                        ),
                    }
                )
            else:
                temporal_score = int(max(days / 30 * 100, 10))
                action_items.append(
                    {
                        "severity": "medium",
                        "message": f"Data captured over only {days:.1f} days",
                        "recommendation": (
                            "Collect data across more days to capture varied "
                            "conditions"
                        ),
                    }
                )
        else:
            temporal_score = 30
    else:
        temporal_score = 0

    weather_score = 50

    score = int(_clamp((geo_score * 0.4) + (temporal_score * 0.35) + (weather_score * 0.25)))
    return score, action_items


async def _compute_confidence(db: AsyncSession, dataset_pk) -> tuple[int, list[dict]]:
    action_items: list[dict] = []

    result = await db.execute(
        select(func.avg(Annotation.quality_score)).where(
            Annotation.dataset_id == dataset_pk
        )
    )
    mean_quality = result.scalar()

    if mean_quality is None:
        action_items.append(
            {
                "severity": "info",
                "message": "No quality scores available for confidence analysis",
                "recommendation": "Complete QA review to generate quality scores",
            }
        )
        return 50, action_items

    score = int(_clamp(mean_quality * 100))

    low_q_result = await db.execute(
        select(func.count()).select_from(Annotation).where(
            Annotation.dataset_id == dataset_pk,
            Annotation.quality_score < 0.5,
        )
    )
    low_count = low_q_result.scalar() or 0

    total_result = await db.execute(
        select(func.count()).select_from(Annotation).where(
            Annotation.dataset_id == dataset_pk
        )
    )
    total = total_result.scalar() or 0

    if total > 0:
        low_pct = (low_count / total) * 100
        if low_pct > 20:
            action_items.append(
                {
                    "severity": "high",
                    "message": (
                        f"{low_pct:.1f}% of annotations have quality score below 0.5"
                    ),
                    "recommendation": (
                        "Re-annotate low-quality samples or escalate to senior QA"
                    ),
                }
            )
        elif low_pct > 10:
            action_items.append(
                {
                    "severity": "medium",
                    "message": (
                        f"{low_pct:.1f}% of annotations have quality score below 0.5"
                    ),
                    "recommendation": "Review and improve annotation guidelines",
                }
            )

    return score, action_items


async def _resolve_dataset_pk(db: AsyncSession, dataset_id: str) -> UUID | None:
    result = await db.execute(
        select(Dataset.id).where(Dataset.dataset_id == dataset_id)
    )
    row = result.scalar_one_or_none()
    return row


async def compute_health_score(
    db: AsyncSession, dataset_id: str
) -> HealthScore:
    dataset_pk = await _resolve_dataset_pk(db, dataset_id)
    if dataset_pk is None:
        raise ValueError(f"Dataset '{dataset_id}' not found")

    uniqueness_score, uniqueness_actions = await _compute_uniqueness(db, dataset_pk)
    balance_score, balance_actions = await _compute_balance(db, dataset_pk)
    coverage_score, coverage_actions = await _compute_coverage(db, dataset_pk)
    confidence_score, confidence_actions = await _compute_confidence(db, dataset_pk)

    overall = int(

            uniqueness_score * 0.25
            + balance_score * 0.25
            + coverage_score * 0.25
            + confidence_score * 0.25

    )

    all_actions = uniqueness_actions + balance_actions + coverage_actions + confidence_actions

    snapshot = DatasetHealthSnapshot(
        dataset_id=dataset_pk,
        overall_score=overall,
        uniqueness_score=uniqueness_score,
        balance_score=balance_score,
        coverage_score=coverage_score,
        confidence_score=confidence_score,
        action_items=all_actions,
    )
    db.add(snapshot)
    await db.commit()

    return HealthScore(
        overall=overall,
        uniqueness=uniqueness_score,
        balance=balance_score,
        coverage=coverage_score,
        confidence=confidence_score,
        action_items=all_actions,
    )


async def get_health_history(
    db: AsyncSession, dataset_id: str, days: int = 30
) -> list[DatasetHealthSnapshot]:
    dataset_pk = await _resolve_dataset_pk(db, dataset_id)
    if dataset_pk is None:
        raise ValueError(f"Dataset '{dataset_id}' not found")

    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(DatasetHealthSnapshot)
        .where(DatasetHealthSnapshot.dataset_id == dataset_pk)
        .where(DatasetHealthSnapshot.created_at >= cutoff)
        .order_by(DatasetHealthSnapshot.created_at.desc())
    )
    return list(result.scalars().all())


async def get_class_distribution(
    db: AsyncSession, dataset_id: str
) -> dict[str, dict[str, int | float]]:
    dataset_pk = await _resolve_dataset_pk(db, dataset_id)
    if dataset_pk is None:
        raise ValueError(f"Dataset '{dataset_id}' not found")

    result = await db.execute(
        select(Annotation.auto_labels, Annotation.human_labels).where(
            Annotation.dataset_id == dataset_pk
        )
    )
    rows = result.all()

    class_counter: Counter = Counter()
    total = 0
    for auto_labels, human_labels in rows:
        labels = human_labels if human_labels else auto_labels
        if labels and isinstance(labels, dict):
            cls = labels.get("class")
            if cls:
                class_counter[str(cls)] += 1
                total += 1
        elif auto_labels and isinstance(auto_labels, dict):
            cls = auto_labels.get("class")
            if cls:
                class_counter[str(cls)] += 1
                total += 1

    distribution: dict[str, dict[str, int | float]] = {}
    for cls, count in sorted(class_counter.items(), key=lambda x: -x[1]):
        pct = (count / total * 100) if total > 0 else 0.0
        distribution[cls] = {"count": count, "percentage": round(pct, 2)}

    return distribution


async def get_capture_recommendations(
    db: AsyncSession, dataset_id: str
) -> list[dict]:
    dataset_pk = await _resolve_dataset_pk(db, dataset_id)
    if dataset_pk is None:
        raise ValueError(f"Dataset '{dataset_id}' not found")

    distribution = await get_class_distribution(db, dataset_id)
    if not distribution:
        return []

    total = sum(d["count"] for d in distribution.values())
    avg_pct = 100.0 / len(distribution) if distribution else 0.0
    underrepresented = {
        cls: d for cls, d in distribution.items() if d["percentage"] < avg_pct
    }

    if not underrepresented:
        return []

    node_result = await db.execute(
        select(Node.node_id, Node.district, Node.category, Node.interest_classes)
    )
    nodes = node_result.all()

    node_list = [
        {
            "node_id": n[0],
            "district": n[1],
            "category": n[2],
            "interest_classes": n[3] or [],
        }
        for n in nodes
    ]

    recommendations: list[dict] = []
    for cls, data in underrepresented.items():
        target_count = max(int(total * avg_pct / 100) - data["count"], 1)
        matching_nodes = [
            n for n in node_list if cls in n["interest_classes"]
        ]

        node_targets = []
        if matching_nodes:
            per_node = max(target_count // len(matching_nodes), 1)
            for n in matching_nodes:
                node_targets.append(
                    {
                        "node_id": n["node_id"],
                        "district": n["district"],
                        "target_captures": per_node,
                    }
                )
        else:
            for n in node_list[:3]:
                node_targets.append(
                    {
                        "node_id": n["node_id"],
                        "district": n["district"],
                        "target_captures": target_count,
                    }
                )

        recommendations.append(
            {
                "class": cls,
                "current_count": data["count"],
                "current_percentage": data["percentage"],
                "target_percentage": round(avg_pct, 2),
                "captures_needed": target_count,
                "recommended_nodes": node_targets,
            }
        )

    return sorted(recommendations, key=lambda r: r["captures_needed"], reverse=True)
