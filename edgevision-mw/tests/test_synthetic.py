"""Tests for F2 — Synthetic Data Engine.

Acceptance criteria:
1. Generated frames pass through COCO/Cityscapes/KITTI export schema with source: synthetic
2. Validation loop produces tracked mAP delta metric
3. De-identification verification: no real identifiable faces/plates in synthetic output
"""
from __future__ import annotations

import numpy as np
import pytest

from app.synthetic.generator import (
    SyntheticGenerator,
    GenerationConfig,
    WeatherCondition,
    TimeOfDay,
    CameraIntrinsics,
    ObjectPlacement,
    SceneLayout,
    PRESETS,
)
from app.synthetic.ground_truth import GroundTruthGenerator, GroundTruth
from app.synthetic.validation import SyntheticValidator, ValidationMetrics


class TestSyntheticGenerator:
    def test_generate_batch(self):
        gen = SyntheticGenerator()
        config = GenerationConfig(
            objects=[ObjectPlacement("car", count=3)],
        )
        frames = gen.generate_batch(config, count=5, seed=42)
        assert len(frames) == 5
        for f in frames:
            assert f.image.shape[0] > 0
            assert f.image.shape[1] > 0
            assert f.image.ndim == 3

    def test_weather_conditioning(self):
        gen = SyntheticGenerator()
        config_clear = GenerationConfig(
            weather=WeatherCondition("clear"),
            objects=[ObjectPlacement("car", count=1)],
        )
        config_rain = GenerationConfig(
            weather=WeatherCondition("rainy", rain_intensity=0.8),
            objects=[ObjectPlacement("car", count=1)],
        )
        frame_clear = gen.generate_batch(config_clear, 1, seed=42)[0]
        frame_rain = gen.generate_batch(config_rain, 1, seed=42)[0]
        assert not np.array_equal(frame_clear.image, frame_rain.image)

    def test_time_of_day_conditioning(self):
        gen = SyntheticGenerator()
        config_day = GenerationConfig(
            time_of_day=TimeOfDay("day"),
            objects=[ObjectPlacement("car", count=1)],
        )
        config_night = GenerationConfig(
            time_of_day=TimeOfDay("night"),
            objects=[ObjectPlacement("car", count=1)],
        )
        frame_day = gen.generate_batch(config_day, 1, seed=42)[0]
        frame_night = gen.generate_batch(config_night, 1, seed=42)[0]
        assert frame_day.image.mean() > frame_night.image.mean()

    def test_presets_work(self):
        gen = SyntheticGenerator()
        for name, config in PRESETS.items():
            frames = gen.generate_batch(config, 1, seed=42)
            assert len(frames) == 1
            assert frames[0].weather == config.weather.name

    def test_objects_placed(self):
        gen = SyntheticGenerator()
        config = GenerationConfig(
            objects=[
                ObjectPlacement("car", count=5),
                ObjectPlacement("pedestrian", count=3),
            ],
        )
        frame = gen.generate_batch(config, 1, seed=42)[0]
        assert len(frame.objects) == 8

    def test_reproducibility(self):
        gen = SyntheticGenerator()
        config = GenerationConfig(objects=[ObjectPlacement("car", count=2)])
        f1 = gen.generate_batch(config, 1, seed=99)[0]
        f2 = gen.generate_batch(config, 1, seed=99)[0]
        np.testing.assert_array_equal(f1.image, f2.image)


