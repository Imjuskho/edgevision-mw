from __future__ import annotations

import io
import sys
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


def _make_image_bytes(width: int = 320, height: int = 240) -> bytes:
    img = Image.new("RGB", (width, height), (100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_locate_anything_falls_back_when_package_missing():
    from app.ai.locate_anything import LocateAnythingSegmenter

    with patch.dict(sys.modules, {"locateanything": None}):
        seg = LocateAnythingSegmenter(model_path="/tmp/nonexistent.onnx")
        assert not seg.is_loaded()
        assert seg.detect(_make_image_bytes()) == []


def test_locate_anything_detects_using_locate_if_available():
    fake_model = MagicMock()
    fake_model.locate.return_value = [
        {
            "class_name": "car",
            "confidence": 0.92,
            "bbox": [0.1, 0.1, 0.4, 0.3],
            "mask": [[0, 1], [1, 0]],
        }
    ]

    fake_module = MagicMock()
    fake_module.load_model.return_value = fake_model

    with patch.dict(sys.modules, {"locateanything": fake_module}):
        from app.ai.locate_anything import LocateAnythingSegmenter

        seg = LocateAnythingSegmenter(model_path="/tmp/fake_model.onnx")
        assert seg.is_loaded()

        detections = seg.detect(_make_image_bytes())
        assert len(detections) == 1
        det = detections[0]
        assert det["class_name"] == "car"
    assert det["confidence"] == pytest.approx(0.92, rel=1e-5)
    assert det["bbox"] == pytest.approx([0.1, 0.1, 0.4, 0.3], rel=1e-5)
