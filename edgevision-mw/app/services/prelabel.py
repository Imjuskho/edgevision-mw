"""Server-side pre-labeling service using ONNX Runtime.

Runs YOLOv8-cls on image patches via a sliding window grid to produce
bounding-box pseudo-detections. These serve as warm-start pre-labels
for human annotators.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Class names matching the browser-side YOLO classifier
CLASS_NAMES = [
    "car", "matola", "pedestrian", "bicycle", "motorcycle",
    "goat", "cow", "dog", "bus", "minibus",
]

# Mapping from YOLO class names to our taxonomy labels
YOLO_TO_TAXONOMY: dict[str, str] = {
    "car": "car_private",
    "matola": "minibus",
    "pedestrian": "pedestrian_roadside",
    "bicycle": "bicycle_private",
    "motorcycle": "motorcycle_kabaza",
    "goat": "goat_sheep",
    "cow": "cattle",
    "dog": "dog",
    "bus": "bus",
    "minibus": "minibus",
}

# ImageNet normalization
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _find_model() -> Path | None:
    """Locate the YOLO classification ONNX model.

    Resolution order:
      1. ``PRELABEL_YOLO_CLS_PATH`` environment variable
      2. Project-local ``frontend/public/models/yolov8n_cls_int8.onnx``
    """
    from app.core.config import settings

    candidates = []
    if settings.PRELABEL_YOLO_CLS_PATH:
        candidates.append(Path(settings.PRELABEL_YOLO_CLS_PATH))
    candidates.append(
        Path(__file__).resolve().parents[2]
        / "frontend/public/models/yolov8n_cls_int8.onnx"
    )
    for p in candidates:
        if p.exists():
            return p
    return None


def _preprocess_crop(img: Image.Image, size: int = 224) -> np.ndarray:
    """Resize + normalize a crop to NCHW float32 tensor."""
    resized = img.resize((size, size), Image.BILINEAR)
    arr = np.array(resized, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    arr = arr.transpose(2, 0, 1)  # HWC → CHW
    return arr[np.newaxis, ...]  # add batch dim


def _iou(a: list[float], b: list[float]) -> float:
    """Compute IoU between two [x1, y1, x2, y2] boxes."""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _nms(boxes: list[list[float]], scores: list[float], iou_thresh: float = 0.3) -> list[int]:
    """Non-maximum suppression. Returns indices of kept boxes."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    keep: list[int] = []
    while order:
        i = order.pop(0)
        keep.append(i)
        order = [
            j for j in order
            if _iou(boxes[i], boxes[j]) <= iou_thresh
        ]
    return keep


def prelabel_image(
    image_bytes: bytes,
    confidence_threshold: float = 0.45,
    grid_step: int = 128,
    patch_size: int = 224,
) -> list[dict[str, Any]]:
    """Run pre-labeling on an image, preferring YOLOv8-seg masks when available."""
    from app.ai.yolo_seg import get_yolo_seg_segmenter

    segmenter = get_yolo_seg_segmenter()
    if segmenter.is_loaded():
        instances = segmenter.detect(image_bytes, conf_threshold=confidence_threshold)
        if instances:
            results = []
            for inst in instances:
                x, y, w, h = inst["bbox"]
                label = inst.get("taxonomy") or inst["class_name"]
                entry: dict[str, Any] = {
                    "label": label,
                    "class_name": inst["class_name"],
                    "confidence": inst["confidence"],
                    "bbox": [x, y, w, h],
                }
                if inst.get("mask") is not None:
                    from app.ai.yolo_seg import mask_to_polygon

                    polygon = mask_to_polygon(inst["mask"])
                    if polygon:
                        entry["mask"] = polygon
                        entry["mask_format"] = "polygon"
                results.append(entry)
            return results

    return _prelabel_sliding_window(
        image_bytes,
        confidence_threshold=confidence_threshold,
        grid_step=grid_step,
        patch_size=patch_size,
    )


def _prelabel_sliding_window(
    image_bytes: bytes,
    confidence_threshold: float = 0.45,
    grid_step: int = 128,
    patch_size: int = 224,
) -> list[dict[str, Any]]:
    """Run sliding-window YOLO classification on an image.

    Returns a list of detection dicts:
        {label, class_name, confidence, bbox: [x, y, w, h]}
    where bbox is normalized [0..1].
    """
    import onnxruntime as ort

    model_path = _find_model()
    if model_path is None:
        logger.warning("YOLO classification model not found; returning empty pre-labels")
        return []

    try:
        img = Image.open(__import__("io").BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        logger.error("Failed to decode image for pre-labeling: %s", exc)
        return []

    img_w, img_h = img.size

    try:
        session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        input_name = session.get_inputs()[0].name
    except Exception as exc:
        logger.error("Failed to load ONNX model: %s", exc)
        return []

    raw_boxes: list[list[float]] = []
    raw_scores: list[float] = []
    raw_labels: list[str] = []

    # Sliding window grid
    for gy in range(0, img_h, grid_step):
        for gx in range(0, img_w, grid_step):
            cx = gx + grid_step // 2
            cy = gy + grid_step // 2

            # Extract crop centered on grid point
            half = patch_size // 2
            x1 = max(0, min(cx - half, img_w - patch_size))
            y1 = max(0, min(cy - half, img_h - patch_size))
            crop = img.crop((x1, y1, x1 + patch_size, y1 + patch_size))

            tensor = _preprocess_crop(crop)
            outputs = session.run(None, {input_name: tensor})
            probs = outputs[0].flatten()

            class_idx = int(np.argmax(probs))
            confidence = float(probs[class_idx])

            if confidence < confidence_threshold:
                continue

            class_name = CLASS_NAMES[class_idx] if class_idx < len(CLASS_NAMES) else "car"
            taxonomy_label = YOLO_TO_TAXONOMY.get(class_name, "car_private")

            # Normalized bbox
            nx = cx / img_w
            ny = cy / img_h
            bw = patch_size / img_w
            bh = patch_size / img_h

            raw_boxes.append([max(0, nx - bw / 2), max(0, ny - bh / 2), nx + bw / 2, ny + bh / 2])
            raw_scores.append(confidence)
            raw_labels.append(taxonomy_label)

    # NMS
    if not raw_boxes:
        return []

    keep = _nms(raw_boxes, raw_scores)

    results = []
    for i in keep:
        x1, y1, x2, y2 = raw_boxes[i]
        results.append({
            "label": raw_labels[i],
            "class_name": CLASS_NAMES[CLASS_NAMES.index(raw_labels[i].split("_")[0])] if raw_labels[i].split("_")[0] in CLASS_NAMES else raw_labels[i],
            "confidence": round(raw_scores[i], 4),
            "bbox": [
                round(x1, 4),
                round(y1, 4),
                round(x2 - x1, 4),
                round(y2 - y1, 4),
            ],
        })

    return results


async def prelabel_batch(
    image_bytes_list: list[bytes],
    confidence_threshold: float = 0.45,
) -> list[list[dict[str, Any]]]:
    """Pre-label a batch of images. Returns list of detection lists."""
    return [
        prelabel_image(img_bytes, confidence_threshold=confidence_threshold)
        for img_bytes in image_bytes_list
    ]
