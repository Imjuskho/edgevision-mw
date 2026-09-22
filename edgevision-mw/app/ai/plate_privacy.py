from __future__ import annotations

import io
import ssl
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.plate_privacy")

MODEL_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "license_plate_detection_yunet/license_plate_detection_lpd_yunet_2023mar.onnx"
)
CACHE_DIR = Path("/tmp/edgevision-plate-model")


def _urlopen(url: str) -> io.BytesIO:
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
        return io.BytesIO(urllib.request.urlopen(url, context=ctx).read())
    except ImportError:
        pass
    try:
        ctx = ssl.create_default_context()
        return io.BytesIO(urllib.request.urlopen(url, context=ctx).read())
    except Exception:
        ctx = ssl._create_unverified_context()
        return io.BytesIO(urllib.request.urlopen(url, context=ctx).read())


def _ensure_model() -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    model_path = CACHE_DIR / "license_plate_detection_lpd_yunet_2023mar.onnx"

    if not model_path.exists():
        logger.info("plate_model_downloading", url=MODEL_URL)
        data = _urlopen(MODEL_URL)
        model_path.write_bytes(data.read())

    return str(model_path)


def _quad_to_bbox(det: np.ndarray, width: int, height: int, padding_pct: float) -> tuple[int, int, int, int] | None:
    if det.shape[0] < 9:
        return None
    xs = det[0:8:2]
    ys = det[1:8:2]
    x1 = max(0, int(np.min(xs)))
    y1 = max(0, int(np.min(ys)))
    x2 = min(width, int(np.max(xs)))
    y2 = min(height, int(np.max(ys)))
    if x2 <= x1 or y2 <= y1:
        return None

    pad_x = int((x2 - x1) * padding_pct)
    pad_y = int((y2 - y1) * padding_pct)
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(width, x2 + pad_x)
    y2 = min(height, y2 + pad_y)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


class PlateBlurrer:
    def __init__(self, conf_threshold: float = 0.55, kernel_size: int = 51, padding_pct: float = 0.12):
        self._conf_threshold = conf_threshold
        self._kernel_size = kernel_size
        self._padding_pct = padding_pct
        self._detector = None
        self._load_model()

    def _load_model(self) -> None:
        try:
            from app.ai.lpd_yunet import LPD_YuNet

            model_path = _ensure_model()
            self._detector = LPD_YuNet(model_path=model_path, conf_threshold=self._conf_threshold)
            logger.info("plate_blurrer_loaded")
        except Exception as exc:
            logger.error("plate_blurrer_load_failed", error=str(exc))
            self._detector = None

    def detect_plates(self, image: np.ndarray) -> list[tuple[int, int, int, int]]:
        if self._detector is None:
            return []

        h, w = image.shape[:2]
        self._detector.set_input_size([w, h])
        try:
            results = self._detector.infer(image)
        except Exception as exc:
            logger.debug("plate_detect_failed", error=str(exc))
            return []

        plates: list[tuple[int, int, int, int]] = []
        for det in results:
            bbox = _quad_to_bbox(det, w, h, self._padding_pct)
            if bbox is not None:
                plates.append(bbox)
        return plates

    def blur_plates(self, image: np.ndarray) -> np.ndarray:
        plates = self.detect_plates(image)
        if not plates:
            return image

        result = image.copy()
        k = self._kernel_size
        if k % 2 == 0:
            k += 1

        for x1, y1, x2, y2 in plates:
            roi = result[y1:y2, x1:x2]
            blurred = cv2.GaussianBlur(roi, (k, k), 0)
            result[y1:y2, x1:x2] = blurred

        logger.debug("plate_blurrer_applied", plates=len(plates))
        return result

    def process_image_bytes(self, image_bytes: bytes) -> bytes:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes
        blurred = self.blur_plates(img)
        _, buf = cv2.imencode(".jpg", blurred, [cv2.IMWRITE_JPEG_QUALITY, 95])
        return buf.tobytes()

    def is_loaded(self) -> bool:
        return self._detector is not None


_blurrer: PlateBlurrer | None = None


def get_plate_blurrer() -> PlateBlurrer:
    global _blurrer
    if _blurrer is None:
        _blurrer = PlateBlurrer()
    return _blurrer


def process_image(image: np.ndarray) -> np.ndarray:
    return get_plate_blurrer().blur_plates(image)


def process_image_bytes(image_bytes: bytes) -> bytes:
    return get_plate_blurrer().process_image_bytes(image_bytes)
