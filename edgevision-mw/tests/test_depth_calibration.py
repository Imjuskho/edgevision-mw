"""Tests for depth calibration (Phase 1 + Phase 2 depth accuracy fix)."""

import math
import time
from unittest.mock import patch

import numpy as np
import pytest

from app.ai.depth_calibration import (
    CalibrationPoint,
    CameraDepthCalibration,
    add_drift_reference,
    calibrate_camera,
    check_drift,
    compute_linear_calibration,
    compute_piecewise_calibration,
    load_calibration,
    relative_to_metric,
    relative_to_metric_array,
    store_calibration,
    validate_calibration,
)
from app.ai.depth_estimator import DepthEstimator


# ═══════════════════════════════════════════════════════════════════════
#  Phase 1.1 — Ordering consistency check
# ═══════════════════════════════════════════════════════════════════════

class TestOrderingConsistency:
    def test_near_object_has_lower_depth_than_far_object(self):
        """Closer objects should have lower relative depth (higher = farther)."""
        depth_map = np.zeros((480, 640), dtype=np.float32)
        # near object at y=300..400, x=100..200  → depth ~0.3
        depth_map[300:400, 100:200] = 0.3
        # far object at y=100..180, x=300..420   → depth ~0.8
        depth_map[100:180, 300:420] = 0.8

        est = DepthEstimator(model_path="/nonexistent")
        near_d, near_q = est.depth_at_bbox(depth_map, [100/640, 300/480, 100/640, 100/480])
        far_d, far_q = est.depth_at_bbox(depth_map, [300/640, 100/480, 120/640, 80/480])

        assert near_d < far_d, f"near={near_d:.4f} should be < far={far_d:.4f}"

    def test_verify_ordering_static_method(self):
        depth_map = np.zeros((480, 640), dtype=np.float32)
        depth_map[350:420, 80:200] = 0.25   # near
        depth_map[80:150, 350:500] = 0.75   # far

        result = DepthEstimator.verify_ordering(
            depth_map,
            near_bbox=[80/640, 350/480, 120/640, 70/480],
            far_bbox=[350/640, 80/480, 150/640, 70/480],
        )
        assert result["consistent"] is True
        assert result["near_depth"] < result["far_depth"]
        assert result["delta"] > 0

    def test_inverted_ordering_detected(self):
        depth_map = np.zeros((480, 640), dtype=np.float32)
        depth_map[350:420, 80:200] = 0.9    # near object but high depth
        depth_map[80:150, 350:500] = 0.1    # far object but low depth

        result = DepthEstimator.verify_ordering(
            depth_map,
            near_bbox=[80/640, 350/480, 120/640, 70/480],
            far_bbox=[350/640, 80/480, 150/640, 70/480],
        )
        assert result["consistent"] is False

    def test_constant_depth_ordering(self):
        depth_map = np.full((480, 640), 0.5, dtype=np.float32)

        result = DepthEstimator.verify_ordering(
            depth_map,
            near_bbox=[80/640, 350/480, 120/640, 70/480],
            far_bbox=[350/640, 80/480, 150/640, 70/480],
        )
        assert result["consistent"] is False  # equal, not strictly less


# ═══════════════════════════════════════════════════════════════════════
#  Phase 1.2 — Mask-based depth sampling
# ═══════════════════════════════════════════════════════════════════════

