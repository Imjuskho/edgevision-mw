from __future__ import annotations

import logging
import math
import os
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.federated_learning import FLSyncRound, FLWeightUpdate, FLModelDistribution

logger = logging.getLogger(__name__)

# Minimum fraction of target contributors required to proceed with aggregation
MIN_PARTICIPATION_FRACTION = 0.5


async def create_sync_round(
    db: AsyncSession,
    model_type: str,
    base_model_version: str = "v1",
    target_contributors: int = 3,
    noise_multiplier: float = 0.1,
) -> FLSyncRound:
    fl_round = FLSyncRound(
        id=str(uuid4()),
        model_type=model_type,
        base_model_version=base_model_version,
        status="COLLECTING",
        target_contributors=target_contributors,
        noise_multiplier=noise_multiplier,
        config={"created_at": datetime.now(UTC).isoformat()},
    )
    db.add(fl_round)
    await db.commit()
    return fl_round


async def submit_weight_update(
    db: AsyncSession,
    round_id: str | None,
    node_id: str,
    num_samples: int = 0,
    local_loss: float | None = None,
    local_accuracy: float | None = None,
    artifact_path: str | None = None,
) -> FLWeightUpdate:
    if round_id is None:
        result = await db.execute(
            select(FLSyncRound)
            .where(FLSyncRound.status == "COLLECTING")
            .order_by(FLSyncRound.created_at.desc())
            .limit(1)
        )
        fl_round = result.scalar_one_or_none()
        if fl_round is None:
            raise ValueError("No active COLLECTING round")
        round_id = fl_round.id

    update = FLWeightUpdate(
        id=str(uuid4()),
        round_id=round_id,
        node_id=node_id,
        num_samples=num_samples,
        local_loss=local_loss,
        local_accuracy=local_accuracy,
        artifact_path=artifact_path,
        status="UPLOADED",
        submitted_at=datetime.now(UTC),
    )
    db.add(update)

    result = await db.execute(
        select(func.count(FLWeightUpdate.id)).where(FLWeightUpdate.round_id == round_id)
    )
    count = result.scalar() or 0

    round_result = await db.execute(select(FLSyncRound).where(FLSyncRound.id == round_id).with_for_update())
    fl_round = round_result.scalar_one_or_none()
    if fl_round:
        fl_round.num_contributors = count + 1

    await db.commit()
    return update


async def close_round(db: AsyncSession, round_id: str) -> FLSyncRound:
    result = await db.execute(select(FLSyncRound).where(FLSyncRound.id == round_id).with_for_update())
    fl_round = result.scalar_one_or_none()
    if fl_round is None:
        raise ValueError(f"Round {round_id} not found")
    fl_round.status = "AGGREGATING"
    await db.commit()
    return fl_round


