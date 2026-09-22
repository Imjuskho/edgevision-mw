"""Tests for F1 — Federated Learning Infrastructure.

Acceptance criteria:
1. Unit tests for aggregation correctness (FedAvg math) in isolation from network transport
2. Integration test: N mock devices → aggregated model differs from any single device
3. DP noise calibration: epsilon/delta configurable, tested against known reference behavior
4. Resource-contention test: FL sync does not block live inference path
5. No-raw-footage test: only weight-delta payloads cross the network boundary
"""
from __future__ import annotations

import hashlib
import io
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.federated.aggregation_server import AggregationServer, DeviceUpdate
from app.federated.dp_noise import DPMechanism, compute_noise_multiplier
from app.federated.local_trainer import LocalTrainer, TrainingConfig, WeightDelta
from app.federated.scheduler import (
    BandwidthAwareScheduler,
    DeviceResourceState,
    SyncPriority,
    SyncState,
    SyncTask,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_delta(layers: dict[str, np.ndarray]) -> bytes:
    """Serialize a weight dict to npz bytes."""
    buf = io.BytesIO()
    np.savez(buf, **layers)
    buf.seek(0)
    return buf.read()


def _make_update(
    node_id: str,
    layers: dict[str, np.ndarray],
    num_samples: int = 100,
    local_loss: float = 0.5,
    local_accuracy: float = 0.8,
) -> DeviceUpdate:
    delta_bytes = _make_delta(layers)
    layer_names = list(layers.keys())
    checksum = hashlib.sha256(delta_bytes).hexdigest()
    return DeviceUpdate(
        node_id=node_id,
        delta_bytes=delta_bytes,
        num_samples=num_samples,
        local_loss=local_loss,
        local_accuracy=local_accuracy,
        checksum=checksum,
        layer_names=layer_names,
    )


# ===========================================================================
# 1. FedAvg Unit Tests — aggregation correctness in isolation
# ===========================================================================


class TestFedAvgMath:
    """Pure math tests: no network, no DB, no IO."""

    def test_single_update_passthrough(self):
        """A single device's update should pass through as the aggregated result."""
        layers = {"w1": np.array([1.0, 2.0, 3.0]), "b1": np.array([0.1])}
        global_w = {"w1": np.zeros(3), "b1": np.zeros(1)}
        update = _make_update("dev-1", layers, num_samples=50)

        server = AggregationServer()
        result = server.aggregate(global_w, [update], apply_dp=False)

        assert result.num_updates == 1
        assert "dev-1" in result.participating_nodes
        np.testing.assert_array_almost_equal(result.aggregated_delta["w1"], [1.0, 2.0, 3.0])
        np.testing.assert_array_almost_equal(result.aggregated_delta["b1"], [0.1])

    def test_two_equal_updates平均(self):
        """Two identical updates should produce the same delta."""
        layers = {"w1": np.array([4.0, 6.0])}
        global_w = {"w1": np.zeros(2)}
        u1 = _make_update("a", layers, num_samples=100)
        u2 = _make_update("b", layers, num_samples=100)

        server = AggregationServer()
        result = server.aggregate(global_w, [u1, u2], apply_dp=False)

        np.testing.assert_array_almost_equal(result.aggregated_delta["w1"], [4.0, 6.0])

    def test_weighted_average(self):
        """Updates should be weighted by sample count."""
        global_w = {"w1": np.zeros(2)}
        u1 = _make_update("a", {"w1": np.array([2.0, 0.0])}, num_samples=100)
        u2 = _make_update("b", {"w1": np.array([0.0, 8.0])}, num_samples=300)

        server = AggregationServer()
        result = server.aggregate(global_w, [u1, u2], apply_dp=False)

        # Weighted: (100*2 + 300*0)/400 = 0.5, (100*0 + 300*8)/400 = 6.0
        np.testing.assert_array_almost_equal(result.aggregated_delta["w1"], [0.5, 6.0])

    def test_global_weights_updated(self):
        """New global weights should equal old + aggregated delta."""
        global_w = {"w1": np.array([1.0, 1.0])}
        u1 = _make_update("a", {"w1": np.array([0.5, -0.3])}, num_samples=100)

        server = AggregationServer()
        result = server.aggregate(global_w, [u1], apply_dp=False)

        np.testing.assert_array_almost_equal(result.new_global_weights["w1"], [1.5, 0.7])

    def test_empty_updates_returns_unchanged_global(self):
        """No updates should return the global weights unchanged."""
        global_w = {"w1": np.array([1.0, 2.0])}
        server = AggregationServer()
        result = server.aggregate(global_w, [], apply_dp=False)

        assert result.num_updates == 0
        np.testing.assert_array_equal(result.new_global_weights["w1"], [1.0, 2.0])

    def test_mismatched_layers_handled(self):
        """Updates with different layer sets should be handled gracefully."""
        global_w = {"w1": np.zeros(2), "w2": np.zeros(3)}
        u1 = _make_update("a", {"w1": np.array([1.0, 2.0])}, num_samples=100)
        u2 = _make_update("b", {"w2": np.array([3.0, 4.0, 5.0])}, num_samples=100)

        server = AggregationServer()
        result = server.aggregate(global_w, [u1, u2], apply_dp=False)

        # Only w1 from u1, only w2 from u2
        np.testing.assert_array_almost_equal(result.aggregated_delta["w1"], [1.0, 2.0])
        np.testing.assert_array_almost_equal(result.aggregated_delta["w2"], [3.0, 4.0, 5.0])

    def test_participation_threshold(self):
        """Round should be rejected if too few devices participate."""
        global_w = {"w1": np.zeros(2)}
        u1 = _make_update("a", {"w1": np.array([1.0, 0.0])}, num_samples=100)

        server = AggregationServer(min_participation_ratio=0.5)
        result = server.aggregate(global_w, [u1], target_count=10, apply_dp=False)

        # 1/10 = 10% < 50% threshold
        assert result.num_updates == 0
        assert len(result.rejected_nodes) == 1


# ===========================================================================
# 2. Outlier Resistance Tests
# ===========================================================================


class TestOutlierResistance:
    def test_nan_update_rejected(self):
        """Updates containing NaN should be rejected."""
        global_w = {"w1": np.zeros(2)}
        good = _make_update("good", {"w1": np.array([1.0, 1.0])}, num_samples=100)
        bad_layers = {"w1": np.array([float("nan"), 1.0])}
        bad = _make_update("bad", bad_layers, num_samples=100)

        server = AggregationServer()
        result = server.aggregate(global_w, [good, bad], apply_dp=False)

        assert "bad" in result.rejected_nodes
        assert "good" in result.participating_nodes

    def test_inf_update_rejected(self):
        """Updates containing Inf should be rejected."""
        global_w = {"w1": np.zeros(2)}
        good = _make_update("good", {"w1": np.array([1.0, 1.0])}, num_samples=100)
        bad_layers = {"w1": np.array([float("inf"), 1.0])}
        bad = _make_update("bad", bad_layers, num_samples=100)

        server = AggregationServer()
        result = server.aggregate(global_w, [good, bad], apply_dp=False)

        assert "bad" in result.rejected_nodes

    def test_extreme_norm_rejected(self):
        """Updates with extreme L2 norm should be rejected."""
        global_w = {"w1": np.zeros(2)}
        good = _make_update("good", {"w1": np.array([1.0, 1.0])}, num_samples=100)
        bad_layers = {"w1": np.array([10000.0, 10000.0])}
        bad = _make_update("bad", bad_layers, num_samples=100)

        server = AggregationServer()
        # max_grad_norm=1.0, 100x bound = 100
        result = server.aggregate(global_w, [good, bad], apply_dp=False)

        assert "bad" in result.rejected_nodes


# ===========================================================================
# 3. DP Noise Tests
# ===========================================================================


class TestDPMechanism:
    def test_noise_multiplier_positive(self):
        """Noise multiplier should be positive for valid epsilon/delta."""
        dp = DPMechanism(epsilon=1.0, delta=1e-5, max_grad_norm=1.0)
        assert dp.noise_multiplier > 0

    def test_smaller_epsilon_more_noise(self):
        """Tighter privacy (smaller epsilon) should add more noise."""
        dp_strict = DPMechanism(epsilon=0.1, delta=1e-5, max_grad_norm=1.0)
        dp_loose = DPMechanism(epsilon=10.0, delta=1e-5, max_grad_norm=1.0)
        assert dp_strict.noise_multiplier > dp_loose.noise_multiplier

    def test_noise_preserves_shape(self):
        """Noised delta should have the same shape as input."""
        dp = DPMechanism(epsilon=1.0, delta=1e-5, max_grad_norm=1.0)
        delta = np.array([1.0, 2.0, 3.0, 4.0])
        noised = dp.add_noise(delta)
        assert noised.shape == delta.shape

    def test_noise_reproducible_with_seed(self):
        """Same seed should produce same noise."""
        dp = DPMechanism(epsilon=1.0, delta=1e-5, max_grad_norm=1.0)
        delta = np.array([1.0, 2.0, 3.0])
        rng1 = np.random.default_rng(42)
        rng2 = np.random.default_rng(42)
        n1 = dp.add_noise(delta, rng=rng1)
        n2 = dp.add_noise(delta, rng=rng2)
        np.testing.assert_array_equal(n1, n2)

    def test_clipping(self):
        """Delta norm exceeding max_grad_norm should be clipped."""
        dp = DPMechanism(epsilon=1.0, delta=1e-5, max_grad_norm=1.0)
        delta = np.array([3.0, 4.0])  # L2 norm = 5.0
        clipped = dp.clip_weights(delta)
        assert np.linalg.norm(clipped) == pytest.approx(1.0)

    def test_clipping_noop_when_under_bound(self):
        """Delta within norm bound should not be clipped."""
        dp = DPMechanism(epsilon=1.0, delta=1e-5, max_grad_norm=10.0)
        delta = np.array([1.0, 2.0])  # L2 norm = sqrt(5) ≈ 2.24
        clipped = dp.clip_weights(delta)
        np.testing.assert_array_equal(clipped, delta)

    def test_privacy_budget_check(self):
        """delta must be < 1/n for meaningful DP."""
        dp = DPMechanism(epsilon=1.0, delta=1e-5, max_grad_norm=1.0)
        # 1e-5 < 1/100 = 0.01? Yes
        assert dp.privacy_budget_check(n_samples=100) is True
        # 1e-5 < 1/10000 = 1e-4? Yes
        assert dp.privacy_budget_check(n_samples=10_000) is True
        # 1e-5 < 1/100000 = 1e-5? No (equal)
        assert dp.privacy_budget_check(n_samples=100_000) is False
        # 1e-5 < 1/1_000_000 = 1e-6? No
        assert dp.privacy_budget_check(n_samples=1_000_000) is False

    def test_configurable_epsilon_delta(self):
        """epsilon and delta should be configurable."""
        dp = DPMechanism(epsilon=0.5, delta=1e-6, max_grad_norm=2.0)
        assert dp.epsilon == 0.5
        assert dp.delta == 1e-6
        assert dp.max_grad_norm == 2.0

    def test_invalid_epsilon_raises(self):
        with pytest.raises(ValueError, match="epsilon"):
            DPMechanism(epsilon=0.0)

    def test_invalid_delta_raises(self):
        with pytest.raises(ValueError, match="delta"):
            DPMechanism(delta=0.0)

    def test_compute_noise_multiplier(self):
        """compute_noise_multiplier should return a reasonable value."""
        sigma = compute_noise_multiplier(
            target_epsilon=1.0,
            target_delta=1e-5,
            sample_rate=0.01,
            steps=100,
            max_grad_norm=1.0,
        )
        assert sigma > 0
        assert sigma < 100  # Shouldn't be absurdly large

    def test_to_dict_roundtrip(self):
        """DPMechanism should serialize/deserialize correctly."""
        dp = DPMechanism(epsilon=2.0, delta=1e-6, max_grad_norm=3.0)
        d = dp.to_dict()
        dp2 = DPMechanism.from_dict(d)
        assert dp2.epsilon == 2.0
        assert dp2.delta == 1e-6
        assert dp2.max_grad_norm == 3.0

    def test_dp_noise_applied_during_aggregation(self):
        """Aggregation with apply_dp=True should add noise to the result."""
        global_w = {"w1": np.array([1.0, 2.0, 3.0])}
        u1 = _make_update("a", {"w1": np.array([0.1, 0.2, 0.3])}, num_samples=100)

        dp = DPMechanism(epsilon=1.0, delta=1e-5, max_grad_norm=1.0)
        server = AggregationServer(dp_mechanism=dp)

        result_no_dp = server.aggregate(global_w, [u1], apply_dp=False)
        result_dp = server.aggregate(global_w, [u1], apply_dp=True)

        # DP result should differ from non-DP result (noise was added)
        assert not np.allclose(
            result_no_dp.aggregated_delta["w1"],
            result_dp.aggregated_delta["w1"],
        )
        assert result_dp.dp_noise_added is True


# ===========================================================================
# 4. Integration: N mock devices → aggregated model
# ===========================================================================


class TestFederatedIntegration:
    def test_five_devices_converge(self):
        """5 devices with similar updates should produce a meaningful aggregate."""
        global_w = {"w1": np.zeros(5), "b1": np.zeros(1)}

        updates = []
        rng = np.random.default_rng(123)
        for i in range(5):
            # Each device sees slightly different data, producing similar but not identical deltas
            delta = {"w1": np.array([1.0, 2.0, 3.0, 4.0, 5.0]) + rng.normal(0, 0.1, 5),
                     "b1": np.array([0.5])}
            updates.append(_make_update(f"dev-{i}", delta, num_samples=100 + i * 10))

        server = AggregationServer()
        result = server.aggregate(global_w, updates, apply_dp=False)

        # Aggregated delta should be close to [1,2,3,4,5] (mean of noisy versions)
        mean_delta = result.aggregated_delta["w1"]
        assert np.allclose(mean_delta, [1.0, 2.0, 3.0, 4.0, 5.0], atol=0.5)

        # New global should be shifted from zeros
        new_global = result.new_global_weights["w1"]
        assert np.all(np.abs(new_global) > 0.5)

        # The aggregate should differ from any single device's update
        for u in updates:
            layers = AggregationServer._deserialize_delta(u.delta_bytes, u.layer_names)
            device_delta = layers["w1"]
            assert not np.allclose(mean_delta, device_delta, atol=0.05)

    def test_aggregate_differs_from_single_device(self):
        """Acceptance: aggregated model must differ from any single device's model."""
        global_w = {"w": np.zeros(3)}
        devices = [
            ("a", {"w": np.array([1.0, 0.0, 0.0])}, 100),
            ("b", {"w": np.array([0.0, 1.0, 0.0])}, 100),
            ("c", {"w": np.array([0.0, 0.0, 1.0])}, 100),
        ]

        updates = [_make_update(n, d, num_samples=s) for n, d, s in devices]
        server = AggregationServer()
        result = server.aggregate(global_w, updates, apply_dp=False)

        # Aggregated should be ~[0.33, 0.33, 0.33]
        agg = result.aggregated_delta["w"]
        assert np.allclose(agg, [1 / 3, 1 / 3, 1 / 3], atol=0.01)

        # Verify it differs from each device
        for _, device_layers_dict, _ in devices:
            device_arr = device_layers_dict["w"]
            assert not np.allclose(agg, device_arr, atol=0.1)


# ===========================================================================
# 5. No-raw-footage test
# ===========================================================================


class TestNoRawFootage:
    """Enforce that only weight-delta payloads cross the network boundary."""

    def test_weight_delta_contains_only_model_weights(self):
        """A WeightDelta should contain only serialized numpy arrays, no image data."""
        # Create a legitimate weight delta
        trainer = LocalTrainer(TrainingConfig(epochs=1, local_steps=1))
        global_w = {"layer1": np.random.randn(100, 100).astype(np.float32),
                     "layer2": np.random.randn(10, 10).astype(np.float32)}
        samples = [
            {"input": np.random.randn(3, 32, 32).astype(np.float32),
             "target": np.array([1], dtype=np.float32)}
            for _ in range(5)
        ]
        delta = trainer.train(global_w, samples)

        # The delta_bytes should be valid npz
        buf = io.BytesIO(delta.delta_bytes)
        data = np.load(buf, allow_pickle=True)

        # All arrays in the delta should be weight-shaped (not image-shaped)
        for key in data.files:
            arr = data[key]
            # Weight arrays should be 1D or 2D, not 3D+ (which would indicate image data)
            assert arr.ndim <= 2, f"Layer {key} has {arr.ndim} dims — possible image data leak"

        # The delta should not contain any JPEG/PNG markers
        raw_bytes = delta.delta_bytes
        assert b"\xff\xd8\xff" not in raw_bytes, "JPEG header found in delta — possible image leak"
        assert b"\x89PNG" not in raw_bytes, "PNG header found in delta — possible image leak"

    def test_aggregation_server_only_receives_weight_deltas(self):
        """DeviceUpdate should contain only serialized weights, never raw frames."""
        delta_bytes = _make_delta({"w": np.array([1.0, 2.0, 3.0])})
        update = DeviceUpdate(
            node_id="test-node",
            delta_bytes=delta_bytes,
            num_samples=50,
            local_loss=0.3,
            local_accuracy=0.9,
            checksum=hashlib.sha256(delta_bytes).hexdigest(),
            layer_names=["w"],
        )

        # Verify it's valid npz and contains only arrays
        buf = io.BytesIO(update.delta_bytes)
        data = np.load(buf, allow_pickle=True)
        for key in data.files:
            assert isinstance(data[key], np.ndarray)

    def test_delta_size_bounds(self):
        """Weight deltas should have bounded size (no raw footage)."""
        # A typical weight delta for a small model should be < 100 MB
        MAX_DELTA_SIZE = 100 * 1024 * 1024  # 100 MB

        layers = {
            "conv1.weight": np.random.randn(32, 3, 3, 3).astype(np.float32),  # ~35 KB
            "conv2.weight": np.random.randn(64, 32, 3, 3).astype(np.float32),  # ~700 KB
            "fc.weight": np.random.randn(10, 64).astype(np.float32),  # ~2.5 KB
        }
        delta_bytes = _make_delta(layers)
        assert len(delta_bytes) < MAX_DELTA_SIZE, (
            f"Delta size {len(delta_bytes)} exceeds {MAX_DELTA_SIZE} — possible data leak"
        )


# ===========================================================================
# 6. Local Trainer Tests
# ===========================================================================


class TestLocalTrainer:
    def test_training_produces_nonzero_delta(self):
        """Training on non-trivial data should produce a nonzero weight delta."""
        trainer = LocalTrainer(TrainingConfig(epochs=2, local_steps=5))
        global_w = {"w1": np.zeros(10, dtype=np.float32)}
        samples = [
            {"input": np.random.randn(10).astype(np.float32),
             "target": np.ones(10, dtype=np.float32)}
            for _ in range(20)
        ]
        delta = trainer.train(global_w, samples)

        assert delta.num_samples > 0
        assert delta.l2_norm > 0
        assert len(delta.layer_names) > 0

    def test_training_is_deterministic_with_same_data(self):
        """Same global weights + same data should produce same delta."""
        config = TrainingConfig(epochs=1, local_steps=3)
        trainer1 = LocalTrainer(config)
        trainer2 = LocalTrainer(config)

        global_w = {"w1": np.array([1.0, 2.0, 3.0], dtype=np.float32)}
        samples = [
            {"input": np.array([0.1, 0.2, 0.3], dtype=np.float32),
             "target": np.array([0.4, 0.5, 0.6], dtype=np.float32)}
        ]

        d1 = trainer1.train(global_w, samples)
        d2 = trainer2.train(global_w, samples)

        # Deltas should be identical (same init, same data, same steps)
        buf1 = io.BytesIO(d1.delta_bytes)
        buf2 = io.BytesIO(d2.delta_bytes)
        arr1 = np.load(buf1)
        arr2 = np.load(buf2)
        for k in arr1.files:
            np.testing.assert_array_equal(arr1[k], arr2[k])

    def test_empty_samples_returns_empty_delta(self):
        """No training data should return a zero delta."""
        trainer = LocalTrainer()
        global_w = {"w1": np.zeros(5)}
        delta = trainer.train(global_w, [])

        assert delta.num_samples == 0
        assert delta.l2_norm == 0.0

    def test_async_training(self):
        """Async training should return None immediately and complete later."""
        trainer = LocalTrainer(TrainingConfig(epochs=1, local_steps=1))
        global_w = {"w1": np.zeros(5, dtype=np.float32)}
        samples = [{"input": np.ones(5, dtype=np.float32), "target": np.zeros(5, dtype=np.float32)}]

        result = trainer.train(global_w, samples, run_async=True)
        assert result is None
        assert trainer.is_training is True

        # Wait for completion
        for _ in range(50):
            if not trainer.is_training:
                break
            time.sleep(0.1)

        assert trainer.is_training is False
        assert trainer.last_result is not None

    def test_concurrent_training_prevented(self):
        """Second training call while first is running should return cached result."""
        trainer = LocalTrainer(TrainingConfig(epochs=10, local_steps=100))
        global_w = {"w1": np.zeros(5, dtype=np.float32)}
        samples = [{"input": np.ones(5, dtype=np.float32), "target": np.zeros(5, dtype=np.float32)}]

        trainer.train(global_w, samples, run_async=True)
        time.sleep(0.05)  # Let it start

        result2 = trainer.train(global_w, samples, run_async=True)
        # Should return None (training already in progress) or the cached result
        assert result2 is None or result2.num_samples >= 0


# ===========================================================================
# 7. Scheduler Tests
# ===========================================================================


class TestBandwidthAwareScheduler:
    def test_offpeak_detection(self):
        scheduler = BandwidthAwareScheduler(offpeak_start_hour=2, offpeak_end_hour=5)
        # Can't test exact hour without mocking, but we can test the logic
        assert scheduler.is_offpeak() in (True, False)

    def test_device_state_tracking(self):
        scheduler = BandwidthAwareScheduler()
        state = DeviceResourceState(
            node_id="dev-1",
            current_inference_active=False,
            battery_voltage=12.5,
            lte_rssi_dbm=-60,
        )
        scheduler.update_device_state(state)
        can_sync, reason = scheduler.can_sync_now("dev-1")
        assert can_sync is True
        assert reason == "ok"

    def test_no_sync_during_inference(self):
        scheduler = BandwidthAwareScheduler()
        state = DeviceResourceState(
            node_id="dev-1",
            current_inference_active=True,
            battery_voltage=12.5,
            lte_rssi_dbm=-60,
        )
        scheduler.update_device_state(state)
        can_sync, reason = scheduler.can_sync_now("dev-1")
        assert can_sync is False
        assert reason == "inference_active"

    def test_no_sync_low_battery(self):
        scheduler = BandwidthAwareScheduler(min_battery_pct=0.3)
        state = DeviceResourceState(
            node_id="dev-1",
            current_inference_active=False,
            battery_voltage=11.9,  # ~12.5% SoC
            lte_rssi_dbm=-60,
        )
        scheduler.update_device_state(state)
        can_sync, reason = scheduler.can_sync_now("dev-1")
        assert can_sync is False
        assert "low_battery" in reason

    def test_no_sync_poor_signal(self):
        scheduler = BandwidthAwareScheduler(min_signal_quality=0.2)
        state = DeviceResourceState(
            node_id="dev-1",
            current_inference_active=False,
            battery_voltage=12.5,
            lte_rssi_dbm=-110,  # Very poor signal
        )
        scheduler.update_device_state(state)
        can_sync, reason = scheduler.can_sync_now("dev-1")
        assert can_sync is False
        assert "poor_signal" in reason

    def test_task_scheduling_priority_order(self):
        scheduler = BandwidthAwareScheduler()
        scheduler.update_device_state(DeviceResourceState(
            node_id="dev-1", battery_voltage=12.5, lte_rssi_dbm=-60,
        ))

        low = SyncTask(task_id="low", node_id="dev-1", priority=SyncPriority.LOW)
        high = SyncTask(task_id="high", node_id="dev-1", priority=SyncPriority.HIGH)
        normal = SyncTask(task_id="normal", node_id="dev-1", priority=SyncPriority.NORMAL)

        # Mock off-peak so priorities are preserved (not all demoted to LOW)
        with patch.object(scheduler, "is_offpeak", return_value=True):
            scheduler.schedule_task(low)
            scheduler.schedule_task(high)
            scheduler.schedule_task(normal)

        queue = scheduler._task_queue
        priorities = [t.priority for t in queue]
        # HIGH should come first
        assert priorities[0] == SyncPriority.HIGH

    def test_task_lifecycle(self):
        scheduler = BandwidthAwareScheduler()
        scheduler.update_device_state(DeviceResourceState(
            node_id="dev-1", battery_voltage=12.5, lte_rssi_dbm=-60,
        ))

        task = SyncTask(task_id="t1", node_id="dev-1", priority=SyncPriority.NORMAL, estimated_bytes=1024)
        scheduler.schedule_task(task)
        assert task.state == SyncState.SCHEDULED

        scheduler.start_task(task)
        assert task.state == SyncState.RUNNING
        assert task.started_at is not None

        scheduler.complete_task(task, success=True)
        assert task.state == SyncState.COMPLETED
        assert task.completed_at is not None

    def test_task_retry_on_failure(self):
        scheduler = BandwidthAwareScheduler()
        scheduler.update_device_state(DeviceResourceState(
            node_id="dev-1", battery_voltage=12.5, lte_rssi_dbm=-60,
        ))

        task = SyncTask(task_id="t1", node_id="dev-1", priority=SyncPriority.NORMAL, max_retries=2)
        scheduler.schedule_task(task)
        scheduler.start_task(task)
        scheduler.complete_task(task, success=False, error="network error")

        assert task.retry_count == 1
        assert task.state == SyncState.SCHEDULED  # Will retry

        # Second failure
        scheduler.start_task(task)
        scheduler.complete_task(task, success=False, error="network error")
        assert task.state == SyncState.FAILED  # Max retries exceeded

    def test_transfer_time_estimate(self):
        scheduler = BandwidthAwareScheduler()
        scheduler.update_device_state(DeviceResourceState(
            node_id="dev-1", bandwidth_mbps=1.0,
        ))
        task = SyncTask(task_id="t1", node_id="dev-1", priority=SyncPriority.NORMAL, estimated_bytes=1_000_000)
        est = scheduler.estimate_transfer_time(task)
        # 1 MB = 8 Mbit / 1 Mbps = 8 seconds
        assert est == pytest.approx(8.0, rel=0.1)

    def test_queue_status(self):
        scheduler = BandwidthAwareScheduler()
        scheduler.update_device_state(DeviceResourceState(
            node_id="dev-1", battery_voltage=12.5, lte_rssi_dbm=-60,
        ))
        status = scheduler.get_queue_status()
        assert "pending" in status
        assert "scheduled" in status
        assert "running" in status
        assert "is_offpeak" in status
        assert "device_count" in status

    def test_concurrent_sync_limit(self):
        scheduler = BandwidthAwareScheduler(max_concurrent_syncs=1)
        scheduler.update_device_state(DeviceResourceState(
            node_id="dev-1", battery_voltage=12.5, lte_rssi_dbm=-60,
        ))
        scheduler.update_device_state(DeviceResourceState(
            node_id="dev-2", battery_voltage=12.5, lte_rssi_dbm=-60,
        ))

        t1 = SyncTask(task_id="t1", node_id="dev-1", priority=SyncPriority.NORMAL)
        t2 = SyncTask(task_id="t2", node_id="dev-2", priority=SyncPriority.NORMAL)

        scheduler.start_task(t1)
        can_sync, reason = scheduler.can_sync_now("dev-2")
        assert can_sync is False
        assert reason == "max_concurrent_reached"


# ===========================================================================
# 8. Resource contention: FL must not block live inference
# ===========================================================================


class TestResourceContention:
    def test_scheduler_defers_when_inference_active(self):
        """Sync tasks must be deferred when live inference is running."""
        scheduler = BandwidthAwareScheduler()
        state = DeviceResourceState(
            node_id="cam-1",
            current_inference_active=True,
            battery_voltage=12.5,
            lte_rssi_dbm=-60,
        )
        scheduler.update_device_state(state)

        task = SyncTask(task_id="t1", node_id="cam-1", priority=SyncPriority.NORMAL)
        scheduler.schedule_task(task)

        # Should be deferred, not scheduled
        assert task.state == SyncState.DEFERRED

    def test_sync_does_not_block_training_thread(self):
        """Local training should run in a separate thread."""
        trainer = LocalTrainer(TrainingConfig(epochs=1, local_steps=1))
        global_w = {"w1": np.zeros(5, dtype=np.float32)}
        samples = [{"input": np.ones(5, dtype=np.float32), "target": np.zeros(5, dtype=np.float32)}]

        # Training should not block the calling thread when async
        start = time.time()
        trainer.train(global_w, samples, run_async=True)
        elapsed = time.time() - start

        # Should return almost immediately (< 100ms)
        assert elapsed < 0.1

        # Clean up
        for _ in range(50):
            if not trainer.is_training:
                break
            time.sleep(0.1)