class TestMaskSampling:
    def test_mask_median_used_when_mask_provided(self):
        h, w = 100, 100
        depth_map = np.zeros((h, w), dtype=np.float32)
        depth_map[:, :] = 0.9   # background high
        depth_map[20:80, 30:70] = 0.1  # object low

        mask = np.zeros((h, w), dtype=np.uint8)
        mask[20:80, 30:70] = 1

        est = DepthEstimator(model_path="/nonexistent")
        d, q = est.depth_at_bbox(depth_map, [30/w, 20/h, 40/w, 60/h], mask=mask)
        assert q == "mask_median"
        assert d < 0.5  # should pick up the low-depth object region

    def test_mask_with_too_few_pixels_falls_back(self):
        h, w = 100, 100
        depth_map = np.full((h, w), 0.5, dtype=np.float32)
        depth_map[50:55, 50:55] = 0.1

        mask = np.zeros((h, w), dtype=np.uint8)
        mask[50:52, 50:52] = 1  # only 4 pixels → below threshold of 5

        est = DepthEstimator(model_path="/nonexistent")
        d, q = est.depth_at_bbox(depth_map, [50/w, 50/h, 5/w, 5/h], mask=mask)
        assert q != "mask_median"

    def test_no_mask_falls_back_to_bias(self):
        h, w = 100, 100
        depth_map = np.zeros((h, w), dtype=np.float32)
        depth_map[:, :] = 0.5

        est = DepthEstimator(model_path="/nonexistent")
        d, q = est.depth_at_bbox(depth_map, [10/w, 10/h, 80/w, 80/h])
        assert q in ("biased_lower_third", "full_bbox")

    def test_mask_shape_mismatch_falls_back(self):
        h, w = 100, 100
        depth_map = np.full((h, w), 0.5, dtype=np.float32)
        wrong_mask = np.zeros((50, 50), dtype=np.uint8)

        est = DepthEstimator(model_path="/nonexistent")
        d, q = est.depth_at_bbox(depth_map, [10/w, 10/h, 80/w, 80/h], mask=wrong_mask)
        assert q != "mask_median"


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2.1 — Linear calibration
# ═══════════════════════════════════════════════════════════════════════

class TestLinearCalibration:
    def test_single_point_linear(self):
        pts = [CalibrationPoint(relative_depth=0.5, real_distance_m=5.0)]
        scale, offset = compute_linear_calibration(pts)
        assert scale == pytest.approx(10.0)
        assert offset == 0.0

    def test_two_points_linear(self):
        pts = [
            CalibrationPoint(relative_depth=0.2, real_distance_m=2.0),
            CalibrationPoint(relative_depth=0.8, real_distance_m=8.0),
        ]
        scale, offset = compute_linear_calibration(pts)
        assert scale == pytest.approx(10.0)
        assert offset == pytest.approx(0.0, abs=1e-6)

    def test_two_points_with_offset(self):
        pts = [
            CalibrationPoint(relative_depth=0.2, real_distance_m=3.0),
            CalibrationPoint(relative_depth=0.8, real_distance_m=9.0),
        ]
        scale, offset = compute_linear_calibration(pts)
        assert scale == pytest.approx(10.0)
        assert offset == pytest.approx(1.0, abs=1e-6)

    def test_empty_points(self):
        scale, offset = compute_linear_calibration([])
        assert scale == 1.0
        assert offset == 0.0

    def test_degenerate_points(self):
        pts = [
            CalibrationPoint(relative_depth=0.0, real_distance_m=2.0),
            CalibrationPoint(relative_depth=0.0, real_distance_m=5.0),
        ]
        scale, offset = compute_linear_calibration(pts)
        assert math.isfinite(scale)


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2.1 — Piecewise-linear calibration
# ═══════════════════════════════════════════════════════════════════════

class TestPiecewiseCalibration:
    def test_three_points_two_segments(self):
        pts = [
            CalibrationPoint(relative_depth=0.1, real_distance_m=1.0, label="near"),
            CalibrationPoint(relative_depth=0.4, real_distance_m=4.0, label="mid"),
            CalibrationPoint(relative_depth=0.9, real_distance_m=12.0, label="far"),
        ]
        segments = compute_piecewise_calibration(pts)
        assert len(segments) == 2
        assert segments[0][0] == 0.1  # first start
        assert segments[1][0] == 0.4  # second start

    def test_too_few_points(self):
        pts = [CalibrationPoint(relative_depth=0.5, real_distance_m=5.0)]
        segments = compute_piecewise_calibration(pts)
        assert segments == []

    def test_piecewise_conversion(self):
        pts = [
            CalibrationPoint(relative_depth=0.1, real_distance_m=1.0),
            CalibrationPoint(relative_depth=0.4, real_distance_m=4.0),
            CalibrationPoint(relative_depth=0.9, real_distance_m=12.0),
        ]
        cal = CameraDepthCalibration(camera_id="test_cam", calibration_points=pts)
        cal.mode = "piecewise"

        # Exact points should return exact values
        for p in pts:
            m = relative_to_metric(p.relative_depth, cal)
            assert m == pytest.approx(p.real_distance_m, abs=0.1)

        # Mid-segment interpolation
        mid = relative_to_metric(0.25, cal)
        assert 2.0 < mid < 4.0


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2.1 — calibrate_camera factory
# ═══════════════════════════════════════════════════════════════════════

