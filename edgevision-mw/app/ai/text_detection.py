from __future__ import annotations

import cv2
import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.text_detection")


def flip_coords(bbox: list[int | float], width: int, height: int | None = None) -> list[int | float]:
    """Flip bbox [x1, y1, x2, y2] horizontally. Used when orientation == 'mirrored'."""
    x1, y1, x2, y2 = bbox
    return [width - x2, y1, width - x1, y2]

try:
    import pytesseract

    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False


def detect_and_ocr(image: np.ndarray) -> list[dict]:
    if not _HAS_TESSERACT:
        logger.warning("pytesseract not installed; OCR unavailable")
        return _detect_text_regions_opencv(image)

    try:
        results = _ocr_tesseract(image)
        if results:
            return results
    except Exception as exc:
        logger.warning("tesseract_ocr_failed", error=str(exc))

    return _detect_text_regions_opencv(image)


def _detect_text_regions_opencv(image: np.ndarray) -> list[dict]:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    morph_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
    dilated = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, morph_kernel, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    results = []
    h, w = image.shape[:2]
    min_area = w * h * 0.001
    max_area = w * h * 0.5

    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        area = bw * bh
        aspect = bw / max(bh, 1)
        if area < min_area or area > max_area:
            continue
        if aspect < 1.5 and area < (w * h * 0.02):
            continue

        results.append({
            "bbox": [int(x), int(y), int(x + bw), int(y + bh)],
            "confidence": 0.0,
            "text": "",
            "method": "opencv_contour",
        })

    return results


def _ocr_tesseract(image: np.ndarray) -> list[dict]:
    config = "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-./ "
    data = pytesseract.image_to_data(image, config=config, output_type=pytesseract.Output.DICT)

    results = []
    n = len(data["text"])
    for i in range(n):
        text = data["text"][i].strip()
        conf = int(data["conf"][i]) / 100.0 if data["conf"][i] != "-1" else 0.0
        if not text or conf < 0.3:
            continue
        x, y, bw, bh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        if bw < 5 or bh < 5:
            continue
        results.append({
            "bbox": [int(x), int(y), int(x + bw), int(y + bh)],
            "confidence": round(conf, 4),
            "text": text,
            "method": "tesseract",
        })

    return results


def detect_signs(image: np.ndarray) -> list[dict]:
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

    SIGN_COLOR_RANGES: list[tuple[str, tuple, tuple]] = [
        ("red_sign", (0, 50, 50), (10, 255, 255)),
        ("red_sign_alt", (170, 50, 50), (180, 255, 255)),
        ("blue_sign", (100, 50, 50), (130, 255, 255)),
        ("green_sign", (40, 50, 50), (80, 255, 255)),
        ("yellow_sign", (20, 50, 50), (35, 255, 255)),
        ("white_sign", (0, 0, 180), (180, 30, 255)),
    ]

    h, w = image.shape[:2]
    min_area = w * h * 0.005
    signs = []

    for name, lower, upper in SIGN_COLOR_RANGES:
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        mask = cv2.erode(mask, None, iterations=1)
        mask = cv2.dilate(mask, None, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            area = bw * bh
            if area < min_area:
                continue
            aspect = bw / max(bh, 1)
            if aspect < 0.3 or aspect > 4.0:
                continue

            sign_roi = image[y : y + bh, x : x + bw]
            ocr_results = _ocr_tesseract(sign_roi) if _HAS_TESSERACT else []

            signs.append({
                "bbox": [int(x), int(y), int(x + bw), int(y + bh)],
                "color_class": name,
                "confidence": round(min(area / (w * h) * 10, 1.0), 4),
                "ocr_text": ocr_results[0]["text"] if ocr_results else "",
                "ocr_confidence": ocr_results[0]["confidence"] if ocr_results else 0.0,
            })

    return signs
