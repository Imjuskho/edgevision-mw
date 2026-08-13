"""YOLOv8-seg instance segmentation via ONNX Runtime.

Runs the bundled ``yolov8n-seg-fp32.onnx`` to produce real object
detections with binary instance masks. Used as the mask backend for
auto-labeling when a SAM decoder is unavailable (the bundled MobileSAM
decoder export is not CPU-runnable), while remaining a clean drop-in
alternative when a valid model is deployed via ``YOLOV8_SEG_MODEL_PATH``.
"""
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.yolo_seg")

_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

# COCO class → EdgeVision taxonomy label
SEG_TO_TAXONOMY: dict[str, str] = {
    "car": "car_private",
    "bus": "bus",
    "truck": "truck",
    "motorcycle": "motorcycle_kabaza",
    "bicycle": "bicycle_private",
    "person": "pedestrian_roadside",
    "sheep": "goat_sheep",
    "cow": "cattle",
    "dog": "dog",
    "cat": "cat",
    "potted plant": "plant",
    "tv": "screen",
    "laptop": "screen",
    "cell phone": "device",
    "helmet": "helmet",
    "picture frame": "picture_frame",
    "clock": "wall_clock",
    "book": "book",
    "vase": "vase",
    "bottle": "bottle",
    "cup": "cup",
    "chair": "chair",
    "couch": "couch",
    "bed": "bed",
    "dining table": "table",
    "toilet": "fixture",
    "sink": "fixture",
    "refrigerator": "appliance",
    "microwave": "appliance",
    "oven": "appliance",
    "toaster": "appliance",
    "keyboard": "device",
    "mouse": "device",
    "remote": "device",
    "scissors": "tool",
    "teddy bear": "toy",
    "sports ball": "sports_equipment",
    "backpack": "bag",
    "handbag": "bag",
    "suitcase": "bag",
    "umbrella": "umbrella",
    "tie": "accessory",
    "wine glass": "glassware",
    "bowl": "bowl",
    "fork": "utensil",
    "knife": "utensil",
    "spoon": "utensil",
    "banana": "produce",
    "apple": "produce",
    "orange": "produce",
    "broccoli": "produce",
    "carrot": "produce",
    "bird": "bird",
    "horse": "animal",
    "elephant": "animal",
    "bear": "animal",
    "zebra": "animal",
    "giraffe": "animal",
    "traffic light": "traffic_light",
    "fire hydrant": "street_furniture",
    "stop sign": "sign",
    "parking meter": "street_furniture",
    "bench": "street_furniture",
}