class TestCalibrateCamera:
    def test_single_point_linear_mode(self):
        pts = [CalibrationPoint(relative_depth=0.5, real_distance_m=5.0)]
        cal = calibrate_camera("cam1", pts)
        assert cal.mode == "linear"
        assert cal.scale == pytest.approx(10.0)
        assert cal.calibration_points == pts
        assert cal.calibrated_at > 0

    def test_three_points_piecewise_mode(self):
        pts = [
            CalibrationPoint(relative_depth=0.1, real_distance_m=1.0),
            CalibrationPoint(relative_depth=0.5, real_distance_m=5.0),
            CalibrationPoint(relative_depth=0.9, real_distance_m=10.0),
        ]
        cal = calibrate_camera("cam2", pts)
        assert cal.mode == "piecewise"

    def test_empty_points_uncalibrated(self):
        cal = calibrate_camera("cam3", [])
        assert cal.mode == "uncalibrated"
        assert cal.is_calibrated is False

    def test_single_point_set_calibration(self):
        pts = [CalibrationPoint(relative_depth=0.3, real_distance_m=6.0)]
        cal = calibrate_camera("cam4", pts, prefer_piecewise=False)
        assert cal.mode == "linear"


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2.1 — relative_to_metric conversion
# ═══════════════════════════════════════════════════════════════════════

class TestRelativeToMetric:
    def test_linear_conversion(self):
        cal = CameraDepthCalibration(
            camera_id="cam1", mode="linear", scale=10.0, offset=0.0
        )
        m = relative_to_metric(0.5, cal)
        assert m == pytest.approx(5.0)

    def test_uncalibrated_returns_none(self):
        cal = CameraDepthCalibration(camera_id="cam1", mode="uncalibrated")
        m = relative_to_metric(0.5, cal)
        assert m is None

    def test_piecewise_conversion(self):
        cal = CameraDepthCalibration(
            camera_id="cam1",
            mode="piecewise",
            calibration_points=[
                CalibrationPoint(relative_depth=0.2, real_distance_m=2.0),
                CalibrationPoint(relative_depth=0.5, real_distance_m=5.0),
                CalibrationPoint(relative_depth=0.9, real_distance_m=12.0),
            ],
        )
        m = relative_to_metric(0.5, cal)
        assert m == pytest.approx(5.0, abs=0.1)


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2.1 — relative_to_metric_array
# ═══════════════════════════════════════════════════════════════════════

class TestRelativeToMetricArray:
    def test_linear_array_conversion(self):
        cal = CameraDepthCalibration(
            camera_id="cam1", mode="linear", scale=10.0, offset=0.0
        )
        depth = np.array([[0.3, 0.5], [0.7, 0.9]], dtype=np.float32)
        metric = relative_to_metric_array(depth, cal)
        assert metric is not None
        assert metric.shape == depth.shape
        np.testing.assert_allclose(metric, depth * 10.0, atol=1e-3)

    def test_uncalibrated_returns_none(self):
        cal = CameraDepthCalibration(camera_id="cam1", mode="uncalibrated")
        depth = np.array([[0.3, 0.5]], dtype=np.float32)
        metric = relative_to_metric_array(depth, cal)
        assert metric is None

    def test_piecewise_array_conversion(self):
        cal = CameraDepthCalibration(
            camera_id="cam1",
            mode="piecewise",
            calibration_points=[
                CalibrationPoint(relative_depth=0.2, real_distance_m=2.0),
                CalibrationPoint(relative_depth=0.5, real_distance_m=5.0),
                CalibrationPoint(relative_depth=0.9, real_distance_m=12.0),
            ],
        )
        depth = np.array([[0.2, 0.5], [0.9, 0.35]], dtype=np.float32)
        metric = relative_to_metric_array(depth, cal)
        assert metric is not None
        assert metric[0, 0] == pytest.approx(2.0, abs=0.1)
        assert metric[0, 1] == pytest.approx(5.0, abs=0.1)


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2.2 — Validation gate
# ═══════════════════════════════════════════════════════════════════════

