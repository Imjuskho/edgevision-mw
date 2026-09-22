"""Federated aggregation server — FedAvg with outlier resistance.

Receives weight deltas from registered devices and produces an
improved global model version.  Implements:
- FedAvg (McMahan et al., 2017) weighted averaging
- Robust aggregation (Trimmed Mean, Krum) for outlier/poisoned updates
- Differential privacy noise injection before creating the new global model
- Per-device validation to detect regressions
"""
from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.federated.dp_noise import DPMechanism

logger = logging.getLogger("edgevision.federated.aggregation")


@dataclass
class DeviceUpdate:
    """A single device's weight update for one round."""

    node_id: str
    delta_bytes: bytes
    num_samples: int
    local_loss: float
    local_accuracy: float
    checksum: str
    layer_names: list[str] = field(default_factory=list)


@dataclass
class AggregationResult:
    """Result of aggregating a round of weight updates."""

    aggregated_delta: dict[str, np.ndarray]
    new_global_weights: dict[str, np.ndarray]
    participating_nodes: list[str]
    num_updates: int
    rejected_nodes: list[str]
    dp_noise_added: bool
    aggregation_method: str
    per_device_validation: dict[str, float]
    weight_contributions: dict[str, float]


class AggregationServer:
    """Server-side aggregation of federated weight updates.

    Supports multiple aggregation strategies resistant to poisoned
    or outlier updates:
    - "fedavg": Standard weighted averaging (default)
    - "trimmed_mean": Remove top/bottom fraction before averaging
    - "krum": Select the update closest to the majority
    """

    def __init__(
        self,
        dp_mechanism: DPMechanism | None = None,
        method: str = "fedavg",
        trim_ratio: float = 0.1,
        min_participation_ratio: float = 0.3,
    ):
        self.dp = dp_mechanism or DPMechanism()
        self.method = method
        self.trim_ratio = trim_ratio
        self.min_participation_ratio = min_participation_ratio
        self._lock = threading.Lock()

    def aggregate(
        self,
        global_weights: dict[str, np.ndarray],
        updates: list[DeviceUpdate],
        *,
        target_count: int | None = None,
        apply_dp: bool = True,
    ) -> AggregationResult:
        """Aggregate weight deltas from multiple devices.

        Parameters
        ----------
        global_weights : dict[str, np.ndarray]
            Current global model weights.
        updates : list[DeviceUpdate]
            Weight deltas from participating devices.
        target_count : int, optional
            Expected number of contributors.  If fewer than
            min_participation_ratio * target_count submit, the
            round is rejected.
        apply_dp : bool
            Whether to add DP noise (can be disabled for testing).

        Returns
        -------
        AggregationResult
        """
        if not updates:
            return AggregationResult(
                aggregated_delta={},
                new_global_weights=global_weights,
                participating_nodes=[],
                num_updates=0,
                rejected_nodes=[],
                dp_noise_added=False,
                aggregation_method=self.method,
                per_device_validation={},
                weight_contributions={},
            )

        # Check participation threshold
        if target_count and len(updates) < int(target_count * self.min_participation_ratio):
            logger.warning(
                "Insufficient participation: %d/%d (need %.0f%%)",
                len(updates),
                target_count,
                self.min_participation_ratio * 100,
            )
            return AggregationResult(
                aggregated_delta={},
                new_global_weights=global_weights,
                participating_nodes=[u.node_id for u in updates],
                num_updates=0,
                rejected_nodes=[u.node_id for u in updates],
                dp_noise_added=False,
                aggregation_method=self.method,
                per_device_validation={},
                weight_contributions={},
            )

        # Deserialize and validate all deltas
        deltas, rejected = self._validate_updates(updates)

        if not deltas:
            logger.warning("All updates rejected after validation")
            return AggregationResult(
                aggregated_delta={},
                new_global_weights=global_weights,
                participating_nodes=[u.node_id for u in updates],
                num_updates=0,
                rejected_nodes=[u.node_id for u in updates],
                dp_noise_added=False,
                aggregation_method=self.method,
                per_device_validation={},
                weight_contributions={},
            )

        # Run aggregation
        with self._lock:
            if self.method == "trimmed_mean":
                agg_delta = self._trimmed_mean(deltas, updates)
            elif self.method == "krum":
                agg_delta = self._krum(deltas, updates)
            else:
                agg_delta = self._fedavg(deltas, updates)

        # Apply DP noise
        dp_applied = False
        if apply_dp:
            for layer_name in agg_delta:
                agg_delta[layer_name] = self.dp.add_noise(agg_delta[layer_name])
            dp_applied = True

        # Compute new global weights
        new_global = {}
        for k in global_weights:
            if k in agg_delta:
                new_global[k] = global_weights[k] + agg_delta[k]
            else:
                new_global[k] = global_weights[k].copy()

        # Count unique contributing devices (not layer entries)
        accepted_node_ids = {u.node_id for u in updates if u.node_id not in rejected}

        # Per-device validation: check each update against the new global
        per_device_val = {}
        for u in updates:
            if u.node_id not in rejected:
                try:
                    device_delta = self._deserialize_delta(u.delta_bytes, u.layer_names)
                    regressions = self._check_regression(global_weights, new_global, device_delta)
                    per_device_val[u.node_id] = 1.0 - min(regressions / max(len(device_delta), 1), 1.0)
                except Exception:
                    per_device_val[u.node_id] = 0.0

        # Weight contributions (fraction of total samples)
        total_samples = sum(u.num_samples for u in updates if u.node_id not in rejected)
        weight_contributions = {}
        for u in updates:
            if u.node_id not in rejected:
                weight_contributions[u.node_id] = u.num_samples / max(total_samples, 1)

        return AggregationResult(
            aggregated_delta=agg_delta,
            new_global_weights=new_global,
            participating_nodes=list(accepted_node_ids),
            num_updates=len(accepted_node_ids),
            rejected_nodes=list(rejected),
            dp_noise_added=dp_applied,
            aggregation_method=self.method,
            per_device_validation=per_device_val,
            weight_contributions=weight_contributions,
        )

    def _validate_updates(
        self, updates: list[DeviceUpdate]
    ) -> tuple[dict[str, list[tuple[str, np.ndarray, int]]], set[str]]:
        """Deserialize and validate all updates.

        Returns
        -------
        deltas : dict[str, list[(node_id, delta_array, num_samples)]]
            Per-layer list of valid deltas.
        rejected : set[str]
            Node IDs whose updates were rejected.
        """
        deltas: dict[str, list[tuple[str, np.ndarray, int]]] = {}
        rejected: set[str] = set()

        for u in updates:
            try:
                layer_deltas = self._deserialize_delta(u.delta_bytes, u.layer_names)

                # Check for NaN/Inf
                has_nan = False
                for arr in layer_deltas.values():
                    if np.any(np.isnan(arr)) or np.any(np.isinf(arr)):
                        has_nan = True
                        break
                if has_nan:
                    logger.warning("Rejecting update from %s: NaN/Inf detected", u.node_id)
                    rejected.add(u.node_id)
                    continue

                # Check L2 norm bound
                all_vals = np.concatenate([v.ravel() for v in layer_deltas.values()])
                l2 = float(np.linalg.norm(all_vals))
                if l2 > self.dp.max_grad_norm * 100:
                    logger.warning(
                        "Rejecting update from %s: L2 norm %.2f exceeds bound",
                        u.node_id,
                        l2,
                    )
                    rejected.add(u.node_id)
                    continue

                for layer_name, arr in layer_deltas.items():
                    if layer_name not in deltas:
                        deltas[layer_name] = []
                    deltas[layer_name].append((u.node_id, arr, u.num_samples))

            except Exception as e:
                logger.warning("Rejecting update from %s: %s", u.node_id, e)
                rejected.add(u.node_id)

        return deltas, rejected

    def _fedavg(
        self,
        deltas: dict[str, list[tuple[str, np.ndarray, int]]],
        updates: list[DeviceUpdate],
    ) -> dict[str, np.ndarray]:
        """Standard FedAvg: weighted average by sample count."""
        sample_map = {u.node_id: u.num_samples for u in updates}
        result = {}
        for layer_name, entries in deltas.items():
            total_samples = sum(n for _, _, n in entries)
            if total_samples == 0:
                continue
            weighted_sum = np.zeros_like(entries[0][1])
            for node_id, delta, n in entries:
                weighted_sum += delta * (n / total_samples)
            result[layer_name] = weighted_sum
        return result

    def _trimmed_mean(
        self,
        deltas: dict[str, list[tuple[str, np.ndarray, int]]],
        updates: list[DeviceUpdate],
    ) -> dict[str, np.ndarray]:
        """Trimmed mean: remove top/bottom fraction, then average."""
        result = {}
        for layer_name, entries in deltas.items():
            if len(entries) <= 2:
                # Too few to trim, fall back to fedavg
                total_samples = sum(n for _, _, n in entries)
                if total_samples == 0:
                    continue
                weighted_sum = np.zeros_like(entries[0][1])
                for node_id, delta, n in entries:
                    weighted_sum += delta * (n / total_samples)
                result[layer_name] = weighted_sum
                continue

            # Stack deltas and trim along the sample axis
            arrs = np.array([e[1] for e in entries])
            ns = np.array([e[2] for e in entries], dtype=np.float64)

            # Per-element trimmed mean
            k = max(1, int(len(arrs) * self.trim_ratio))
            sorted_idx = np.argsort(arrs, axis=0)
            trimmed = np.take_along_axis(arrs, sorted_idx[k:-k] if k < len(arrs) else sorted_idx[:1], axis=0)

            # Weighted average of trimmed values
            trimmed_ns = np.take_along_axis(ns, sorted_idx[k:-k] if k < len(arrs) else sorted_idx[:1], axis=0)
            total_n = trimmed_ns.sum()
            if total_n > 0:
                result[layer_name] = np.average(trimmed, axis=0, weights=trimmed_ns / total_n)
            else:
                result[layer_name] = trimmed.mean(axis=0)

        return result

    def _krum(
        self,
        deltas: dict[str, list[tuple[str, np.ndarray, int]]],
        updates: list[DeviceUpdate],
    ) -> dict[str, np.ndarray]:
        """Krum: select the update with smallest sum of distances to others."""
        result = {}
        for layer_name, entries in deltas.items():
            if len(entries) <= 1:
                result[layer_name] = entries[0][1]
                continue

            arrs = np.array([e[1] for e in entries])
            n = len(arrs)

            # Compute pairwise L2 distances
            dists = np.zeros((n, n))
            for i in range(n):
                for j in range(i + 1, n):
                    d = float(np.linalg.norm(arrs[i] - arrs[j]))
                    dists[i, j] = d
                    dists[j, i] = d

            # For each update, sum distances to closest (n - f - 1) neighbors
            f = max(1, n // 4)  # tolerate up to 25% Byzantine
            scores = []
            for i in range(n):
                sorted_dists = np.sort(dists[i])
                score = sorted_dists[1 : n - f].sum()  # skip self (distance=0)
                scores.append(score)

            best_idx = int(np.argmin(scores))
            result[layer_name] = arrs[best_idx]

        return result

    def _check_regression(
        self,
        old_weights: dict[str, np.ndarray],
        new_weights: dict[str, np.ndarray],
        device_delta: dict[str, np.ndarray],
    ) -> int:
        """Count layers where the device's update would regress the global model.

        A regression is defined as the device moving a layer in the
        opposite direction of the aggregated improvement.
        """
        regressions = 0
        for k in device_delta:
            if k in old_weights and k in new_weights:
                global_direction = new_weights[k] - old_weights[k]
                device_direction = device_delta[k]
                # Dot product: negative means opposite direction
                dot = float(np.sum(global_direction * device_direction))
                if dot < 0:
                    regressions += 1
        return regressions

    @staticmethod
    def _deserialize_delta(
        delta_bytes: bytes, layer_names: list[str]
    ) -> dict[str, np.ndarray]:
        """Deserialize npz bytes back to weight dict."""
        buf = io.BytesIO(delta_bytes)
        data = np.load(buf, allow_pickle=True)
        result = {}
        for name in layer_names:
            if name in data:
                result[name] = data[name]
        # Also load any layers not in the explicit list
        for k in data.files:
            if k not in result:
                result[k] = data[k]
        return result

    def serialize_global_weights(
        self, weights: dict[str, np.ndarray]
    ) -> bytes:
        """Serialize global model weights to npz bytes for distribution."""
        buf = io.BytesIO()
        np.savez(buf, **weights)
        buf.seek(0)
        return buf.read()
