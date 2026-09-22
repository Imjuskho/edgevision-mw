from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.locate_anything")


def _find_model() -> Path | None:
    """Locate the LocateAnything model artifact.

    Resolution order:
      1. ``LOCATE_ANYTHING_MODEL_PATH`` environment variable
      2. Project-local ``frontend/public/models/locate_anything.onnx``
    """
    from app.core.config import settings

    candidates = []
    if settings.LOCATE_ANYTHING_MODEL_PATH:
        candidates.append(Path(settings.LOCATE_ANYTHING_MODEL_PATH))
    candidates.append(Path(__file__).resolve().parents[2] / "frontend/public/models/locate_anything.onnx")
    for p in candidates:
        if p.exists():
            return p
    return None


class LocateAnythingSegmenter:
    """Optional NVIDIA LocateAnything instance segmentation wrapper."""

    def __init__(self, model_path: str | None = None):
        self._model_path = model_path or _find_model()
        self._lock = threading.Lock()
        self._model = None
        self._loaded = False
        self._load()

    def _load(self) -> None:
        try:
            import locateanything as la
        except ImportError:
            logger.info("locate_anything_package_missing")
            return

        if self._model_path is None:
            logger.warning("locate_anything_model_missing", model_path=self._model_path)
            return

        try:
            if hasattr(la, "load_model"):
                self._model = la.load_model(str(self._model_path))
            elif hasattr(la, "LocateAnything"):
                locator_cls = la.LocateAnything
                if hasattr(locator_cls, "from_pretrained"):
                    self._model = locator_cls.from_pretrained(str(self._model_path))
                else:
                    self._model = locator_cls()
            else:
                self._model = None

            if self._model is None:
                raise RuntimeError("LocateAnything model loader not found")

            self._loaded = True
            logger.info("locate_anything_loaded", model_path=str(self._model_path))
        except Exception as exc:
            logger.error("locate_anything_load_failed", error=str(exc), model_path=str(self._model_path))
            self._model = None
            self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

    def detect(
        self,
        image,
        conf_threshold: float = 0.35,
    ) -> list[dict]:
        """Return detections in the same shape expected by the auto-label pipeline."""
        if not self._loaded or self._model is None:
            return []

        try:
            image_np = self._prepare_image(image)
        except Exception as exc:
            logger.error("locate_anything_prepare_image_failed", error=str(exc))
            return []

        try:
            with self._lock:
                if hasattr(self._model, "locate"):
                    raw = self._model.locate(image_np)
                elif hasattr(self._model, "predict"):
                    raw = self._model.predict(image_np)
                else:
                    raise RuntimeError("LocateAnything model has no locate/predict API")
        except Exception as exc:
            logger.error("locate_anything_detect_failed", error=str(exc))
            return []

        return self._parse_predictions(raw, image_np.shape[:2], conf_threshold)

    def _prepare_image(self, image):
        import cv2

        if isinstance(image, bytes):
            arr = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
            if arr is None:
                raise ValueError("unable to decode image bytes")
            return arr

        if hasattr(image, "shape"):
            return np.asarray(image)

        try:
            from PIL import Image

            if isinstance(image, Image.Image):
                return np.asarray(image.convert("RGB"))
        except ImportError:
            pass

        raise ValueError("unsupported image type for LocateAnything")

    def _parse_predictions(
        self,
        raw,
        image_shape: tuple[int, int],
        conf_threshold: float,
    ) -> list[dict]:
        if raw is None:
            return []

        items = []
        if isinstance(raw, dict):
            if "predictions" in raw:
                items = list(raw["predictions"] or [])
            elif "detections" in raw:
                items = list(raw["detections"] or [])
            else:
                items = [raw]
        elif isinstance(raw, list):
            items = raw
        else:
            try:
                items = list(raw)
            except Exception:
                items = [raw]

        results: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            score = float(item.get("confidence") or item.get("score") or item.get("confidence_score", 0.0))
            if score < conf_threshold:
                continue

            class_name = (
                item.get("class_name")
                or item.get("label")
                or item.get("category_name")
                or item.get("category")
                or "object"
            )
            bbox = self._normalize_bbox(item.get("bbox") or item.get("box"), image_shape)
            if bbox is None:
                continue

            mask = self._normalize_mask(item.get("mask"), image_shape)
            result = {
                "class_name": class_name,
                "taxonomy": class_name,
                "confidence": round(score, 4),
                "bbox": bbox,
            }
            if mask is not None:
                result["mask"] = mask
            results.append(result)

        return results

    def _normalize_bbox(
        self,
        raw_bbox,
        image_shape: tuple[int, int],
    ) -> list[float] | None:
        if raw_bbox is None:
            return None
        arr = np.asarray(raw_bbox, dtype=np.float32).flatten()
        if arr.size != 4:
            return None

        h, w = image_shape
        x0, y0, x2, y2 = arr

        if np.all((arr >= 0.0) & (arr <= 1.0)):
            # Assume normalized [x, y, w, h] by default when all values are in [0,1]. This
            # is the common format for LocateAnything-style object outputs.
            return [float(x0), float(y0), float(x2), float(y2)]

        if x2 >= x0 and y2 >= y0:
            # Absolute [x1, y1, x2, y2]
            return [float(x0 / w), float(y0 / h), float((x2 - x0) / w), float((y2 - y0) / h)]

        return None

    def _normalize_mask(self, raw_mask, image_shape: tuple[int, int]):
        if raw_mask is None:
            return None
        arr = np.asarray(raw_mask)
        if arr.ndim == 3 and arr.shape[0] == 1:
            arr = arr[0]
        if arr.ndim != 2:
            return None
        mask = arr > 0.5 if arr.dtype != bool else arr
        if mask.shape != image_shape:
            return None
        return mask.astype(bool)


_segmenter: LocateAnythingSegmenter | None = None
_segmenter_lock = threading.Lock()


def get_locate_anything_segmenter() -> LocateAnythingSegmenter:
    global _segmenter
    if _segmenter is None:
        with _segmenter_lock:
            if _segmenter is None:
                _segmenter = LocateAnythingSegmenter()
    return _segmenter