async def aggregate_weights(db: AsyncSession, round_id: str, method: str = "fedavg") -> dict:
    result = await db.execute(select(FLSyncRound).where(FLSyncRound.id == round_id).with_for_update())
    fl_round = result.scalar_one_or_none()
    if fl_round is None:
        raise ValueError(f"Round {round_id} not found")

    updates_result = await db.execute(
        select(FLWeightUpdate).where(
            FLWeightUpdate.round_id == round_id,
            FLWeightUpdate.status == "UPLOADED",
        )
    )
    updates = updates_result.scalars().all()

    if not updates:
        fl_round.status = "FAILED"
        fl_round.error_message = "No weight updates to aggregate"
        await db.commit()
        raise ValueError("No weight updates to aggregate")

    # Validate contributor participation threshold
    min_required = max(1, int(math.ceil(fl_round.target_contributors * MIN_PARTICIPATION_FRACTION)))
    if len(updates) < min_required:
        fl_round.status = "FAILED"
        fl_round.error_message = (
            f"Insufficient contributors: {len(updates)}/{fl_round.target_contributors} "
            f"(minimum {min_required} required, {MIN_PARTICIPATION_FRACTION*100:.0f}% participation)"
        )
        await db.commit()
        return {
            "error": fl_round.error_message,
            "round_id": round_id,
            "contributors": len(updates),
            "target_contributors": fl_round.target_contributors,
            "min_required": min_required,
            "status": "FAILED",
        }

    total_samples = sum(u.num_samples for u in updates)
    weighted_loss = 0.0
    weighted_accuracy = 0.0
    contributors = 0

    for u in updates:
        weight = u.num_samples / max(total_samples, 1)
        if u.local_loss is not None:
            weighted_loss += u.local_loss * weight
        if u.local_accuracy is not None:
            weighted_accuracy += u.local_accuracy * weight
        contributors += 1

    noise = 0.0
    if fl_round.noise_multiplier > 0 and total_samples > 0:
        sensitivity = 1.0 / total_samples
        noise = float(np.random.normal(0, fl_round.noise_multiplier * sensitivity))

    aggregated_version = f"fl-{fl_round.model_type}-{round_id[:8]}"
    fl_round.aggregated_model_version = aggregated_version
    fl_round.global_loss = round(weighted_loss + noise, 6)
    fl_round.global_accuracy = round(weighted_accuracy, 4)
    fl_round.num_contributors = contributors
    fl_round.status = "COMPLETED"
    fl_round.completed_at = datetime.now(UTC)

    for u in updates:
        u.status = "AGGREGATED"

    await db.commit()

    return {
        "round_id": round_id,
        "contributors": contributors,
        "total_samples": total_samples,
        "global_loss": fl_round.global_loss,
        "global_accuracy": fl_round.global_accuracy,
        "noise_added": round(noise, 8),
        "aggregated_version": aggregated_version,
    }


async def distribute_model(
    db: AsyncSession, round_id: str, model_version: str, artifact_path: str
) -> list[FLModelDistribution]:
    result = await db.execute(select(FLSyncRound).where(FLSyncRound.id == round_id))
    fl_round = result.scalar_one_or_none()
    if fl_round is None:
        raise ValueError(f"Round {round_id} not found")

    updates_result = await db.execute(
        select(FLWeightUpdate.node_id).where(FLWeightUpdate.round_id == round_id).distinct()
    )
    node_ids = [r[0] for r in updates_result.all()]

    distributions = []
    for node_id in node_ids:
        dist = FLModelDistribution(
            id=str(uuid4()),
            round_id=round_id,
            node_id=node_id,
            model_version=model_version,
            artifact_path=artifact_path,
            status="SENT",
            sent_at=datetime.now(UTC),
        )
        db.add(dist)
        distributions.append(dist)

    await db.commit()
    return distributions


async def get_round_status(db: AsyncSession, round_id: str) -> dict | None:
    result = await db.execute(select(FLSyncRound).where(FLSyncRound.id == round_id))
    fl_round = result.scalar_one_or_none()
    if fl_round is None:
        return None

    updates_result = await db.execute(
        select(FLWeightUpdate).where(FLWeightUpdate.round_id == round_id)
    )
    updates = updates_result.scalars().all()

    return {
        "round_id": fl_round.id,
        "model_type": fl_round.model_type,
        "status": fl_round.status,
        "num_contributors": fl_round.num_contributors,
        "target_contributors": fl_round.target_contributors,
        "global_loss": fl_round.global_loss,
        "global_accuracy": fl_round.global_accuracy,
        "contributors": [
            {"node_id": u.node_id, "status": u.status, "num_samples": u.num_samples, "local_loss": u.local_loss}
            for u in updates
        ],
    }


async def get_fl_overview(db: AsyncSession) -> dict:
    total_result = await db.execute(select(func.count(FLSyncRound.id)))
    total_rounds = total_result.scalar() or 0

    active_result = await db.execute(
        select(func.count(FLSyncRound.id)).where(FLSyncRound.status.in_(["COLLECTING", "AGGREGATING"]))
    )
    active_rounds = active_result.scalar() or 0

    contributors_result = await db.execute(select(func.count(func.distinct(FLWeightUpdate.node_id))))
    total_contributors = contributors_result.scalar() or 0

    return {
        "total_rounds": total_rounds,
        "active_rounds": active_rounds,
        "total_contributors": total_contributors,
    }