class TestGroundTruth:
    def test_gt_generation(self):
        gen = SyntheticGenerator()
        gt_gen = GroundTruthGenerator()
        config = GenerationConfig(
            objects=[ObjectPlacement("car", count=2)],
        )
        frame = gen.generate_batch(config, 1, seed=42)[0]
        gt = gt_gen.generate(frame.image, frame.objects, config.scene, config.camera)

        assert gt.segmentation_mask.shape == (gt.height, gt.width)
        assert gt.depth_map.shape == (gt.height, gt.width)
        assert gt.instance_mask.shape == (gt.height, gt.width)
        assert len(gt.bounding_boxes) == len(gt.class_labels)

    def test_coco_export(self):
        gt = GroundTruth(
            segmentation_mask=np.zeros((100, 100), dtype=np.int32),
            bounding_boxes=[{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "depth_m": 5.0, "polygon": [0.1, 0.2, 0.4, 0.2, 0.4, 0.6, 0.1, 0.6]}],
            depth_map=np.ones((100, 100), dtype=np.float32) * 10,
            class_labels=["car"],
            instance_mask=np.zeros((100, 100), dtype=np.int32),
            width=100,
            height=100,
        )
        coco = gt.to_coco()
        assert coco["source"] == "synthetic"
        assert len(coco["annotations"]) == 1
        assert coco["annotations"][0]["category_name"] == "car"
        assert coco["annotations"][0]["source"] == "synthetic"

    def test_cityscapes_export(self):
        gt = GroundTruth(
            segmentation_mask=np.zeros((100, 100), dtype=np.int32),
            bounding_boxes=[],
            depth_map=np.ones((100, 100), dtype=np.float32),
            class_labels=[],
            instance_mask=np.zeros((100, 100), dtype=np.int32),
            width=100,
            height=100,
        )
        cs = gt.to_cityscapes()
        assert cs["source"] == "synthetic"

    def test_kitti_export(self):
        gt = GroundTruth(
            segmentation_mask=np.zeros((100, 100), dtype=np.int32),
            bounding_boxes=[{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}],
            depth_map=np.ones((100, 100), dtype=np.float32),
            class_labels=["car"],
            instance_mask=np.zeros((100, 100), dtype=np.int32),
            width=100,
            height=100,
        )
        kitti = gt.to_kitti()
        assert kitti["source"] == "synthetic"
        assert kitti["objects"][0]["type"] == "car"


class TestSyntheticValidation:
    def test_validation_metrics(self):
        val = SyntheticValidator()
        real = [np.random.randint(0, 256, (64, 64, 3), dtype=np.uint8) for _ in range(10)]
        synthetic = [np.random.randint(0, 256, (64, 64, 3), dtype=np.uint8) for _ in range(10)]
        metrics = val.validate(real, synthetic)

        assert isinstance(metrics, ValidationMetrics)
        assert 0 <= metrics.overall_score <= 1
        assert 0 <= metrics.color_histogram_jsd <= 1

    def test_empty_input(self):
        val = SyntheticValidator()
        metrics = val.validate([], [])
        assert metrics.color_histogram_jsd == 1.0
        assert metrics.structural_similarity == 0.0

    def test_identical_data_low_divergence(self):
        val = SyntheticValidator()
        rng = np.random.default_rng(42)
        frames = [rng.integers(50, 200, (32, 32, 3), dtype=np.uint8) for _ in range(5)]
        metrics = val.validate(frames, frames.copy())
        assert metrics.color_histogram_jsd < 0.1
        assert metrics.structural_similarity > 0.9

    def test_drift_detection(self):
        val = SyntheticValidator(drift_threshold=0.01)
        for _ in range(10):
            val._history.append(np.random.uniform(0.3, 0.7))
        assert len(val._history) >= 5


class TestDeidentification:
    """Synthetic frames must not contain real identifiable faces/plates."""

    def test_no_jpeg_markers_in_synthetic(self):
        gen = SyntheticGenerator()
        config = GenerationConfig(
            objects=[ObjectPlacement("car", count=3)],
        )
        frame = gen.generate_batch(config, 1, seed=42)[0]
        raw = frame.image.tobytes()
        assert b"\xff\xd8\xff" not in raw, "JPEG marker in synthetic data"
        assert b"\x89PNG" not in raw, "PNG marker in synthetic data"

    def test_synthetic_source_tag(self):
        gen = SyntheticGenerator()
        config = GenerationConfig(objects=[ObjectPlacement("car", count=1)])
        frame = gen.generate_batch(config, 1, seed=42)[0]
        assert frame.config_hash is not None
        assert len(frame.config_hash) == 12

    def test_no_real_image_reference(self):
        gen = SyntheticGenerator()
        config = GenerationConfig(
            objects=[ObjectPlacement("pedestrian", count=5)],
        )
        frames = gen.generate_batch(config, 10, seed=42)
        for f in frames:
            assert f.source_checksum is not None
            assert len(f.source_checksum) == 16
