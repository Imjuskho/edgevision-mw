from __future__ import annotations

import numpy as np
import pytest


class TestDepthEstimator:
    def test_heuristic_fallback_when_no_model(self, monkeypatch):
        from app.ai import depth_estimator as de

        monkeypatch.setattr(de, "_find_model", lambda: None)
        est = de.DepthEstimator()
        img = np.zeros((100, 80, 3), dtype=np.uint8)
        depth, available = est.estimate_depth_map(img)
        assert depth.shape == (100, 80)
        assert available is False
        assert not est.is_loaded()

    def test_depth_at_bbox_lower_third_bias(self):
        from app.ai.depth_estimator import DepthEstimator

        est = DepthEstimator(model_path="/nonexistent")
        depth_map = np.linspace(0.0, 1.0, 100, dtype=np.float32).reshape(100, 1)
        depth_map = np.broadcast_to(depth_map, (100, 100)).copy()
        median, quality = est.depth_at_bbox(depth_map, [0.0, 0.0, 1.0, 1.0])
        assert 0.0 <= median <= 1.0
        assert quality in ("biased_lower_third", "full_bbox", "fallback_center")

    def test_singleton_pattern(self):
        from app.ai.depth_estimator import get_depth_estimator

        a = get_depth_estimator()
        b = get_depth_estimator()
        assert a is b


class TestDepthEstimatorOnnx:
    def test_onnx_inference_when_session_available(self, monkeypatch):
        pytest.importorskip("onnxruntime")
        from app.ai.depth_estimator import DepthEstimator

        class FakeSession:
            def get_inputs(self):
                return [type("Inp", (), {"name": "image"})()]

            def run(self, *_args, **_kwargs):
                return [np.ones((1, 1, 256, 256), dtype=np.float32)]

        est = DepthEstimator(model_path="/fake/model.onnx")
        est._session = FakeSession()
        est._input_name = "image"

        img = np.random.randint(0, 255, (120, 160, 3), dtype=np.uint8)
        depth, available = est.estimate_depth_map(img)
        assert depth.shape == (120, 160)
        assert available is True
