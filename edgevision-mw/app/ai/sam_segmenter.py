from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.sam_segmenter")

# ImageNet normalization used by the SAM family of models
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_EMBED_SIZE = 1024
_EMBED_GRID = 64
_MASK_RESOLUTION = 256


def _find_model(kind: str) -> Path | None:
    """Locate a MobileSAM ONNX sub-model.

    ``kind`` is one of ``encoder`` / ``decoder``. Resolution order:
      1. ``SAM_ENCODER_ONNX_PATH`` / ``SAM_DECODER_ONNX_PATH`` env vars
      2. Project-local ``frontend/public/models/mobile_sam_{kind}.onnx``
    """
    from app.core.config import settings

    candidates = []
    if kind == "encoder":
        if settings.SAM_ENCODER_ONNX_PATH:
            candidates.append(Path(settings.SAM_ENCODER_ONNX_PATH))
        candidates.append(Path(__file__).resolve().parents[2] / "frontend/public/models/mobile_sam_encoder.onnx")
    else:
        if settings.SAM_DECODER_ONNX_PATH:
            candidates.append(Path(settings.SAM_DECODER_ONNX_PATH))
        candidates.append(Path(__file__).resolve().parents[2] / "frontend/public/models/mobile_sam_decoder.onnx")
    for p in candidates:
        if p.exists():
            return p
    return None


