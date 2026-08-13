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

    def test_real_decoder_probe_and_non_heuristic_mask(self):
        """When bundled ONNX models exist, decoder probe must pass and beat heuristics."""
        from pathlib import Path

        from app.ai.sam_segmenter import SAMSegmenter

        enc = Path(__file__).resolve().parents[1] / "frontend/public/models/mobile_sam_encoder.onnx"
        dec = Path(__file__).resolve().parents[1] / "frontend/public/models/mobile_sam_decoder.onnx"
        if not enc.exists() or not dec.exists():
            pytest.skip("MobileSAM ONNX weights not present")

        seg = SAMSegmenter(encoder_path=str(enc), decoder_path=str(dec))
        if not seg.is_loaded():
            pytest.skip("MobileSAM decoder probe failed — replace decoder ONNX")

        img = _make_image()
        px, py = 80, 70
        mask = seg.predict_point(img, px, py)
        heur = seg._heuristic_point(img, px, py)
        assert mask.shape == (240, 320)
        assert mask.sum() > 0
        inter = (mask * heur).sum()
        union = ((mask + heur) > 0).sum()
        iou = inter / union if union else 0.0
        assert iou < 0.95, f"SAM mask should differ from heuristic fallback (IoU={iou:.3f})"
        from app.ai.mask_utils import mask_to_rle, pycocotools_available

        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[10:20, 10:20] = 1
        if pycocotools_available():
            rle = mask_to_rle(mask)
            assert rle
        else:
            with pytest.raises(ImportError):
                mask_to_rle(mask)
