from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _make_image(w: int = 320, h: int = 240) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[40:120, 30:110] = (200, 180, 120)
    return img


def _make_mock_onnx_session(*args, **kwargs) -> MagicMock:
    path = str(args[0]) if args else ""
    kind = "decoder" if "decoder" in path else "encoder"
    session = MagicMock()
    inp = MagicMock()
    inp.name = "image" if kind == "encoder" else "image_embeddings"
    session.get_inputs.return_value = [inp]

    if kind == "encoder":
        out = MagicMock()
        out.name = "image_embeddings"
        session.get_outputs.return_value = [out]

        def run(output_names, feed):
            return [np.zeros((1, 256, 64, 64), dtype=np.float32)]

        session.run.side_effect = run
    else:
        out_names = ["masks", "iou_predictions", "low_res_masks"]
        session.get_outputs.return_value = [MagicMock(name=n) for n in out_names]
        inputs = [
            MagicMock(name="image_embeddings"),
            MagicMock(name="point_coords"),
            MagicMock(name="point_labels"),
            MagicMock(name="mask_input"),
            MagicMock(name="has_mask_input"),
            MagicMock(name="orig_im_size"),
        ]
        for m in inputs:
            m.name = m.name.split(".")[0]
        session.get_inputs.return_value = inputs

        def run(output_names, feed):
            masks = np.zeros((1, 1, 256, 256), dtype=np.float32)
            masks[0, 0, 60:140, 80:200] = 0.8
            return [masks, np.zeros((1, 1)), masks]

        session.run.side_effect = run

    return session


class TestSAMSegmenter:
    def test_fallback_point_mask_shape_and_ones(self):
        from app.ai.sam_segmenter import SAMSegmenter

        seg = SAMSegmenter(
            encoder_path="/nonexistent_encoder.onnx",
            decoder_path="/nonexistent_decoder.onnx",
        )
        assert not seg.is_loaded()

        img = _make_image()
        mask = seg.predict_point(img, 80, 70)
        assert mask.shape == (240, 320)
        assert set(np.unique(mask)).issubset({0.0, 1.0})
        assert mask.sum() > 0

    def test_fallback_box_mask_respects_bounds(self):
        from app.ai.sam_segmenter import SAMSegmenter

        seg = SAMSegmenter(
            encoder_path="/nonexistent_encoder.onnx",
            decoder_path="/nonexistent_decoder.onnx",
        )
        img = _make_image()
        mask = seg.predict_box(img, 30, 40, 110, 120)
        assert mask.shape == (240, 320)
        assert mask[40:120, 30:110].all()
        assert mask[0, 0] == 0.0

    def test_onnx_pipeline_predict_box(self):
        from app.ai.sam_segmenter import SAMSegmenter

        with (
            patch("onnxruntime.InferenceSession", side_effect=_make_mock_onnx_session) as mock_load,
        ):
            seg = SAMSegmenter(
                encoder_path="/tmp/nonexistent_encoder.onnx",
                decoder_path="/tmp/nonexistent_decoder.onnx",
            )
            assert seg.is_loaded()
            assert mock_load.call_count == 2

            img = _make_image()
            mask = seg.predict_box(img, 30, 40, 110, 120)
            assert mask.shape == (240, 320)
            assert mask[70, 100] > 0.0

    def test_onnx_pipeline_predict_point(self):
        from app.ai.sam_segmenter import SAMSegmenter

        with patch("onnxruntime.InferenceSession", side_effect=_make_mock_onnx_session):
            seg = SAMSegmenter(
                encoder_path="/tmp/nonexistent_encoder.onnx",
                decoder_path="/tmp/nonexistent_decoder.onnx",
            )
            img = _make_image()
            mask = seg.predict_point(img, 80, 70)
            assert mask.shape == (240, 320)

    def test_mask_to_rle_raises_without_pycocotools(self):
        from app.ai.mask_utils import mask_to_rle, pycocotools_available

        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[10:20, 10:20] = 1
        if pycocotools_available():
            rle = mask_to_rle(mask)
            assert rle
        else:
            with pytest.raises(ImportError):
                mask_to_rle(mask)
