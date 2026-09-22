"""Tests for F5 — Living 3D Scene Reconstruction."""
from __future__ import annotations

import numpy as np
import pytest

from app.reconstruction.incremental_scene import (
    GaussianPrimitive,
    GaussianSplatScene,
    IncrementalSceneBuilder,
    estimate_cost_per_camera,
)
from app.reconstruction.change_detection import (
    SceneChangeDetector,
    detect_changes,
    estimate_cost_per_comparison,
)


def _upper_tri_from_diag(diag_vars):
    """Convert (3,) diagonal variances to (6,) upper-triangular covariance."""
    cov = np.zeros(6, dtype=np.float64)
    cov[0] = diag_vars[0]  # xx
    cov[3] = diag_vars[1]  # yy
    cov[5] = diag_vars[2]  # zz
    return cov


def _make_gaussians(n=3):
    gaussians = []
    rng = np.random.default_rng(42)
    for i in range(n):
        gaussians.append(GaussianPrimitive(
            position=rng.normal(0, 1, 3).astype(np.float32),
            covariance_upper=_upper_tri_from_diag([0.1, 0.1, 0.1]),
            opacity=0.8,
            sh_coefficients=np.zeros(27, dtype=np.float32),
        ))
    return gaussians


class TestGaussianPrimitive:
    def test_creation(self):
        g = GaussianPrimitive(
            position=np.array([1.0, 2.0, 3.0], dtype=np.float32),
            covariance_upper=_upper_tri_from_diag([0.1, 0.1, 0.1]),
            opacity=0.8,
            sh_coefficients=np.zeros(27, dtype=np.float32),
        )
        assert g.position.shape == (3,)
        assert g.covariance_upper.shape == (6,)
        assert g.opacity == 0.8

    def test_default_fields(self):
        g = GaussianPrimitive(
            position=np.zeros(3, dtype=np.float32),
            covariance_upper=np.ones(6, dtype=np.float32),
            opacity=1.0,
            sh_coefficients=np.zeros(27, dtype=np.float32),
        )
        assert g.observed_count == 0
        assert g.last_seen_frame == 0
        assert g.class_label == ""

    def test_serialization(self):
        g = GaussianPrimitive(
            position=np.array([1.0, 2.0, 3.0], dtype=np.float32),
            covariance_upper=_upper_tri_from_diag([0.1, 0.2, 0.3]),
            opacity=0.7,
            sh_coefficients=np.ones(27, dtype=np.float32) * 0.5,
            observed_count=5,
            class_label="car",
        )
        data = g.to_dict()
        g2 = GaussianPrimitive.from_dict(data)
        np.testing.assert_array_almost_equal(g.position, g2.position)
        np.testing.assert_array_almost_equal(g.covariance_upper, g2.covariance_upper)
        assert g.opacity == g2.opacity
        assert g.class_label == g2.class_label


class TestGaussianSplatScene:
    def test_creation(self):
        scene = GaussianSplatScene(camera_node_id="cam-001")
        assert len(scene.gaussians) == 0

    def test_add_primitives(self):
        scene = GaussianSplatScene(camera_node_id="cam-001")
        for g in _make_gaussians(10):
            scene.gaussians.append(g)
        assert len(scene.gaussians) == 10

    def test_serialization(self):
        scene = GaussianSplatScene(camera_node_id="cam-001")
        scene.gaussians.append(GaussianPrimitive(
            position=np.array([1.0, 2.0, 3.0], dtype=np.float32),
            covariance_upper=_upper_tri_from_diag([0.1, 0.1, 0.1]),
            opacity=0.8,
            sh_coefficients=np.zeros(27, dtype=np.float32),
        ))
        data = scene.to_dict()
        scene2 = GaussianSplatScene.from_dict(data)
        assert scene2.camera_node_id == "cam-001"
        assert len(scene2.gaussians) == 1

    def test_max_gaussians_attr(self):
        scene = GaussianSplatScene(camera_node_id="cam-001", max_gaussians=5)
        assert scene.max_gaussians == 5