def aggregate_weight_tensors(
    weight_paths: list[str],
    sample_counts: list[int],
    epsilon: float = 1.0,
    delta: float = 1e-5,
) -> dict[str, np.ndarray]:
    """Perform FedAvg over numpy weight files with differential privacy noise.

    Args:
        weight_paths: Paths to .npy or .npz files, one per contributor.
        sample_counts: Number of training samples per contributor (must match length).
        epsilon: Privacy budget for Gaussian DP (smaller = more private).
        delta: Failure probability for (epsilon, delta)-DP.

    Returns:
        Dictionary mapping layer names to averaged numpy arrays.
    """
    if len(weight_paths) != len(sample_counts):
        raise ValueError("weight_paths and sample_counts must have the same length")
    if not weight_paths:
        raise ValueError("At least one weight path is required")

    total_samples = sum(sample_counts)
    if total_samples == 0:
        raise ValueError("Total sample count must be greater than zero")

    aggregated: dict[str, np.ndarray] = {}
    contributor_tensors: dict[str, list[tuple[np.ndarray, int]]] = {}

    for path, n_samples in zip(weight_paths, sample_counts):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Weight file not found: {path}")

        if path.endswith(".npz"):
            data = dict(np.load(path, allow_pickle=False))
        else:
            data = {"__single__": np.load(path, allow_pickle=False)}

        for key, tensor in data.items():
            if not np.all(np.isfinite(tensor)):
                raise ValueError(f"Non-finite values in layer '{key}' of {path}")
            if key not in contributor_tensors:
                contributor_tensors[key] = []
            contributor_tensors[key].append((tensor, n_samples))

    for key, contributions in contributor_tensors.items():
        weighted_sum = np.zeros_like(contributions[0][0], dtype=np.float64)
        for tensor, n in contributions:
            weighted_sum += tensor.astype(np.float64) * (n / total_samples)

        # Gaussian mechanism for differential privacy
        # Sensitivity = max_change_per_sample = 1/total_samples (normalized)
        sensitivity = 1.0 / total_samples
        sigma = sensitivity * math.sqrt(2.0 * math.log(1.25 / delta)) / epsilon if epsilon > 0 else 0.0
        if sigma > 0:
            noise = np.random.normal(0, sigma, size=weighted_sum.shape)
            weighted_sum += noise

        aggregated[key] = weighted_sum.astype(np.float32)

    return aggregated


