from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image


def _make_test_image(width: int = 320, height: int = 240) -> bytes:
    img = Image.new("RGB", (width, height), (120, 120, 120))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_mock_session():
    session = MagicMock()
    inp = MagicMock()
    inp.name = "images"
    session.get_inputs.return_value = [inp]
    session.get_outputs.return_value = [MagicMock(name="output0"), MagicMock(name="output1")]

    def run(output_names, feed):
        # one detection: box centered (0.5, 0.5) size 0.4, class 2 (car)
        pred = np.zeros(116, dtype=np.float32)
        pred[0] = 0.5 * 640
        pred[1] = 0.5 * 640
        pred[2] = 0.4 * 640
        pred[3] = 0.4 * 640
        pred[4 + 2] = 0.9
        coeffs = np.zeros(32, dtype=np.float32)
        coeffs[0] = 1.0
        pred[84:116] = coeffs
        out0 = pred[np.newaxis, np.newaxis, :].transpose(0, 2, 1)
        proto = np.zeros((1, 32, 160, 160), dtype=np.float32)
        proto[0, 0] = 0.8
        return [out0, proto]

    session.run.side_effect = run
    return session


class TestYoloSeg:
    def test_missing_model_returns_empty(self):
        from app.ai.yolo_seg import YoloSegSegmenter

        seg = YoloSegSegmenter(model_path="/nonexistent/model.onnx")
        assert not seg.is_loaded()
        assert seg.detect(b"not an image") == []

    def test_detect_returns_real_detections(self):
        from app.ai.yolo_seg import YoloSegSegmenter

        with patch("onnxruntime.InferenceSession", return_value=_make_mock_session()):
            seg = YoloSegSegmenter(model_path="/tmp/yolo.onnx")
            assert seg.is_loaded()

            dets = seg.detect(_make_test_image(), conf_threshold=0.3)
            assert len(dets) == 1
            det = dets[0]
            assert det["class_name"] == "car"
            assert det["taxonomy"] == "car_private"
            assert det["confidence"] > 0.8
            assert len(det["bbox"]) == 4
            assert det["mask"].shape == (240, 320)
            assert det["mask"].any()

    def test_detect_empty_below_threshold(self):
        from app.ai.yolo_seg import YoloSegSegmenter

        with patch("onnxruntime.InferenceSession", return_value=_make_mock_session()):
            seg = YoloSegSegmenter(model_path="/tmp/yolo.onnx")
            dets = seg.detect(_make_test_image(), conf_threshold=0.99)
            assert dets == []

    def test_assign_masks_by_iou(self):
        from app.ai.yolo_seg import assign_masks

        detections = [
            {
                "label": "car_private",
                "confidence": 0.9,
                "bbox": [0.3, 0.3, 0.4, 0.4],
            }
        ]
        mask = np.zeros((100, 100), dtype=bool)
        mask[30:70, 30:70] = True
        instances = [
            {
                "class_name": "car",
                "bbox": [0.29, 0.29, 0.42, 0.42],
                "mask": mask,
            }
        ]
        result = assign_masks(detections, instances)
        assert result[0]["mask"] is mask
        assert result[0]["mask_iou"] > 0.5

    def test_assign_masks_no_overlap_keeps_bbox_only(self):
        from app.ai.yolo_seg import assign_masks

        detections = [
            {
                "label": "car_private",
                "bbox": [0.1, 0.1, 0.2, 0.2],
                "confidence": 0.9,
            }
        ]
        mask = np.zeros((100, 100), dtype=bool)
        mask[70:90, 70:90] = True
        instances = [{"class_name": "car", "bbox": [0.7, 0.7, 0.2, 0.2], "mask": mask}]
        result = assign_masks(detections, instances)
        assert "mask" not in result[0]


@pytest.mark.asyncio
async def test_auto_label_falls_back_to_yolo_seg_when_sam_unavailable():
    """Auto-label must prefer SAM masks and fall back to YOLOv8-seg."""
    import app.workers.tasks as tasks_mod

    class FakeResult:
        def __init__(self, batch):
            self._batch = batch

        def scalar_one_or_none(self):
            return self._batch

    class FakeSession:
        def __init__(self, batch):
            self._batch = batch

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, stmt):
            return FakeResult(self._batch)

        def add(self, obj):
            pass

        async def commit(self):
            pass

    batch = MagicMock()
    batch.id = __import__("uuid").uuid4()
    batch.batch_id = "batch-1"
    batch.node_id = __import__("uuid").uuid4()
    batch.event_count = 1

    class FakeObj:
        def read(self):
            return _make_test_image()

    mc = MagicMock()
    mc.get_object.return_value = FakeObj()

    seg_mock = MagicMock()
    seg_mock.is_loaded.return_value = False

    yolo_mock = MagicMock()
    yolo_mock.is_loaded.return_value = True
    inst_mask = np.zeros((100, 100), dtype=bool)
    inst_mask[30:70, 30:70] = True
    yolo_mock.detect.return_value = [
        {
            "class_name": "car",
            "taxonomy": "car_private",
            "confidence": 0.9,
            "bbox": [0.3, 0.3, 0.4, 0.4],
            "mask": inst_mask,
        }
    ]

    with (
        patch("app.core.dependencies.get_minio_client_sync", return_value=mc),
        patch("app.core.database.async_session", return_value=FakeSession(batch)),
        patch("app.ai.sam_segmenter.get_sam_segmenter", return_value=seg_mock),
        patch("app.ai.yolo_seg.get_yolo_seg_segmenter", return_value=yolo_mock),
        patch("app.services.prelabel.prelabel_image", return_value=[]),
    ):
        summary = await tasks_mod._auto_label_async("batch-1")

    assert summary["annotations_created"] == 1
    assert summary["prelabeled"] == 0
    assert yolo_mock.detect.call_count == 1