class TestIncrementalSceneBuilder:
    def test_frame_ingestion(self):
        builder = IncrementalSceneBuilder(camera_node_id="cam-001")
        depth_map = np.ones((64, 64), dtype=np.float32) * 0.5
        detections = [
            {"bbox": [0.3, 0.3, 0.1, 0.1], "class_name": "car",
             "centroid": {"x": 0.35, "y": 0.35}, "confidence": 0.9},
        ]
        scene = builder.ingest_frame(
            depth_map=depth_map,
            segmentation_mask=None,
            detections=detections,
            image_width=64,
            image_height=64,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert len(scene.gaussians) > 0

    def test_incremental_update(self):
        builder = IncrementalSceneBuilder(camera_node_id="cam-001")
        depth1 = np.ones((64, 64), dtype=np.float32) * 0.5
        depth2 = np.ones((64, 64), dtype=np.float32) * 0.6

        scene1 = builder.ingest_frame(depth1, None, [], 64, 64, "t1")
        n1 = len(scene1.gaussians)
        scene2 = builder.ingest_frame(depth2, None, [], 64, 64, "t2")
        assert len(scene2.gaussians) >= n1

    def test_empty_frame(self):
        builder = IncrementalSceneBuilder(camera_node_id="cam-001")
        depth = np.ones((32, 32), dtype=np.float32) * 0.5
        scene = builder.ingest_frame(depth, None, [], 32, 32, "t0")
        assert len(scene.gaussians) >= 0

    def test_pruning_budget(self):
        builder = IncrementalSceneBuilder(camera_node_id="cam-001", max_gaussians=20)
        for i in range(30):
            depth = np.ones((64, 64), dtype=np.float32) * (0.3 + i * 0.01)
            builder.ingest_frame(depth, None, [], 64, 64, f"t{i}")
        assert len(builder.scene.gaussians) <= 20 + 100


class TestCostModel:
    def test_cost_per_camera(self):
        cost = estimate_cost_per_camera()
        assert "camera_count" in cost
        assert "avg_gaussians" in cost
        assert cost["avg_gaussians"] > 0

    def test_cost_per_camera_custom(self):
        cost = estimate_cost_per_camera(frames_per_second=2.0, hours_per_day=24.0)
        assert cost["frames_per_second"] == 2.0


class TestChangeDetection:
    def test_no_change(self):
        detector = SceneChangeDetector()
        scene = GaussianSplatScene(camera_node_id="cam-001")
        for g in _make_gaussians(3):
            scene.gaussians.append(g)
        report = detector.compare(scene, scene)
        assert report.overall_change_score == pytest.approx(0.0, abs=0.01)

    def test_detect_change_score(self):
        scene1 = GaussianSplatScene(camera_node_id="cam-001")
        scene1.gaussians.append(GaussianPrimitive(
            position=np.array([1, 0, 0], dtype=np.float32),
            covariance_upper=_upper_tri_from_diag([0.1, 0.1, 0.1]),
            opacity=0.8,
            sh_coefficients=np.zeros(27, dtype=np.float32),
        ))

        scene2 = GaussianSplatScene(camera_node_id="cam-001")
        scene2.gaussians.append(GaussianPrimitive(
            position=np.array([1, 0, 0], dtype=np.float32),
            covariance_upper=_upper_tri_from_diag([0.1, 0.1, 0.1]),
            opacity=0.8,
            sh_coefficients=np.zeros(27, dtype=np.float32),
        ))
        scene2.gaussians.append(GaussianPrimitive(
            position=np.array([5, 5, 5], dtype=np.float32),
            covariance_upper=_upper_tri_from_diag([0.1, 0.1, 0.1]),
            opacity=0.8,
            sh_coefficients=np.zeros(27, dtype=np.float32),
        ))

        report = SceneChangeDetector().compare(scene1, scene2)
        assert report.overall_change_score > 0
        assert report.new_gaussian_count == 2
        assert len(report.moved) > 0

    def test_cost_per_comparison(self):
        cost = estimate_cost_per_comparison()
        assert "arm_ms" in cost
        assert cost["arm_ms"] > 0


class TestDetectChangesFunction:
    def test_detect_changes_function(self):
        scene = GaussianSplatScene(camera_node_id="cam-001")
        scene.gaussians.append(GaussianPrimitive(
            position=np.array([1, 2, 3], dtype=np.float32),
            covariance_upper=_upper_tri_from_diag([0.1, 0.1, 0.1]),
            opacity=0.8,
            sh_coefficients=np.zeros(27, dtype=np.float32),
        ))
        report = detect_changes(scene, scene)
        assert hasattr(report, 'appeared')
        assert hasattr(report, 'disappeared')
        assert hasattr(report, 'moved')