class TestValidationGate:
    def _make_cal_with_points(self, scale=10.0):
        cal = CameraDepthCalibration(
            camera_id="cam1",
            mode="linear",
            scale=scale,
            offset=0.0,
            calibration_points=[
                CalibrationPoint(relative_depth=0.3, real_distance_m=3.0),
                CalibrationPoint(relative_depth=0.6, real_distance_m=6.0),
            ],
        )
        return cal

    def test_validation_passes_when_within_tolerance(self):
        cal = self._make_cal_with_points(scale=10.0)
        test_pts = [
            CalibrationPoint(relative_depth=0.2, real_distance_m=2.0, label="near"),
            CalibrationPoint(relative_depth=0.5, real_distance_m=5.0, label="mid"),
            CalibrationPoint(relative_depth=0.8, real_distance_m=8.0, label="far"),
        ]
        cal = validate_calibration(cal, test_pts)
        assert cal.validation_passed is True
        assert len(cal.validation_results) == 3

    def test_validation_fails_when_error_exceeds_tolerance(self):
        cal = self._make_cal_with_points(scale=10.0)
        # Test point expects 1.0 m but model returns 0.1*10=1.0 — actually fine.
        # Let's force a mismatch by using a wrong calibration
        cal.scale = 20.0  # wrong scale
        test_pts = [
            CalibrationPoint(relative_depth=0.2, real_distance_m=2.0, label="near"),
            CalibrationPoint(relative_depth=0.5, real_distance_m=5.0, label="mid"),
            CalibrationPoint(relative_depth=0.8, real_distance_m=8.0, label="far"),
        ]
        cal = validate_calibration(cal, test_pts)
        assert cal.validation_passed is False

    def test_validation_uncalibrated(self):
        cal = CameraDepthCalibration(camera_id="cam1", mode="uncalibrated")
        cal = validate_calibration(cal, [])
        assert cal.validation_passed is False

    def test_validation_results_have_all_fields(self):
        cal = self._make_cal_with_points(scale=10.0)
        test_pts = [
            CalibrationPoint(relative_depth=0.3, real_distance_m=3.0, label="test"),
        ]
        cal = validate_calibration(cal, test_pts)
        r = cal.validation_results[0]
        assert "label" in r
        assert "real_m" in r
        assert "predicted_m" in r
        assert "error_m" in r
        assert "error_pct" in r
        assert "passed" in r

    def test_far_point_uses_far_tolerance(self):
        cal = CameraDepthCalibration(
            camera_id="cam1", mode="linear", scale=10.0,
            tolerance_near_m=0.3, tolerance_mid_m=1.0, tolerance_far_m=4.0,
        )
        test_pts = [
            CalibrationPoint(relative_depth=0.9, real_distance_m=10.0, label="far"),
        ]
        cal = validate_calibration(cal, test_pts)
        assert cal.validation_results[0]["passed"] is True  # 0.0 error within 4.0 tolerance


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2.4 — Drift detection
# ═══════════════════════════════════════════════════════════════════════