def _find_model() -> Path | None:
    """Locate the YOLOv8-seg ONNX model.

    Resolution order:
      1. ``YOLOV8_SEG_MODEL_PATH`` environment variable
      2. Project-local ``frontend/public/models/yolov8n-seg-fp32.onnx``
    """
    from app.core.config import settings

    candidates = []
    if settings.YOLOV8_SEG_MODEL_PATH:
        candidates.append(Path(settings.YOLOV8_SEG_MODEL_PATH))
    candidates.append(
        Path(__file__).resolve().parents[2]
        / "frontend/public/models/yolov8n-seg-fp32.onnx"
    )
    for p in candidates:
        if p.exists():
            return p
    return None


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class YoloSegSegmenter:
    """YOLOv8-seg ONNX instance segmentation with real binary masks."""

    def __init__(self, model_path: str | None = None):
        self._model_path = model_path or _find_model()
        self._session = None
        self._input_name: str | None = None
        self._output_names: list[str] = []
        self._input_size = 640
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if self._model_path is None:
            logger.warning("yolo_seg_model_missing", model_path=self._model_path)
            return
        try:
            import onnxruntime as ort

            providers = [
                p for p in ("CPUExecutionProvider",) if p in ort.get_available_providers()
            ]
            self._session = ort.InferenceSession(str(self._model_path), providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            self._output_names = [o.name for o in self._session.get_outputs()]
            logger.info("yolo_seg_loaded", model_path=str(self._model_path))
        except Exception as exc:
            logger.error("yolo_seg_load_failed", error=str(exc))
            self._session = None

    def is_loaded(self) -> bool:
        return self._session is not None

    def detect(
        self,
        image_bytes: bytes,
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
    ) -> list[dict]:
        """Return detections ``{class_name, taxonomy, confidence, bbox, mask}``.

        ``bbox`` is normalized ``[x, y, w, h]``; ``mask`` is a 2D bool ndarray
        in full-image pixel space.
        """
        if self._session is None:
            return []
        try:
            import cv2

            arr = cv2.imdecode(
                np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
            )
            if arr is None:
                return []
            orig_h, orig_w = arr.shape[:2]
            with self._lock:
                blob, pad_x, pad_y, scale = self._preprocess(arr)
                outputs = self._session.run(self._output_names, {self._input_name: blob})
            return self._postprocess(
                outputs, (orig_h, orig_w), (pad_x, pad_y, scale),
                conf_threshold, iou_threshold,
            )
        except Exception as exc:
            logger.error("yolo_seg_detect_failed", error=str(exc))
            return []

    def _preprocess(self, img: np.ndarray) -> tuple[np.ndarray, int, int, float]:
        import cv2

        h, w = img.shape[:2]
        scale = min(self._input_size / w, self._input_size / h)
        nw, nh = round(w * scale), round(h * scale)
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((self._input_size, self._input_size, 3), 114, dtype=np.uint8)
        pad_x = (self._input_size - nw) // 2
        pad_y = (self._input_size - nh) // 2
        canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = resized
        blob = np.transpose(canvas.astype(np.float32) / 255.0, (2, 0, 1))[np.newaxis]
        return blob, pad_x, pad_y, scale

    def _postprocess(
        self,
        outputs: list[np.ndarray],
        orig_shape: tuple[int, int],
        pad: tuple[int, int, float],
        conf_threshold: float,
        iou_threshold: float,
    ) -> list[dict]:
        import cv2

        orig_h, orig_w = orig_shape
        pad_x, pad_y, scale = pad
        predictions = outputs[0][0].transpose()  # [8400, 116]
        protos = outputs[1][0]  # [32, 160, 160]

        boxes: list[list[float]] = []
        confidences: list[float] = []
        class_ids: list[int] = []
        coefficients: list[np.ndarray] = []

        for pred in predictions:
            scores = pred[4:84]
            max_score = float(scores.max())
            if max_score < conf_threshold:
                continue
            class_id = int(scores.argmax())
            cx, cy, w, h = pred[0], pred[1], pred[2], pred[3]
            boxes.append([cx - w / 2, cy - h / 2, w, h])
            confidences.append(max_score)
            class_ids.append(class_id)
            coefficients.append(pred[84:116])

        if not boxes:
            return []

        keep = self._nms(boxes, confidences, iou_threshold)
        results: list[dict] = []
        for i in keep:
            x1, y1, w, h = boxes[i]
            # denormalize to original pixel space
            x1_orig = (x1 - pad_x) / scale
            y1_orig = (y1 - pad_y) / scale
            w_orig = w / scale
            h_orig = h / scale
            x1_orig = max(0, x1_orig)
            y1_orig = max(0, y1_orig)
            w_orig = min(w_orig, orig_w - x1_orig)
            h_orig = min(h_orig, orig_h - y1_orig)

            mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
            try:
                proto = protos
                coeffs = coefficients[i]
                masks_pred = np.tensordot(proto, coeffs, axes=([0], [0]))
                masks_pred = 1.0 / (1.0 + np.exp(-masks_pred))
                mask_160 = masks_pred.reshape((160, 160))
                mask_full = cv2.resize(mask_160, (self._input_size, self._input_size))
                # strip letterbox padding
                mask_crop = mask_full[
                    pad_y:pad_y + round(orig_h * scale),
                    pad_x:pad_x + round(orig_w * scale),
                ]
                mask_crop = cv2.resize(mask_crop, (orig_w, orig_h))
                mask_bin = (mask_crop > 0.5).astype(np.uint8)
                bx1, by1 = int(x1_orig), int(y1_orig)
                bx2, by2 = int(x1_orig + w_orig), int(y1_orig + h_orig)
                mask_bin[:by1, :] = 0
                mask_bin[by2:, :] = 0
                mask_bin[:, :bx1] = 0
                mask_bin[:, bx2:] = 0
                mask = mask_bin
            except Exception:
                pass

            class_name = _NAMES[class_ids[i]] if class_ids[i] < len(_NAMES) else f"class_{class_ids[i]}"
            results.append({
                "class_name": class_name,
                "taxonomy": SEG_TO_TAXONOMY.get(class_name, class_name),
                "confidence": round(confidences[i], 4),
                "bbox": [
                    round(x1_orig / orig_w, 4),
                    round(y1_orig / orig_h, 4),
                    round(w_orig / orig_w, 4),
                    round(h_orig / orig_h, 4),
                ],
                "mask": (mask > 0),
            })
        return results

    def _nms(self, boxes: list[list[float]], scores: list[float], iou_threshold: float) -> list[int]:
        if not boxes:
            return []
        boxes_arr = np.array(boxes)
        scores_arr = np.array(scores)
        x1 = boxes_arr[:, 0]
        y1 = boxes_arr[:, 1]
        x2 = boxes_arr[:, 0] + boxes_arr[:, 2]
        y2 = boxes_arr[:, 1] + boxes_arr[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores_arr.argsort()[::-1]

        keep: list[int] = []
        while order.size > 0:
            i = int(order[0])
            keep.append(i)
            if order.size == 1:
                break
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter)
            order = order[1:][iou <= iou_threshold]
        return keep


_segmenter: YoloSegSegmenter | None = None
_segmenter_lock = threading.Lock()


def get_yolo_seg_segmenter() -> YoloSegSegmenter:
    """Return the process-wide lazy YOLOv8-seg segmenter singleton."""
    global _segmenter
    if _segmenter is None:
        with _segmenter_lock:
            if _segmenter is None:
                _segmenter = YoloSegSegmenter()
    return _segmenter


def mask_to_polygon(mask: np.ndarray, max_points: int = 32) -> list[list[float]]:
    """Convert a binary mask to a normalized polygon (0..1 coords), capped at max_points."""
    try:
        import cv2

        mask_u8 = (mask > 0).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        largest = max(contours, key=cv2.contourArea)
        epsilon = 0.01 * cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, epsilon, True)
        h, w = mask.shape[:2]
        points = [[round(float(p[0][0]) / w, 4), round(float(p[0][1]) / h, 4)] for p in approx]
        if len(points) > max_points:
            step = max(1, len(points) // max_points)
            points = points[::step][:max_points]
        return points
    except Exception:
        return []


def attach_masks_from_instances(
    detections: list[dict],
    instances: list[dict],
    img_w: int,
    img_h: int,
    max_points: int = 32,
    min_iou: float = 0.1,
) -> list[dict]:
    """Attach mask polygons from existing seg instances (no extra forward pass)."""
    if not detections or not instances:
        return detections

    enriched = []
    for det in detections:
        d = dict(det)
        dbox = det.get("bbox", [0, 0, 0, 0])
        if len(dbox) == 4 and dbox[2] <= 1.0 and dbox[3] <= 1.0:
            px_box = np.array([
                dbox[0] * img_w, dbox[1] * img_h,
                (dbox[0] + dbox[2]) * img_w, (dbox[1] + dbox[3]) * img_h,
            ])
        else:
            px_box = np.array([dbox[0], dbox[1], dbox[2], dbox[3]], dtype=np.float64)

        best = None
        best_iou = 0.0
        for inst in instances:
            ib = inst["bbox"]
            if ib[2] <= 1.0:
                ibox = np.array([
                    ib[0] * img_w, ib[1] * img_h,
                    (ib[0] + ib[2]) * img_w, (ib[1] + ib[3]) * img_h,
                ])
            else:
                ibox = np.array([ib[0], ib[1], ib[0] + ib[2], ib[1] + ib[3]])
            val = _iou(px_box, ibox)
            if val > best_iou:
                best_iou = val
                best = inst

        if best is not None and best_iou >= min_iou and best.get("mask") is not None:
            polygon = mask_to_polygon(best["mask"], max_points=max_points)
            if polygon:
                d["mask"] = polygon
                d["mask_format"] = "polygon"
        enriched.append(d)
    return enriched


def attach_mask_polygons(
    detections: list[dict],
    image_bytes: bytes,
    conf_threshold: float = 0.35,
    max_points: int = 32,
) -> list[dict]:
    """Run YOLOv8-seg and attach downsampled mask polygons to detections by IoU."""
    segmenter = get_yolo_seg_segmenter()
    if not segmenter.is_loaded():
        return detections

    instances = segmenter.detect(image_bytes, conf_threshold=conf_threshold)
    if not instances:
        return detections

    enriched = []
    import cv2

    arr = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    oh, ow = (arr.shape[:2] if arr is not None else (1, 1))

    for det in detections:
        d = dict(det)
        dbox = det.get("bbox", [0, 0, 0, 0])
        if len(dbox) == 4 and dbox[2] <= 1.0:
            px_box = np.array([
                dbox[0] * ow, dbox[1] * oh,
                (dbox[0] + dbox[2]) * ow, (dbox[1] + dbox[3]) * oh,
            ])
        else:
            px_box = np.array([dbox[0], dbox[1], dbox[2], dbox[3]])

        best = None
        best_iou = 0.0
        for inst in instances:
            ib = inst["bbox"]
            if ib[2] <= 1.0:
                ibox = np.array([ib[0] * ow, ib[1] * oh, (ib[0] + ib[2]) * ow, (ib[1] + ib[3]) * oh])
            else:
                ibox = np.array([ib[0], ib[1], ib[0] + ib[2], ib[1] + ib[3]])
            val = _iou(px_box, ibox)
            if val > best_iou:
                best_iou = val
                best = inst

        if best is not None and best.get("mask") is not None:
            polygon = mask_to_polygon(best["mask"], max_points=max_points)
            if polygon:
                d["mask"] = polygon
                d["mask_format"] = "polygon"
        enriched.append(d)
    return enriched


def assign_masks(detections: list[dict], instances: list[dict]) -> list[dict]:
    """Attach instance masks to prelabel detections by best bbox overlap."""
    if not detections or not instances:
        return detections
    for idx, det in enumerate(detections):
        dbox = det["bbox"]
        best = None
        best_iou = 0.0
        for inst in instances:
            if inst["mask"].sum() == 0:
                continue
            ibox = inst["bbox"]
            iou = _iou(
                np.array([dbox[0], dbox[1], dbox[0] + dbox[2], dbox[1] + dbox[3]]),
                np.array([ibox[0], ibox[1], ibox[0] + ibox[2], ibox[1] + ibox[3]]),
            )
            if iou > best_iou:
                best_iou = iou
                best = inst
        if best is not None:
            det = dict(det)
            det["mask"] = best["mask"]
            det["mask_iou"] = round(best_iou, 4)
            detections[idx] = det
    return detections
