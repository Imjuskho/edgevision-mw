"""Optional monocular depth estimation for 3D bounding boxes."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.depth_estimator")

_DEPTH_MODEL_FILENAME = "depth_anything_v2_vits.onnx"
_INFERENCE_SIZE = 256
_ORIGINAL_INPUT_SIZE = 518


def _find_model() -> Path | None:
    from app.core.config import settings

    candidates = []
    depth_path = getattr(settings, "DEPTH_MODEL_PATH", None) or getattr(settings, "DEPTH_ANYTHING_MODEL_PATH", None)
    if depth_path:
        candidates.append(Path(depth_path))
    candidates.append(Path(__file__).resolve().parents[2] / f"frontend/public/models/{_DEPTH_MODEL_FILENAME}")
    for p in candidates:
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


class DepthEstimator:
    """Lazy Depth-Anything-V2-Small ONNX depth map with heuristic fallback."""

    def __init__(self, model_path: str | None = None):
        self._model_path = model_path or _find_model()
        self._session = None
        self._input_name: str | None = None
        self._lock = threading.Lock()
        self._last_inference_ms: float = 0.0
        self._load()

    def _load(self) -> None:
        if self._model_path is None:
            logger.info("depth_estimator_heuristic_only", reason="model_missing")
            return
        try:
            import onnxruntime as ort

            providers = [p for p in ("CPUExecutionProvider",) if p in ort.get_available_providers()]
            self._session = ort.InferenceSession(str(self._model_path), providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            logger.info("depth_estimator_loaded", model_path=str(self._model_path))
        except Exception as exc:
            logger.warning("depth_estimator_load_failed", error=str(exc))
            self._session = None

    def is_loaded(self) -> bool:
        return self._session is not None

    @property
    def last_inference_ms(self) -> float:
        return self._last_inference_ms

    def estimate_depth_map(self, image: np.ndarray) -> tuple[np.ndarray, bool]:
        """Return ``(depth_map, depth_available)`` where depth is higher = farther."""
        if self._session is None or self._input_name is None:
            return self._heuristic_depth(image), False

        try:
            import cv2

            start = time.perf_counter()
            h, w = image.shape[:2]
            if image.ndim == 2:
                rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            elif image.shape[2] == 4:
                rgb = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
            else:
                rgb = image

            inp_size = _INFERENCE_SIZE
            resized = cv2.resize(rgb, (inp_size, inp_size))
            blob = np.transpose(resized.astype(np.float32) / 255.0, (2, 0, 1))[np.newaxis]
            with self._lock:
                outputs = self._session.run(None, {self._input_name: blob})
            depth = np.squeeze(outputs[0])
            if depth.ndim > 2:
                depth = depth[0]
            depth = cv2.resize(depth.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
            depth = depth - depth.min()
            denom = depth.max()
            if denom > 0:
                depth = depth / denom
            self._last_inference_ms = (time.perf_counter() - start) * 1000
            return depth.astype(np.float32), True
        except Exception as exc:
            logger.warning("depth_estimator_inference_failed", error=str(exc))
            return self._heuristic_depth(image), False

    @staticmethod
    def _heuristic_depth(image: np.ndarray) -> np.ndarray:
        """Vertical gradient fallback: lower pixels assumed closer."""
        h, w = image.shape[:2]
        y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, np.newaxis]
        depth = np.broadcast_to(y, (h, w)).copy()
        return depth

    def depth_at_bbox(
        self,
        depth_map: np.ndarray,
        bbox_xywh: list[float],
        *,
        lower_third_bias: float = 0.66,
        mask: np.ndarray | None = None,
    ) -> tuple[float, str]:
        """Median relative depth inside bbox with lower-third vertical bias.

        When a segmentation ``mask`` (H×W bool or uint8) is provided, depth is
        sampled only from masked pixels — avoiding background/edge contamination
        on irregular or overlapping objects.  Falls back to bbox-based sampling
        when no mask is supplied or the mask contains fewer than 5 valid pixels.
        """
        h, w = depth_map.shape[:2]
        x, y, bw, bh = bbox_xywh
        x1 = max(0, int(x * w))
        y1 = max(0, int(y * h))
        x2 = min(w, int((x + bw) * w))
        y2 = min(h, int((y + bh) * h))
        if x2 <= x1 or y2 <= y1:
            return 0.5, "fallback_center"

        # --- Mask-based sampling (preferred) ---
        if mask is not None and mask.shape[:2] == (h, w):
            mask_region = mask[y1:y2, x1:x2]
            if mask_region.size > 0:
                bool_mask = mask_region.astype(bool) if mask_region.dtype != bool else mask_region
                if bool_mask.sum() >= 5:
                    depth_region = depth_map[y1:y2, x1:x2]
                    masked_depths = depth_region[bool_mask]
                    median = float(np.median(masked_depths))
                    return median, "mask_median"

        # --- Fallback: bbox lower-third bias ---
        region = depth_map[y1:y2, x1:x2]
        if region.size == 0:
            return 0.5, "fallback_center"

        rh = region.shape[0]
        bias_start = int(rh * (1.0 - lower_third_bias))
        biased = region[bias_start:, :] if bias_start < rh else region
        median = float(np.median(biased if biased.size else region))
        quality = "biased_lower_third" if biased.size and bias_start > 0 else "full_bbox"
        return median, quality

    @staticmethod
    def verify_ordering(
        depth_map: np.ndarray,
        near_bbox: list[float],
        far_bbox: list[float],
        *,
        mask_near: np.ndarray | None = None,
        mask_far: np.ndarray | None = None,
    ) -> dict:
        """Phase 1.1 ordering check: verify closer objects have lower relative depth.

        Returns a dict with ``consistent`` (bool), ``near_depth``, ``far_depth``,
        and ``delta``.  Depth-Anything-V2 convention: higher value = farther, so
        ``near_depth`` should be < ``far_depth`` for consistent ordering.
        """
        est = DepthEstimator(model_path="/nonexistent")
        near_d, near_q = est.depth_at_bbox(depth_map, near_bbox, mask=mask_near)
        far_d, far_q = est.depth_at_bbox(depth_map, far_bbox, mask=mask_far)
        return {
            "consistent": near_d < far_d,
            "near_depth": near_d,
            "near_quality": near_q,
            "far_depth": far_d,
            "far_quality": far_q,
            "delta": far_d - near_d,
        }


_estimator: DepthEstimator | None = None
_estimator_lock = threading.Lock()


def get_depth_estimator() -> DepthEstimator:
    """Return the process-wide lazy depth estimator singleton."""
    global _estimator
    if _estimator is None:
        with _estimator_lock:
            if _estimator is None:
                _estimator = DepthEstimator()
    return _estimator