def validate_weight_update(
    artifact_path: str,
    expected_layers: int | None = None,
    max_file_size_mb: float = 500.0,
    norm_threshold: float = 10.0,
) -> dict:
    """Validate a submitted weight update file.

    Checks:
    - File exists and is readable
    - Contains numpy arrays with finite values
    - File size is within reasonable bounds
    - Number of layers matches expectation (if provided)
    - L2 norm of the update is within bounds

    Returns:
        Dict with validation_score (0.0-1.0), is_outlier flag, and details.
    """
    result = {
        "valid": False,
        "validation_score": 0.0,
        "is_outlier": False,
        "details": {},
    }

    if not os.path.isfile(artifact_path):
        result["details"]["error"] = f"File not found: {artifact_path}"
        return result

    # File size check
    file_size_bytes = os.path.getsize(artifact_path)
    file_size_mb = file_size_bytes / (1024 * 1024)
    result["details"]["file_size_mb"] = round(file_size_mb, 3)

    if file_size_mb > max_file_size_mb:
        result["details"]["error"] = f"File too large: {file_size_mb:.1f}MB > {max_file_size_mb}MB"
        result["is_outlier"] = True
        return result

    if file_size_mb < 0.001:
        result["details"]["error"] = "File too small to contain valid weights"
        result["is_outlier"] = True
        return result

    try:
        if artifact_path.endswith(".npz"):
            data = dict(np.load(artifact_path, allow_pickle=False))
        else:
            arr = np.load(artifact_path, allow_pickle=False)
            if arr.ndim == 0:
                data = {"__single__": arr}
            else:
                data = {"__single__": arr}
    except Exception as e:
        result["details"]["error"] = f"Failed to load numpy file: {e}"
        return result

    num_layers = len(data)
    result["details"]["num_layers"] = num_layers

    # Check for finite values
    has_nan = False
    has_inf = False
    norms = []
    total_params = 0

    for key, tensor in data.items():
        if not isinstance(tensor, np.ndarray):
            continue
        total_params += tensor.size
        if not np.all(np.isfinite(tensor)):
            nan_count = int(np.sum(np.isnan(tensor)))
            inf_count = int(np.sum(np.isinf(tensor)))
            if nan_count > 0:
                has_nan = True
                result["details"][f"{key}_nan_count"] = nan_count
            if inf_count > 0:
                has_inf = True
                result["details"][f"{key}_inf_count"] = inf_count

        norms.append(float(np.linalg.norm(tensor)))

    result["details"]["total_params"] = total_params
    result["details"]["layer_norms"] = [round(n, 4) for n in norms]

    if has_nan or has_inf:
        result["is_outlier"] = True
        result["details"]["error"] = "Weight file contains NaN or Inf values"
        return result

    # Compute validation score
    score = 1.0

    # Penalize for file size reasonableness (sweet spot: 1-100 MB)
    if file_size_mb < 0.1:
        score *= 0.5
    elif file_size_mb > 200:
        score *= 0.7

    # Penalize layer count mismatch
    if expected_layers is not None and num_layers != expected_layers:
        layer_ratio = min(num_layers, expected_layers) / max(num_layers, expected_layers)
        score *= max(0.3, layer_ratio)

    # Check norm range — extreme norms suggest corrupted training
    if norms:
        mean_norm = float(np.mean(norms))
        result["details"]["mean_norm"] = round(mean_norm, 4)
        if mean_norm > norm_threshold:
            score *= 0.4
            result["is_outlier"] = True
        elif mean_norm > norm_threshold * 0.7:
            score *= 0.8

    result["validation_score"] = round(min(1.0, max(0.0, score)), 4)
    result["valid"] = True
    return result


def compute_federated_accuracy(
    aggregated_metrics: dict,
    baseline_accuracy: float,
) -> dict:
    """Compare aggregated model accuracy against a baseline.

    Args:
        aggregated_metrics: Dict from aggregate_weights() output containing global_accuracy.
        baseline_accuracy: The baseline model accuracy to compare against.

    Returns:
        Dict with improvement_delta, baseline, aggregated, and whether it improved.
    """
    agg_accuracy = aggregated_metrics.get("global_accuracy")
    if agg_accuracy is None:
        return {
            "improvement_delta": None,
            "baseline": baseline_accuracy,
            "aggregated": None,
            "improved": False,
            "error": "No aggregated accuracy available",
        }

    delta = round(agg_accuracy - baseline_accuracy, 4)
    return {
        "improvement_delta": delta,
        "baseline": baseline_accuracy,
        "aggregated": agg_accuracy,
        "improved": delta > 0,
        "relative_improvement_pct": round((delta / max(abs(baseline_accuracy), 1e-8)) * 100, 2),
    }


async def update_weight_validation(
    db: AsyncSession,
    update_id: str,
    artifact_path: str,
    expected_layers: int | None = None,
) -> FLWeightUpdate:
    """Validate a weight update and persist validation results to the database."""
    result = await db.execute(select(FLWeightUpdate).where(FLWeightUpdate.id == update_id))
    update = result.scalar_one_or_none()
    if update is None:
        raise ValueError(f"Weight update {update_id} not found")

    path = artifact_path or update.artifact_path
    if not path:
        update.validation_score = 0.0
        update.is_outlier = True
        await db.commit()
        return update

    validation = validate_weight_update(path, expected_layers=expected_layers)
    update.validation_score = validation["validation_score"]
    update.is_outlier = validation["is_outlier"]

    if validation["is_outlier"]:
        update.status = "REJECTED"
        logger.warning(
            "weight_update_rejected",
            update_id=update_id,
            node_id=update.node_id,
            details=validation["details"],
        )
    else:
        logger.info(
            "weight_update_validated",
            update_id=update_id,
            node_id=update.node_id,
            score=validation["validation_score"],
        )

    await db.commit()
    return update
