from __future__ import annotations

import io
import ssl
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.face_privacy")

MODEL_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
CACHE_DIR = Path("/tmp/edgevision-face-model")


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
    model_path = CACHE_DIR / "face_detection_yunet_2023mar.onnx"

    if not model_path.exists():
        logger.info("face_model_downloading", url=MODEL_URL)
        data = _urlopen(MODEL_URL)
        model_path.write_bytes(data.read())

    return str(model_path)


class FaceBlurrer:
    def __init__(self, conf_threshold: float = 0.45, kernel_size: int = 51):
        self._conf_threshold = conf_threshold
        self._kernel_size = kernel_size
        self._detector = None
        self._load_model()

    def _load_model(self) -> None:
        try:
            model_path = _ensure_model()
            self._detector = cv2.FaceDetectorYN.create(
                model=model_path,
                config="",
                input_size=(320, 320),
                score_threshold=self._conf_threshold,
                nms_threshold=0.3,
                top_k=5000,
            )
            logger.info("face_blurrer_loaded")
        except Exception as exc:
            logger.error("face_blurrer_load_failed", error=str(exc))
            self._detector = None

    def detect_faces(self, image: np.ndarray) -> list[tuple[int, int, int, int]]:
        if self._detector is None:
            return []

        h, w = image.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces_arr = self._detector.detect(image)
        if faces_arr is None:
            return []

        faces: list[tuple[int, int, int, int]] = []
        for i in range(faces_arr.shape[0]):
            x, y, fw, fh, *_ = faces_arr[i, :4].tolist()
            x1 = max(0, int(x))
            y1 = max(0, int(y))
            x2 = min(w, int(x + fw))
            y2 = min(h, int(y + fh))
            if x2 > x1 and y2 > y1:
                faces.append((x1, y1, x2, y2))

        return faces

    def blur_faces(self, image: np.ndarray) -> np.ndarray:
        faces = self.detect_faces(image)
        if not faces:
            return image

        result = image.copy()
        k = self._kernel_size
        if k % 2 == 0:
            k += 1

        for x1, y1, x2, y2 in faces:
            face_roi = result[y1:y2, x1:x2]
            blurred = cv2.GaussianBlur(face_roi, (k, k), 0)
            result[y1:y2, x1:x2] = blurred

        logger.debug("face_blurrer_applied", faces=len(faces))
        return result

    def process_image_bytes(self, image_bytes: bytes) -> bytes:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes
        blurred = self.blur_faces(img)
        _, buf = cv2.imencode(".jpg", blurred, [cv2.IMWRITE_JPEG_QUALITY, 95])
        return buf.tobytes()

    def is_loaded(self) -> bool:
        return self._detector is not None


_blurrer: FaceBlurrer | None = None


def get_face_blurrer() -> FaceBlurrer:
    global _blurrer
    if _blurrer is None:
        _blurrer = FaceBlurrer()
    return _blurrer


def process_image(image: np.ndarray) -> np.ndarray:
    return get_face_blurrer().blur_faces(image)


def process_image_bytes(image_bytes: bytes) -> bytes:
    return get_face_blurrer().process_image_bytes(image_bytes)
