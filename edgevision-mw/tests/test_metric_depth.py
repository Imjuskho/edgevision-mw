"""Unit tests for flat-ground metric depth calibration."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.ai.metric_depth import (
    CameraCalibration,
    attach_metric_depth,
    ground_plane_distance_m,
    metric_depth_map,
    metric_distance_at_bbox,
)


class TestGroundPlaneDistance:
    def test_distance_matches_pinhole_relation(self):
        cal = CameraCalibration(height_m=1.5, focal_length_px=700.0, horizon_fraction=0.35)
        h = 480
        row = 240
        expected = (1.5 * 700.0) / (row - 0.35 * h)
        assert math.isclose(ground_plane_distance_m(row, h, cal), expected)

    def test_near_rows_are_closer(self):
        cal = CameraCalibration()
        assert ground_plane_distance_m(460, 480, cal) < ground_plane_distance_m(300, 480, cal)

    def test_horizon_or_above_is_inf(self):
        cal = CameraCalibration()
        assert math.isinf(ground_plane_distance_m(0, 480, cal))
        assert math.isinf(ground_plane_distance_m(int(0.35 * 480), 480, cal))

    def test_lower_camera_height_yields_closer_distance(self):
        low = CameraCalibration(height_m=1.0, focal_length_px=700.0)
        high = CameraCalibration(height_m=2.0, focal_length_px=700.0)
        assert ground_plane_distance_m(300, 480, low) < ground_plane_distance_m(300, 480, high)


class TestMetricDepthMap:
    def test_shape_and_finite_values(self):
        cal = CameraCalibration()
        depth = metric_depth_map((480, 640), cal)
        assert depth.shape == (480, 640)
        assert depth.dtype == np.float32
        bottom = depth[479, :]
        assert bottom.min() > 0 and np.isfinite(bottom).all()
        assert np.all(depth[0, :] == 0.0)

    def test_bottom_is_closer_than_middle(self):
        cal = CameraCalibration()
        depth = metric_depth_map((480, 640), cal)
        assert depth[479, 0] < depth[300, 0]


class TestMetricDistanceAtBbox:
    def test_pixel_xyxy_bbox(self):
        cal = CameraCalibration(height_m=1.5, focal_length_px=700.0, horizon_fraction=0.35)
        shape = (480, 640)
        meters, quality = metric_distance_at_bbox([100.0, 300.0, 200.0, 470.0], shape, cal)
        assert quality == "metric_ground_plane"
        expected = (1.5 * 700.0) / (470.0 - 1.0 - 0.35 * 480.0)
        assert math.isclose(meters, expected, rel_tol=1e-3)

    def test_normalized_xywh_bbox(self):
        cal = CameraCalibration()
        shape = (480, 640)
        meters_n, _ = metric_distance_at_bbox([0.2, 0.5, 0.3, 0.4], shape, cal)
        meters_p, _ = metric_distance_at_bbox([0.2 * 640, 0.5 * 480, 0.5 * 640, 0.9 * 480], shape, cal)
        assert math.isclose(meters_n, meters_p, rel_tol=1e-3)

    def test_bbox_above_horizon_unknown(self):
        cal = CameraCalibration()
        meters, quality = metric_distance_at_bbox([0.1, 0.05, 0.2, 0.2], (480, 640), cal)
        assert math.isinf(meters)
        assert quality == "below_horizon_unknown"


class TestAttachMetricDepth:
    def test_attaches_fields(self):
        dets = [
            {"bbox": [0, 200, 100, 460], "class_name": "person", "confidence": 0.9},
            {"bbox": [300, 400, 400, 470], "class_name": "car", "confidence": 0.8},
        ]
        out = attach_metric_depth(dets, (480, 640))
        assert len(out) == 2
        for det in out:
            assert det["distance_m"] is not None
            assert det["distance_quality"] == "metric_ground_plane"
            assert det["depth_units"] == "meters"

    def test_empty_input(self):
        assert attach_metric_depth([], (480, 640)) == []

    def test_bbox_above_horizon_gets_none(self):
        dets = [{"bbox": [0, 0, 50, 100], "class_name": "car", "confidence": 0.9}]
        out = attach_metric_depth(dets, (480, 640))
        assert out[0]["distance_m"] is None
        assert out[0]["distance_quality"] == "below_horizon_unknown"

    def test_near_bbox_closer_than_far_bbox(self):
        near = attach_metric_depth([{"bbox": [0, 450, 100, 479]}], (480, 640))[0]["distance_m"]
        far = attach_metric_depth([{"bbox": [0, 250, 100, 350]}], (480, 640))[0]["distance_m"]
        assert near is not None and far is not None
        assert near < far

    def test_custom_calibration_respected(self):
        cal = CameraCalibration(height_m=2.2, focal_length_px=900.0, horizon_fraction=0.3)
        det = {"bbox": [0, 300, 100, 470]}
        out = attach_metric_depth([dict(det)], (480, 640), cal)[0]
        expected = (2.2 * 900.0) / (470.0 - 1.0 - 0.3 * 480.0)
        assert pytest.approx(out["distance_m"], rel=1e-3) == expected
