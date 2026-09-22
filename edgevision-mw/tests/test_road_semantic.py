"""Unit tests for semantic road-scene analysis."""

from __future__ import annotations

import numpy as np
import pytest
from pycocotools import mask as mask_utils

from app.ai.metric_depth import CameraCalibration, metric_depth_map
from app.ai.road_semantic import (
    RoadSceneAnalysis,
    analyze_road_scene,
    decode_mask_rle,
)
from app.ai.road_segmenter import InstanceMaskResult


def _rle(mask_bin: np.ndarray) -> str:
    rle = mask_utils.encode(np.asfortranarray(mask_bin))
    counts = rle["counts"]
    return counts.decode("ascii") if isinstance(counts, bytes) else counts


def _instance(cid: int, cname: str, mask_bin: np.ndarray, confidence: float = 0.9, bbox=None):
    if bbox is None:
        rows = np.nonzero(mask_bin.any(axis=1))[0]
        cols = np.nonzero(mask_bin.any(axis=0))[0]
        h, w = mask_bin.shape
        if rows.size and cols.size:
            y1, y2, x1, x2 = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
            bbox = [x1 / w, y1 / h, (x2 - x1) / w, (y2 - y1) / h]
        else:
            bbox = [0.0, 0.0, 0.0, 0.0]
    return InstanceMaskResult(
        class_id=cid,
        class_name=cname,
        confidence=confidence,
        bbox=bbox,
        mask_rle=_rle(mask_bin),
    )


class TestDecodeMaskRle:
    def test_roundtrip(self):
        shape = (100, 100)
        mask = np.zeros(shape, dtype=bool)
        mask[20:60, 30:80] = True
        rle = _rle(mask)
        decoded = decode_mask_rle(rle, shape)
        assert decoded is not None
        assert np.array_equal(decoded, mask)

    def test_empty_and_none(self):
        assert decode_mask_rle(None, (10, 10)) is None
        assert decode_mask_rle("", (10, 10)) is None


class TestAnalyzeRoadScene:
    def _scene(self, image_shape=(480, 640)):
        mask = np.zeros(image_shape, dtype=bool)
        mask[300:470, 160:480] = True  # road reaching bottom center
        road = _instance(0, "good_road", mask)
        return analyze_road_scene([road], image_shape)

    def test_has_road_and_drivable_classes(self):
        scene = self._scene()
        assert scene.has_road
        assert scene.drivable_ratio > 0.2
        assert 0 in scene.drivable_class_ids

    def test_hazard_isolation(self):
        shape = (480, 640)
        road_mask = np.zeros(shape, dtype=bool)
        road_mask[300:470, 160:480] = True
        hazard_mask = np.zeros(shape, dtype=bool)
        hazard_mask[380:410, 300:340] = True
        scene = analyze_road_scene(
            [_instance(0, "good_road", road_mask), _instance(1, "pothole", hazard_mask)], shape
        )
        assert len(scene.hazards) == 1
        assert scene.hazards[0]["class_name"] == "pothole"

    def test_metric_hazard_distance(self):
        shape = (480, 640)
        cal = CameraCalibration(height_m=1.5, focal_length_px=700.0, horizon_fraction=0.35)
        metric_map = metric_depth_map(shape, cal)
        road_mask = np.zeros(shape, dtype=bool)
        road_mask[300:470, 160:480] = True
        hazard_mask = np.zeros(shape, dtype=bool)
        hazard_mask[380:410, 300:340] = True
        scene = analyze_road_scene(
            [_instance(0, "good_road", road_mask), _instance(1, "pothole", hazard_mask)],
            shape,
            metric_map=metric_map,
            calibration=cal,
        )
        assert scene.hazards[0]["distance_m"] is not None
        assert scene.hazards[0]["distance_quality"] == "metric_ground_plane"

    def test_road_continuous_no_edge_distance(self):
        shape = (480, 640)
        cal = CameraCalibration()
        metric_map = metric_depth_map(shape, cal)
        road_mask = np.zeros(shape, dtype=bool)
        road_mask[168:480, 192:448] = True
        scene = analyze_road_scene(
            [_instance(0, "good_road", road_mask)], shape, metric_map=metric_map, calibration=cal
        )
        assert scene.road_continuous_fraction >= 0.9
        assert scene.road_edge_distance_m is None
        assert scene.road_edge_quality == "road_continuous"

    def test_edge_distance_when_road_ends(self):
        shape = (480, 640)
        cal = CameraCalibration(height_m=1.5, focal_length_px=700.0, horizon_fraction=0.35)
        metric_map = metric_depth_map(shape, cal)
        road_mask = np.zeros(shape, dtype=bool)
        road_mask[300:400, 160:480] = True  # ends at row 400, not bottom
        scene = analyze_road_scene(
            [_instance(0, "good_road", road_mask)], shape, metric_map=metric_map, calibration=cal
        )
        assert scene.road_edge_distance_m is not None
        assert scene.road_edge_quality == "metric_ground_plane"
        expected = (1.5 * 700.0) / (399.0 - 0.35 * 480.0)
        assert pytest.approx(scene.road_edge_distance_m, rel=1e-3) == expected

    def test_no_instances(self):
        scene = analyze_road_scene([], (480, 640))
        assert not scene.has_road
        assert scene.road_edge_quality == "no_drivable_region"

    def test_sidewalk_and_curb_heuristics(self):
        shape = (480, 640)
        cal = CameraCalibration(horizon_fraction=0.35)
        metric_map = metric_depth_map(shape, cal)
        road_mask = np.zeros(shape, dtype=bool)
        road_mask[180:470, 192:448] = True  # narrow road in center, bands open
        scene = analyze_road_scene(
            [_instance(0, "good_road", road_mask)], shape, metric_map=metric_map, calibration=cal
        )
        assert scene.sidewalk_present
        assert scene.curb_present
        assert scene.curb_method == "geometric_boundary"
        assert len(scene.sidewalk_regions) >= 1

    def test_to_dict_shape(self):
        scene = self._scene()
        d = scene.to_dict()
        assert d["has_road"] is True
        assert "road_edge_distance_m" in d
        assert "curb_method" in d


class TestDictInstancesAccepted:
    def test_dict_style_instances(self):
        shape = (480, 640)
        mask = np.zeros(shape, dtype=bool)
        mask[300:470, 160:480] = True
        rle = _rle(mask)
        inst = {"class_id": 0, "class_name": "good_road", "confidence": 0.95, "bbox": [0.25, 0.625, 0.5, 0.354], "mask_rle": rle}
        scene = analyze_road_scene([inst], shape)
        assert scene.has_road
        assert 0 in scene.drivable_class_ids


class TestAnalysisIsDataclass:
    def test_returns_analysis(self):
        shape = (480, 640)
        mask = np.zeros(shape, dtype=bool)
        mask[300:470, 160:480] = True
        scene = analyze_road_scene([_instance(0, "good_road", mask)], shape)
        assert isinstance(scene, RoadSceneAnalysis)
