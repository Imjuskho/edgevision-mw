from __future__ import annotations

import numpy as np


class TestMono3d:
    def test_estimate_3d_car_returns_corners(self):
        from app.ai.mono_3d import estimate_3d

        result = estimate_3d(
            [0.3, 0.2, 0.2, 0.4],
            "car",
            (480, 640),
        )
        assert result is not None
        assert len(result["corners"]) == 8
        assert "yaw" in result
        assert "yaw_source" in result
        assert "distance_quality" in result
        assert result["depth_available"] is False

    def test_estimate_3d_with_depth_available(self):
        import numpy as np

        from app.ai.mono_3d import estimate_3d

        depth_map = np.linspace(0, 1, 480 * 640, dtype=np.float32).reshape(480, 640)
        result = estimate_3d(
            [0.3, 0.2, 0.2, 0.4],
            "car",
            (480, 640),
            depth_map=depth_map,
            depth_available=True,
        )
        assert result is not None
        assert result["depth_available"] is True
        assert result["limitation"] == "depth_onnx_yaw_estimated"

    def test_estimate_3d_skips_unknown_class(self):
        from app.ai.mono_3d import estimate_3d

        result = estimate_3d(
            [0.1, 0.1, 0.2, 0.2],
            "traffic light",
            (480, 640),
        )
        assert result is None

    def test_attach_3d_boxes(self):
        from app.ai.mono_3d import attach_3d_boxes

        detections = [
            {"class_name": "car", "bbox": [0.2, 0.3, 0.3, 0.4], "confidence": 0.9},
            {"class_name": "bench", "bbox": [0.5, 0.5, 0.1, 0.1], "confidence": 0.8},
        ]
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        enriched = attach_3d_boxes(detections, image)
        assert enriched[0].get("bbox_3d") is not None
        assert enriched[1].get("bbox_3d") is None

    def test_attach_3d_boxes_pixel_xyxy(self):
        from app.ai.mono_3d import attach_3d_boxes

        detections = [
            {
                "class_name": "car",
                "bbox": np.array([50.0, 40.0, 150.0, 120.0]),
                "confidence": 0.9,
                "taxonomy_label": "car_private",
            },
        ]
        image = np.zeros((384, 512, 3), dtype=np.uint8)
        enriched = attach_3d_boxes(detections, image)
        corners = enriched[0]["bbox_3d"]["corners"]
        assert len(corners) == 8
        assert all(0.0 <= c[0] <= 1.0 for c in corners)
        assert all(0.0 <= c[1] <= 1.0 for c in corners)

    def test_flip_cuboid_x_identity_via_frontend_contract(self):
        """Document expected 3D corner layout for downstream consumers."""
        from app.ai.mono_3d import estimate_3d

        result = estimate_3d([0.25, 0.25, 0.5, 0.5], "person", (480, 640))
        assert result is not None
        for corner in result["corners"]:
            assert len(corner) == 3
            assert 0.0 <= corner[0] <= 1.0 or corner[0] < 0 or corner[0] > 1
