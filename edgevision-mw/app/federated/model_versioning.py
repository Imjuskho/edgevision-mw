"""Federated model versioning extensions for the model registry.

Adds per-device rollback tracking and federated-aggregated model
version management.  Works with the existing DeployedModel table
(no new columns needed — uses the FL* tables for FL-specific state).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.federated.aggregation_server import AggregationServer, AggregationResult, DeviceUpdate
from app.federated.dp_noise import DPMechanism
from app.models.deployed_model import DeployedModel
from app.models.federated_learning import FLSyncRound, FLWeightUpdate, FLModelDistribution
from app.models.enums import ModelType

logger = logging.getLogger("edgevision.federated.model_versioning")


@dataclass
class FederatedModelVersion:
    """A version of a model produced by federated aggregation."""

    model_type: str
    version: str
    parent_version: str
    round_id: str
    artifact_path: str
    participating_nodes: list[str]
    global_accuracy: float | None
    created_at: datetime


class FederatedModelRegistry:
    """Extends the model registry with federated-specific operations.

    Tracks:
    - Which FL round produced each model version
    - Per-device validation scores against each version
    - Rollback triggers when a device regresses
    """

    def __init__(self, dp_mechanism: DPMechanism | None = None):
        self.aggregator = AggregationServer(dp_mechanism=dp_mechanism)

    async def promote_fl_round(
        self,
        db: AsyncSession,
        round_id: str,
        global_weights: dict[str, np.ndarray],
        base_model_version: str,
    ) -> FederatedModelVersion:
        """Promote an FL round's aggregated weights into the model registry.

        Creates a new DeployedModel entry (inactive) linked to the FL round.
        """
        round_record = await db.get(FLSyncRound, round_id)
        if round_record is None:
            raise ValueError(f"FL round {round_id} not found")

        if round_record.status != "AGGREGATING":
            raise ValueError(f"Round {round_id} is in status {round_record.status}, expected AGGREGATING")

        # Determine model type
        model_type_str = round_record.model_type
        try:
            model_type = ModelType(model_type_str)
        except ValueError:
            model_type = ModelType.object_detection

        # Count existing versions for this model type
        existing_count = (
            await db.execute(
                select(DeployedModel).where(DeployedModel.model_type == model_type)
            )
        ).scalars().all()
        version = f"fl_v{len(existing_count) + 1}"

        # Get artifact path from the round or use a default
        artifact_path = round_record.artifact_path or f"models/federated/{model_type_str}/{version}.npz"

        # Create the deployed model entry
        deployed = DeployedModel(
            training_job_id=round_record.id,  # Using round_id as FK (same string PK)
            model_name=f"FL-{model_type_str}-{version}",
            model_type=model_type,
            version=version,
            dataset_id="federated",
            artifact_path=artifact_path,
            accuracy=round_record.global_accuracy,
            is_active=False,
            notes=f"Federated aggregation round {round_id}, {round_record.num_contributors} contributors",
        )
        db.add(deployed)

        # Update the round record
        round_record.aggregated_model_version = version
        round_record.status = "COMPLETED"
        round_record.completed_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(deployed)

        # Get participating nodes
        updates_result = await db.execute(
            select(FLWeightUpdate).where(FLWeightUpdate.round_id == round_id)
        )
        updates = updates_result.scalars().all()
        participating = [u.node_id for u in updates if u.status == "ACCEPTED"]

        return FederatedModelVersion(
            model_type=model_type_str,
            version=version,
            parent_version=base_model_version,
            round_id=round_id,
            artifact_path=artifact_path,
            participating_nodes=participating,
            global_accuracy=round_record.global_accuracy,
            created_at=deployed.created_at or datetime.now(UTC),
        )

    async def record_device_validation(
        self,
        db: AsyncSession,
        round_id: str,
        node_id: str,
        validation_score: float,
    ) -> None:
        """Record a device's validation score after receiving a new model."""
        dist_result = await db.execute(
            select(FLModelDistribution).where(
                FLModelDistribution.round_id == round_id,
                FLModelDistribution.node_id == node_id,
            )
        )
        dist = dist_result.scalar_one_or_none()
        if dist:
            dist.node_validation_score = validation_score
            await db.commit()

    async def check_rollback_needed(
        self,
        db: AsyncSession,
        round_id: str,
        node_id: str,
        threshold: float = 0.8,
    ) -> bool:
        """Check if a device should rollback to the previous model version.

        Returns True if the device's validation score dropped below the
        threshold compared to the previous version's score.
        """
        dist_result = await db.execute(
            select(FLModelDistribution).where(
                FLModelDistribution.round_id == round_id,
                FLModelDistribution.node_id == node_id,
            )
        )
        dist = dist_result.scalar_one_or_none()
        if dist is None:
            return False

        if dist.node_validation_score is None:
            return False

        if dist.node_validation_score < threshold:
            logger.warning(
                "Device %s validation score %.3f below threshold %.3f — rollback recommended",
                node_id,
                dist.node_validation_score,
                threshold,
            )
            return True

        return False

    async def get_version_chain(
        self,
        db: AsyncSession,
        model_type: str,
    ) -> list[dict]:
        """Get the version history chain for a model type."""
        try:
            mt = ModelType(model_type)
        except ValueError:
            mt = ModelType.object_detection

        result = await db.execute(
            select(DeployedModel)
            .where(DeployedModel.model_type == mt)
            .order_by(DeployedModel.created_at.desc())
        )
        models = result.scalars().all()

        chain = []
        for m in models:
            chain.append({
                "id": str(m.id),
                "version": m.version,
                "accuracy": m.accuracy,
                "is_active": m.is_active,
                "notes": m.notes,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            })
        return chain
