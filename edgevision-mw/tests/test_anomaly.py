"""Tests for F4 — Open-Set Anomaly Detection."""
from __future__ import annotations

import numpy as np
import pytest

from app.anomaly.scene_embedder import SceneEmbedder
from app.anomaly.scorer import AnomalyScorer
from app.anomaly.describe import AnomalyDescriber


def _random_frame(seed=0, h=64, w=64):
    return (np.random.default_rng(seed).random((h, w, 3)) * 255).astype(np.uint8)


class TestSceneEmbedder:
    def test_not_ready_without_data(self):
        embedder = SceneEmbedder(min_frames=10)
        assert embedder.is_ready("cam-test") is False

    def test_ready_after_min_frames(self):
        embedder = SceneEmbedder(min_frames=5)
        for i in range(5):
            embedder.feed_frame("cam-test", frame_rgb=_random_frame(seed=i))
        assert embedder.is_ready("cam-test") is True

    def test_encode_returns_none_before_ready(self):
        embedder = SceneEmbedder(min_frames=5)
        result = embedder.encode("cam-test", frame_rgb=_random_frame(0))
        assert result is None

    def test_encode_returns_embedding_after_ready(self):
        embedder = SceneEmbedder(min_frames=3)
        for i in range(3):
            embedder.feed_frame("cam-test", frame_rgb=_random_frame(seed=i))
        result = embedder.encode("cam-test", frame_rgb=_random_frame(seed=99))
        assert result is not None
        assert isinstance(result, np.ndarray)

    def test_snapshot_restore(self):
        embedder = SceneEmbedder(min_frames=3)
        for i in range(5):
            embedder.feed_frame("cam-test", frame_rgb=_random_frame(seed=i))
        snapshot = embedder.snapshot("cam-test")
        assert snapshot is not None
        assert snapshot["is_ready"] is True

        embedder2 = SceneEmbedder(min_frames=3)
        embedder2.load_snapshot(snapshot)
        assert embedder2.is_ready("cam-test") is True

    def test_multiple_cameras_independent(self):
        embedder = SceneEmbedder(min_frames=2)
        for i in range(3):
            embedder.feed_frame("cam-a", frame_rgb=_random_frame(seed=i))
        assert embedder.is_ready("cam-a") is True
        assert embedder.is_ready("cam-b") is False


class TestAnomalyScorer:
    def test_not_ready_without_baseline(self):
        scorer = AnomalyScorer()
        assert scorer.is_ready("cam-test") is False

    def test_ready_after_enough_data(self):
        scorer = AnomalyScorer()
        rng = np.random.default_rng(42)
        for _ in range(35):
            scorer.feed_embedding("cam-test", rng.normal(0, 1, 32).astype(np.float32))
        assert scorer.is_ready("cam-test") is True

    def test_normal_data_returns_none(self):
        scorer = AnomalyScorer()
        rng = np.random.default_rng(42)
        for _ in range(30):
            scorer.feed_embedding("cam-test", rng.normal(0, 0.1, 32).astype(np.float32))
        result = scorer.score("cam-test", rng.normal(0, 0.1, 32).astype(np.float32))
        assert result is None

    def test_anomalous_data_may_score(self):
        scorer = AnomalyScorer()
        rng = np.random.default_rng(42)
        for _ in range(30):
            scorer.feed_embedding("cam-test", rng.normal(0, 1, 32).astype(np.float32))
        result = scorer.score("cam-test", rng.normal(10, 1, 32).astype(np.float32))
        if result is not None:
            assert result["is_anomalous"] is True
            assert "anomaly_score" in result
            assert "contributing_dims" in result

    def test_multiple_cameras(self):
        scorer = AnomalyScorer()
        rng = np.random.default_rng(42)
        for _ in range(35):
            scorer.feed_embedding("cam-a", rng.normal(0, 1, 32).astype(np.float32))
            scorer.feed_embedding("cam-b", rng.normal(0, 1, 32).astype(np.float32))
        assert scorer.is_ready("cam-a") is True
        assert scorer.is_ready("cam-b") is True


class TestAnomalyDescriber:
    def test_feature_flag_disabled(self):
        describer = AnomalyDescriber(enabled=False)
        desc = describer.describe(
            "cam-test",
            {
                "anomaly_score": 0.9,
                "is_anomalous": True,
                "dominant_component": 0,
                "component_responsibilities": {"comp_0": 0.9},
                "contributing_dims": [{"dim": 0, "contribution": 0.5, "value": 1.0, "expected": 0.0}],
            },
        )
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_description_for_anomalous_result(self):
        describer = AnomalyDescriber(enabled=True)
        desc = describer.describe(
            "cam-test",
            {
                "anomaly_score": 5.0,
                "threshold": 2.0,
                "is_anomalous": True,
                "dominant_component": 0,
                "component_responsibilities": {"comp_0": 0.9},
                "contributing_dims": [
                    {"dim": 0, "contribution": 0.5, "value": 1.0, "expected": 0.0},
                    {"dim": 1, "contribution": 0.3, "value": 0.8, "expected": 0.1},
                    {"dim": 2, "contribution": 0.2, "value": 0.6, "expected": 0.2},
                ],
            },
        )
        assert len(desc) > 0
        assert isinstance(desc, str)

    def test_description_with_detections(self):
        describer = AnomalyDescriber(enabled=True)
        desc = describer.describe(
            "cam-test",
            {
                "anomaly_score": 5.0,
                "threshold": 2.0,
                "is_anomalous": True,
                "dominant_component": 0,
                "component_responsibilities": {"comp_0": 0.9},
                "contributing_dims": [
                    {"dim": 0, "contribution": 0.5, "value": 1.0, "expected": 0.0},
                ],
            },
            detections=[{"class_name": "person", "confidence": 0.8, "bbox": [0.1, 0.1, 0.2, 0.2]}],
        )
        assert isinstance(desc, str)