class TestDriftDetection:
    def _calibrated(self, scale=10.0):
        cal = CameraDepthCalibration(
            camera_id="cam1", mode="linear", scale=scale, validation_passed=True
        )
        add_drift_reference(cal, 0.3, 3.0, label="signpost")
        return cal

    def test_no_drift_when_stable(self):
        cal = self._calibrated()
        result = check_drift(cal, 0.3, reference_label="signpost")
        assert result["drifted"] is False
        assert result["status"] == "ok"

    def test_drift_warn_at_15pct(self):
        cal = self._calibrated(scale=10.0)
        # relative_depth 0.2 → predicted 2.0, reference 3.0 → error 33% > 15%
        result = check_drift(cal, 0.2, reference_label="signpost")
        assert result["drifted"] is True
        assert result["status"] == "fail"

    def test_drift_fail_at_25pct(self):
        cal = self._calibrated(scale=10.0)
        # relative_depth 0.1 → predicted 1.0, reference 3.0 → error 66%
        result = check_drift(cal, 0.1, reference_label="signpost")
        assert result["drifted"] is True
        assert result["status"] == "fail"

    def test_no_references_returns_ok(self):
        cal = CameraDepthCalibration(camera_id="cam1", mode="linear", scale=10.0)
        result = check_drift(cal, 0.5)
        assert result["drifted"] is False
        assert result["details"] == "no_references"

    def test_add_drift_reference(self):
        cal = CameraDepthCalibration(camera_id="cam1", mode="linear", scale=10.0)
        add_drift_reference(cal, 0.5, 5.0, label="landmark")
        assert len(cal.drift_references) == 1
        assert cal.drift_references[0]["label"] == "landmark"

    def test_drift_check_updates_last_drift_check(self):
        cal = self._calibrated()
        cal.last_drift_check = 0.0
        check_drift(cal, 0.3, reference_label="signpost")
        assert cal.last_drift_check > 0.0


# ═══════════════════════════════════════════════════════════════════════
#  Serialisation
# ═══════════════════════════════════════════════════════════════════════

class TestSerialisation:
    def test_to_dict_and_back(self):
        cal = CameraDepthCalibration(
            camera_id="cam-serial",
            mode="piecewise",
            scale=12.3,
            offset=1.5,
            calibration_points=[
                CalibrationPoint(relative_depth=0.2, real_distance_m=2.0, label="a"),
                CalibrationPoint(relative_depth=0.8, real_distance_m=8.0, label="b"),
            ],
            calibrated_at=1234567890.0,
            validation_passed=True,
        )
        d = cal.to_dict()
        cal2 = CameraDepthCalibration.from_dict(d)
        assert cal2.camera_id == "cam-serial"
        assert cal2.mode == "piecewise"
        assert cal2.scale == 12.3
        assert len(cal2.calibration_points) == 2
        assert cal2.calibration_points[0].label == "a"
        assert cal2.validation_passed is True

    def test_from_dict_defaults(self):
        cal = CameraDepthCalibration.from_dict({"camera_id": "x"})
        assert cal.mode == "uncalibrated"
        assert cal.scale == 1.0
        assert cal.validation_passed is False


# ═══════════════════════════════════════════════════════════════════════
#  In-memory store
# ═══════════════════════════════════════════════════════════════════════

class TestInMemoryStore:
    def test_store_and_load(self):
        cal = CameraDepthCalibration(
            camera_id="Cam-Store", mode="linear", scale=10.0
        )
        store_calibration(cal)
        loaded = load_calibration("cam-store")
        assert loaded.scale == 10.0
        assert loaded.camera_id == "Cam-Store"

    def test_load_missing_returns_uncalibrated(self):
        loaded = load_calibration("nonexistent-cam-999")
        assert loaded.mode == "uncalibrated"

    def test_overwrite(self):
        cal1 = CameraDepthCalibration(camera_id="ow-test", mode="linear", scale=5.0)
        cal2 = CameraDepthCalibration(camera_id="ow-test", mode="linear", scale=15.0)
        store_calibration(cal1)
        store_calibration(cal2)
        loaded = load_calibration("ow-test")
        assert loaded.scale == 15.0
