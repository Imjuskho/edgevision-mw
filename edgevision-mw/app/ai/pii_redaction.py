"""Unified face + license plate de-identification for stored and exported imagery."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.pii_redaction")


@dataclass
class RedactionResult:
    image_bytes: bytes
    faces_blurred: int = 0
    plates_blurred: int = 0

    @property
    def redacted(self) -> bool:
        return self.faces_blurred > 0 or self.plates_blurred > 0


def redact_image(
    image: np.ndarray,
    *,
    blur_faces: bool = True,
    blur_plates: bool = True,
) -> tuple[np.ndarray, int, int]:
    """Blur faces and license plates in-place on a copy of ``image``."""
    result = image.copy()
    faces_blurred = 0
    plates_blurred = 0

    if blur_faces:
        try:
            from app.ai.face_privacy import get_face_blurrer

            face_blurrer = get_face_blurrer()
            if face_blurrer.is_loaded():
                faces = face_blurrer.detect_faces(result)
                if faces:
                    result = face_blurrer.blur_faces(result)
                    faces_blurred = len(faces)
            else:
                logger.warning("face_blur_skipped", reason="detector_not_loaded")
        except Exception as exc:
            logger.warning("face_blur_failed", error=str(exc))

    if blur_plates:
        try:
            from app.ai.plate_privacy import get_plate_blurrer

            plate_blurrer = get_plate_blurrer()
            if plate_blurrer.is_loaded():
                plates = plate_blurrer.detect_plates(result)
                if plates:
                    result = plate_blurrer.blur_plates(result)
                    plates_blurred = len(plates)
            else:
                logger.warning("plate_blur_skipped", reason="detector_not_loaded")
        except Exception as exc:
            logger.warning("plate_blur_failed", error=str(exc))

    return result, faces_blurred, plates_blurred


def redact_image_bytes(
    image_bytes: bytes,
    *,
    blur_faces: bool = True,
    blur_plates: bool = True,
) -> RedactionResult:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return RedactionResult(image_bytes=image_bytes)

    redacted, faces_blurred, plates_blurred = redact_image(
        img,
        blur_faces=blur_faces,
        blur_plates=blur_plates,
    )
    if faces_blurred == 0 and plates_blurred == 0:
        return RedactionResult(image_bytes=image_bytes)

    _, buf = cv2.imencode(".jpg", redacted, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return RedactionResult(
        image_bytes=buf.tobytes(),
        faces_blurred=faces_blurred,
        plates_blurred=plates_blurred,
    )


@dataclass
class PiiScanResult:
    faces: int = 0
    plates: int = 0
    scan_status: str = "complete"

    @property
    def total(self) -> int:
        return self.faces + self.plates


def scan_image(
    image: np.ndarray,
    *,
    detect_faces: bool = True,
    detect_plates: bool = True,
) -> PiiScanResult:
    faces = 0
    plates = 0

    if detect_faces:
        try:
            from app.ai.face_privacy import get_face_blurrer

            face_blurrer = get_face_blurrer()
            if face_blurrer.is_loaded():
                faces = len(face_blurrer.detect_faces(image))
            else:
                logger.warning("face_model_not_loaded")
                faces = -1
        except Exception as e:
            logger.warning("PII face detection failed: %s", e)
            faces = -1

    if detect_plates:
        try:
            from app.ai.plate_privacy import get_plate_blurrer

            plate_blurrer = get_plate_blurrer()
            if plate_blurrer.is_loaded():
                plates = len(plate_blurrer.detect_plates(image))
            else:
                logger.warning("plate_model_not_loaded")
                plates = -1
        except Exception as e:
            logger.warning("PII plate detection failed: %s", e)
            plates = -1

    scan_status = "complete"
    if faces == -1 or plates == -1:
        scan_status = "partial"
    return PiiScanResult(faces=faces, plates=plates, scan_status=scan_status)


def scan_image_bytes(image_bytes: bytes) -> PiiScanResult:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return PiiScanResult()
    return scan_image(img)


def redact_export_image_bytes(image_bytes: bytes) -> RedactionResult:
    """Apply mandatory de-identification before any external dataset image release."""
    return redact_image_bytes(image_bytes, blur_faces=True, blur_plates=True)
