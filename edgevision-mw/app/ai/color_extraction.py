from __future__ import annotations

import cv2
import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.color_extraction")

COLOR_RANGES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "red": ((0, 50, 50), (10, 255, 255)),
    "red_alt": ((170, 50, 50), (180, 255, 255)),
    "orange": ((11, 50, 50), (25, 255, 255)),
    "yellow": ((26, 50, 50), (35, 255, 255)),
    "green": ((36, 50, 50), (85, 255, 255)),
    "cyan": ((86, 50, 50), (100, 255, 255)),
    "blue": ((101, 50, 50), (130, 255, 255)),
    "purple": ((131, 50, 50), (160, 255, 255)),
    "pink": ((161, 50, 50), (169, 255, 255)),
    "white": ((0, 0, 200), (180, 30, 255)),
    "gray": ((0, 0, 50), (180, 30, 200)),
    "black": ((0, 0, 0), (180, 255, 50)),
    "brown": ((0, 50, 20), (20, 255, 150)),
}


def extract_dominant_colors(image: np.ndarray, top_k: int = 5) -> list[dict[str, float | list[int]]]:
    pixels = image.reshape(-1, 3)
    _, labels, centers = cv2.kmeans(
        pixels.astype(np.float32),
        top_k,
        None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0),
        10,
        cv2.KMEANS_RANDOM_CENTERS,
    )
    counts = np.bincount(labels.ravel())
    total = counts.sum()
    colors = []
    for i in range(top_k):
        bgr = centers[i].astype(int).tolist()
        percentage = float(counts[i] / total)
        colors.append({"bgr": bgr, "percentage": round(percentage, 4)})
    colors.sort(key=lambda c: c["percentage"], reverse=True)
    return colors


def classify_colors(image: np.ndarray) -> dict[str, float]:
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    total_pixels = image.shape[0] * image.shape[1]
    result: dict[str, float] = {}

    for name, (lower, upper) in COLOR_RANGES.items():
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        count = int(cv2.countNonZero(mask))
        result[name] = round(count / total_pixels, 4)

    if "red" in result and "red_alt" in result:
        result["red"] = round(result["red"] + result.pop("red_alt"), 4)

    return result


def color_histogram(image: np.ndarray, bins: int = 32) -> dict[str, list[float]]:
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    h_hist = cv2.calcHist([h], [0], None, [bins], [0, 180]).flatten()
    s_hist = cv2.calcHist([s], [0], None, [bins], [0, 256]).flatten()
    v_hist = cv2.calcHist([v], [0], None, [bins], [0, 256]).flatten()

    return {
        "hue": (h_hist / h_hist.sum()).tolist(),
        "saturation": (s_hist / s_hist.sum()).tolist(),
        "value": (v_hist / v_hist.sum()).tolist(),
    }


def extract_color_features(image: np.ndarray) -> dict:
    result: dict = {}
    result["dominant_colors"] = extract_dominant_colors(image)
    result["color_classes"] = classify_colors(image)
    result["histogram"] = color_histogram(image)
    result["mean_hsv"] = cv2.mean(cv2.cvtColor(image, cv2.COLOR_RGB2HSV))[:3]
    return result