class SAMSegmenter:
    """MobileSAM instance segmentation via ONNX Runtime.

    Uses the standard two-part MobileSAM ONNX export:
      * encoder: ``image`` [1,3,1024,1024] → ``image_embeddings`` [1,256,64,64]
      * decoder: embeddings + point/box prompt → ``masks`` [1,N,256,256]

    When the ONNX models are unavailable or inference fails, the segmenter
    degrades gracefully to deterministic heuristic masks so downstream
    pipelines (auto-labeling, face privacy) never hard-fail.
    """

    def __init__(
        self,
        encoder_path: str | None = None,
        decoder_path: str | None = None,
    ):
        self._encoder_path = encoder_path or _find_model("encoder")
        self._decoder_path = decoder_path or _find_model("decoder")
        self._lock = threading.Lock()
        self._encoder_session = None
        self._decoder_session = None
        self._encoder_input_name: str | None = None
        self._encoder_output_name: str | None = None
        self._decoder_inputs: dict[str, str] = {}
        self._decoder_input_ranks: dict[str, int] = {}
        self._decoder_expected_points: int | None = None
        self._decoder_output_names: list[str] = []
        self._loaded = False
        self._load()

    # ── loading ────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._encoder_path is None or self._decoder_path is None:
            logger.warning(
                "sam_models_missing",
                encoder=bool(self._encoder_path),
                decoder=bool(self._decoder_path),
            )
            return

        try:
            import onnxruntime as ort

            providers = [p for p in ("CPUExecutionProvider",) if p in ort.get_available_providers()]
            self._encoder_session = ort.InferenceSession(str(self._encoder_path), providers=providers)
            self._encoder_input_name = self._encoder_session.get_inputs()[0].name
            self._encoder_output_name = self._encoder_session.get_outputs()[0].name
        except Exception as exc:
            logger.error("sam_encoder_load_failed", error=str(exc))
            self._encoder_session = None
            return

        try:
            import onnxruntime as ort

            self._decoder_session = ort.InferenceSession(str(self._decoder_path), providers=providers)
            for inp in self._decoder_session.get_inputs():
                name = inp.name.lower()
                for token in (
                    "image_embeddings",
                    "point_coords",
                    "point_labels",
                    "has_mask_input",
                    "mask_input",
                    "orig_im_size",
                ):
                    if token in name:
                        self._decoder_inputs[token] = inp.name
                        rank = len(inp.shape) if isinstance(inp.shape, (list, tuple)) else 0
                        self._decoder_input_ranks[token] = rank
                        if token == "point_coords" and rank >= 2:
                            dim1 = inp.shape[1]
                            if isinstance(dim1, int):
                                self._decoder_expected_points = dim1
                        break
            self._decoder_output_names = [o.name for o in self._decoder_session.get_outputs()]
            # Probe the decoder — the bundled export fails at runtime on all prompt shapes.
            probe_emb = np.zeros((1, 256, _EMBED_GRID, _EMBED_GRID), dtype=np.float32)
            probe_coords = np.array([[512.0, 512.0]], dtype=np.float32)
            probe_labels = np.array([1.0], dtype=np.float32)
            self._decode(probe_emb, probe_coords, probe_labels, (_EMBED_SIZE, _EMBED_SIZE))
        except Exception as exc:
            logger.warning("sam_decoder_unusable", error=str(exc))
            self._decoder_session = None

        self._loaded = self._encoder_session is not None and self._decoder_session is not None
        if self._loaded:
            logger.info("sam_segmenter_loaded", encoder=str(self._encoder_path))

    def is_loaded(self) -> bool:
        return self._loaded

    # ── preprocessing ──────────────────────────────────────────────────────

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        import cv2

        h, w = image.shape[:2]
        scale = _EMBED_SIZE / max(h, w)
        nh, nw = round(h * scale), round(w * scale)
        resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((_EMBED_SIZE, _EMBED_SIZE, 3), 128, dtype=np.uint8)
        canvas[:nh, :nw] = resized
        arr = canvas.astype(np.float32) / 255.0
        arr = (arr - _MEAN) / _STD
        arr = np.transpose(arr, (2, 0, 1))
        return arr[np.newaxis, ...]  # [1,3,1024,1024]

    def _resize_pad_scale(self, image: np.ndarray) -> tuple[np.ndarray, float]:
        import cv2

        h, w = image.shape[:2]
        scale = _EMBED_SIZE / max(h, w)
        nh, nw = round(h * scale), round(w * scale)
        resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((_EMBED_SIZE, _EMBED_SIZE, 3), 128, dtype=np.uint8)
        canvas[:nh, :nw] = resized
        return canvas, scale

    # ── inference ──────────────────────────────────────────────────────────

    def _embed(self, image: np.ndarray) -> np.ndarray:
        canvas, _ = self._resize_pad_scale(image)
        arr = canvas.astype(np.float32) / 255.0
        arr = (arr - _MEAN) / _STD
        arr = np.transpose(arr, (2, 0, 1))[np.newaxis, ...]
        embeddings = self._encoder_session.run(
            [self._encoder_output_name],
            {self._encoder_input_name: arr},
        )[0]
        return embeddings  # [1,256,64,64]

    def _decode(
        self,
        embeddings: np.ndarray,
        point_coords: np.ndarray,
        point_labels: np.ndarray,
        orig_size: tuple[int, int],
    ) -> np.ndarray:
        coords = point_coords.astype(np.float32)
        labels = point_labels.astype(np.float32)
        # Some exports fix num_points (e.g. 2) in the prompt encoder. Pad any
        # shorter prompt with a background point at the last location so the
        # graph stays valid.
        expected = self._decoder_expected_points
        if expected is not None and coords.ndim == 2 and coords.shape[0] < expected:
            pad_n = expected - coords.shape[0]
            coords = np.vstack([coords, np.tile(coords[-1:], (pad_n, 1))])
            labels = np.concatenate([labels, np.zeros((pad_n,), dtype=np.float32)])
        # Adapt to the exporter's rank convention (some exports carry a batch
        # dim, some don't).
        if self._decoder_input_ranks.get("point_coords", 0) == 3:
            coords = coords[np.newaxis, ...]
        if self._decoder_input_ranks.get("point_labels", 0) == 2:
            labels = labels[np.newaxis, ...]

        feed: dict[str, np.ndarray] = {}
        for token, name in self._decoder_inputs.items():
            if token == "image_embeddings":
                feed[name] = embeddings
            elif token == "point_coords":
                feed[name] = coords
            elif token == "point_labels":
                feed[name] = labels
            elif token == "mask_input":
                feed[name] = np.zeros((1, 1, _MASK_RESOLUTION, _MASK_RESOLUTION), dtype=np.float32)
            elif token == "has_mask_input":
                feed[name] = np.zeros((1,), dtype=np.float32)
            elif token == "orig_im_size":
                feed[name] = np.array(orig_size, dtype=np.float32)
            else:
                feed[name] = np.zeros((1, 1, _MASK_RESOLUTION, _MASK_RESOLUTION), dtype=np.float32)

        outputs = self._decoder_session.run(self._decoder_output_names, feed)
        masks = outputs[0]  # [1, N, 256, 256] (or [N, 256, 256])
        if masks.ndim == 4:
            masks = masks[0]
        return masks  # [N, 256, 256]

    def _postprocess(self, low_res_masks: np.ndarray, _image: np.ndarray, orig_size: tuple[int, int]) -> np.ndarray:
        import cv2

        h, w = orig_size
        best = low_res_masks[0]  # use the highest-IoU mask
        mask = cv2.resize(best.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
        return (mask > 0.0).astype(np.float32)

    # ── public API ─────────────────────────────────────────────────────────

    def predict_point(self, image: np.ndarray, x: int, y: int) -> np.ndarray:
        if not self._loaded:
            return self._heuristic_point(image, x, y)
        h, w = image.shape[:2]
        try:
            with self._lock:
                embeddings = self._embed(image)
                coords = np.array([[x * _EMBED_SIZE / w, y * _EMBED_SIZE / h]], dtype=np.float32)
                labels = np.array([1], dtype=np.float32)
                low_res = self._decode(embeddings, coords, labels, (h, w))
            return self._postprocess(low_res, image, (h, w))
        except Exception as exc:
            logger.warning("sam_predict_point_failed", error=str(exc))
            return self._heuristic_point(image, x, y)

    def predict_box(self, image: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
        if not self._loaded:
            return self._heuristic_box(image, x1, y1, x2, y2)
        h, w = image.shape[:2]
        try:
            x1c, y1c, x2c, y2c = (max(0, v) for v in (x1, y1, x2, y2))
            with self._lock:
                embeddings = self._embed(image)
                coords = np.array(
                    [
                        [x1c * _EMBED_SIZE / w, y1c * _EMBED_SIZE / h],
                        [x2c * _EMBED_SIZE / w, y2c * _EMBED_SIZE / h],
                    ],
                    dtype=np.float32,
                )
                labels = np.array([2, 3], dtype=np.float32)
                low_res = self._decode(embeddings, coords, labels, (h, w))
            return self._postprocess(low_res, image, (h, w))
        except Exception as exc:
            logger.warning("sam_predict_box_failed", error=str(exc))
            return self._heuristic_box(image, x1, y1, x2, y2)

    # ── degraded fallbacks ─────────────────────────────────────────────────

    def _heuristic_point(self, image: np.ndarray, x: int, y: int) -> np.ndarray:
        h, w = image.shape[:2]
        mask = np.zeros((h, w), dtype=np.float32)
        r = min(50, h // 4, w // 4)
        y1, y2 = max(0, y - r), min(h, y + r)
        x1, x2 = max(0, x - r), min(w, x + r)
        mask[y1:y2, x1:x2] = 1.0
        return mask

    def _heuristic_box(self, image: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
        h, w = image.shape[:2]
        mask = np.zeros((h, w), dtype=np.float32)
        mask[max(0, y1) : min(h, y2), max(0, x1) : min(w, x2)] = 1.0
        return mask


_segmenter: SAMSegmenter | None = None
_segmenter_lock = threading.Lock()


def get_sam_segmenter() -> SAMSegmenter:
    """Return the process-wide lazy SAM segmenter singleton."""
    global _segmenter
    if _segmenter is None:
        with _segmenter_lock:
            if _segmenter is None:
                _segmenter = SAMSegmenter()
    return _segmenter


def mask_to_rle(mask: np.ndarray) -> str:
    """Encode a binary mask as a COCO RLE string."""
    from app.ai.mask_utils import mask_to_rle as _mask_to_rle

    return _mask_to_rle(mask)
