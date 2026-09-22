"""Supplemental scene-object detection for live annotate.

COCO YOLO does not include classes like bike helmet or picture frame.
This module adds lightweight heuristics on top of seg detections and
edge/contour analysis for common indoor/outdoor studio objects.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.scene_objects")

# Small accessory classes that often appear near a person's head.
_HEADWEAR_PROXIES = frozenset(
    {
        "sports ball",
        "frisbee",
        "umbrella",
        "handbag",
        "backpack",
        "tie",
    }
)


def _box_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _xywh_to_xyxy(box: list[float], w: int, h: int) -> tuple[float, float, float, float]:
    if len(box) != 4:
        return (0.0, 0.0, 0.0, 0.0)
    x, y, third, fourth = box
    if third <= 1.0 and fourth <= 1.0:
        x1 = x * w
        y1 = y * h
        x2 = (x + third) * w
        y2 = (y + fourth) * h
    elif third > x and fourth > y:
        x1, y1, x2, y2 = x, y, third, fourth
    else:
        x1, y1 = x, y
        x2, y2 = x + third, y + fourth
    return (x1, y1, x2, y2)


def detect_headwear(
    tracked: list[dict],
    seg_instances: list[dict],
    img_w: int,
    img_h: int,
) -> list[dict]:
    """Infer bike helmets from person boxes + nearby accessory detections."""
    persons = [t for t in tracked if t.get("class_name") == "person"]
    if not persons:
        return []

    extras: list[dict] = []
    used_tracks: set[int] = set()

    for person in persons:
        px1, py1, px2, py2 = person["bbox"]
        head_y2 = py1 + (py2 - py1) * 0.32
        head_zone = (px1, py1, px2, head_y2)
        person_area = max(1.0, (px2 - px1) * (py2 - py1))

        best: dict | None = None
        best_score = 0.12

        for inst in seg_instances:
            cls = inst.get("class_name", "")
            if cls == "person":
                continue
            ibox = _xywh_to_xyxy(inst["bbox"], img_w, img_h)
            iou = _box_iou(head_zone, ibox)
            inst_area = max(1.0, (ibox[2] - ibox[0]) * (ibox[3] - ibox[1]))
            area_ratio = inst_area / person_area
            # Headwear is small relative to the person and overlaps the head zone.
            if area_ratio > 0.35:
                continue
            score = iou
            if cls in _HEADWEAR_PROXIES:
                score += 0.15
            if score > best_score:
                best_score = score
                best = inst

        if best is None:
            continue

        track_id = person.get("track_id")
        if track_id in used_tracks:
            continue
        used_tracks.add(track_id)

        ibox = _xywh_to_xyxy(best["bbox"], img_w, img_h)
        extras.append(
            {
                "class_name": "helmet",
                "taxonomy_label": "helmet",
                "confidence": round(min(0.92, float(best.get("confidence", 0.5)) + 0.15), 4),
                "bbox": [ibox[0], ibox[1], ibox[2] - ibox[0], ibox[3] - ibox[1]],
                "track_id": f"helmet_{track_id}",
                "mask_format": best.get("mask_format"),
                "mask": best.get("mask"),
                "source": "headwear_heuristic",
            }
        )

    return extras


def detect_picture_frames(image: np.ndarray, max_frames: int = 4) -> list[dict]:
    """Find rectangular wall-mounted frames via contour analysis."""
    h, w = image.shape[:2]
    if h < 80 or w < 80:
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = (w * h) * 0.004
    max_area = (w * h) * 0.35
    candidates: list[tuple[float, list[float]]] = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) < 4 or len(approx) > 8:
            continue
        x, y, bw, bh = cv2.boundingRect(approx)
        if bw < 24 or bh < 24:
            continue
        aspect = bw / bh if bh else 0
        if aspect < 0.45 or aspect > 2.2:
            continue
        # Prefer upper/mid field of view (typical wall placement)
        cy = y + bh / 2
        if cy > h * 0.92:
            continue
        score = min(1.0, area / max_area) * (1.0 - abs(1.0 - aspect) * 0.3)
        candidates.append((score, [float(x), float(y), float(bw), float(bh)]))

    candidates.sort(key=lambda c: c[0], reverse=True)
    results: list[dict] = []
    for score, box in candidates[:max_frames]:
        results.append(
            {
                "class_name": "picture frame",
                "taxonomy_label": "picture_frame",
                "confidence": round(0.35 + score * 0.45, 4),
                "bbox": box,
                "track_id": f"frame_{len(results)}",
                "mask_format": None,
                "source": "contour_heuristic",
            }
        )
    return results


def enrich_live_detections(
    tracked: list[dict],
    seg_instances: list[dict],
    image: np.ndarray,
) -> list[dict]:
    """Merge supplemental helmet / picture-frame detections into tracked list."""
    h, w = image.shape[:2]
    merged = list(tracked)

    headwear = detect_headwear(tracked, seg_instances, w, h)
    frames = detect_picture_frames(image)

    existing_boxes = [_xywh_to_xyxy(t["bbox"], w, h) if len(t.get("bbox", [])) == 4 else (0, 0, 0, 0) for t in merged]

    for extra in headwear + frames:
        ebox = _xywh_to_xyxy(extra["bbox"], w, h)
        if any(_box_iou(ebox, eb) > 0.45 for eb in existing_boxes):
            continue
        merged.append(extra)
        existing_boxes.append(ebox)

    if headwear or frames:
        logger.debug(
            "scene_objects_enriched",
            headwear=len(headwear),
            picture_frames=len(frames),
        )
    return merged
