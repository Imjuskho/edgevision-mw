from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
from onnxruntime import GraphOptimizationLevel, InferenceSession, SessionOptions

from app.core.logging import get_logger
from app.models.agri_taxonomy import CROP_TYPES, HEALTH_STATUS_TYPES

logger = get_logger("edgevision.agri_segmenter")


class InstanceMaskResult:
    def __init__(
        self,
        class_id: int,
        class_name: str,
        confidence: float,
        bbox: list[float],
        mask_rle: str,
        polygon: list[list[float]] | None = None,
    ):
        self.class_id = class_id
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox
        self.mask_rle = mask_rle
        self.polygon = polygon


class AgriSegmenter:
    """Agricultural instance segmentation supporting ONNX Runtime and YOLO.

    A single AgriSegmenter instance is scoped to one taxonomy (either crop
    type OR health condition) — the two are trained and deployed as separate
    models (see get_agri_crop_segmenter / get_agri_health_segmenter below),
    each resolved independently through the model registry
    (ModelType.agri_crop_classification / ModelType.agri_health_classification).
    This avoids needing an artificial class-id offset scheme to disambiguate
    "crop" vs "health" detections coming out of a single combined model.
    """

    def __init__(self, model_path: str | None = None, device: str = "cpu", class_names: list[str] | None = None):
        self._model_path = model_path
        self._device = device
        self._class_names = class_names or []
        self._session: InferenceSession | None = None
        self._input_name: str | None = None
        self._output_names: list[str] | None = None
        self._input_width = 640
        self._input_height = 640
        self._yolo_model = None

        if model_path and Path(model_path).exists():
            ext = Path(model_path).suffix.lower()
            if ext == ".onnx":
                self._load_model_onnx(model_path)
            elif ext == ".pt":
                self._load_model_yolo(model_path)
            else:
                logger.warning("agri_segmenter_unknown_format", model_path=model_path, ext=ext)
        else:
            logger.warning("agri_segmenter_no_model", model_path=model_path)

    def _load_model_onnx(self, model_path: str) -> None:
        options = SessionOptions()
        options.enable_cpu_mem_arena = False
        options.graph_optimization_level = GraphOptimizationLevel.ORT_ENABLE_ALL

        try:
            import onnxruntime

            providers = (
                ["CUDAExecutionProvider", "CPUExecutionProvider"] if self._device == "gpu" else ["CPUExecutionProvider"]
            )
            available = onnxruntime.get_available_providers()
            providers = [p for p in providers if p in available]
            self._session = InferenceSession(model_path, options, providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            self._output_names = [o.name for o in self._session.get_outputs()]
            logger.info("agri_segmenter_onnx_loaded", model_path=model_path, device=self._device)
        except Exception as exc:
            logger.error("agri_segmenter_onnx_load_failed", error=str(exc))
            self._session = None

    def _load_model_yolo(self, model_path: str) -> None:
        try:
            from ultralytics import YOLO

            self._yolo_model = YOLO(model_path)
            logger.info("agri_segmenter_yolo_loaded", model_path=model_path)
        except Exception as exc:
            logger.error("agri_segmenter_yolo_load_failed", error=str(exc))
            self._yolo_model = None

    def segment(
        self,
        image: np.ndarray,
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
    ) -> list[InstanceMaskResult]:
        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            logger.warning("agri_segmenter_invalid_input")
            return []
        if image.ndim != 3 or image.shape[2] not in (1, 3, 4):
            logger.warning("agri_segmenter_invalid_channels", shape=image.shape)
            return []

        if self._yolo_model is not None:
            return self._segment_yolo(image, conf_threshold)

        if self._session is None:
            logger.warning("agri_segmenter_not_loaded")
            return []

        start = time.perf_counter()

        preprocessed = self._preprocess(image)
        outputs = self._session.run(self._output_names, {self._input_name: preprocessed})
        instances = self._postprocess(outputs, image.shape[:2], conf_threshold, iou_threshold)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug("agri_segmenter_onnx_inference", instances=len(instances), latency_ms=round(elapsed_ms, 2))

        return instances

    def _segment_yolo(
        self,
        image: np.ndarray,
        conf_threshold: float,
    ) -> list[InstanceMaskResult]:
        try:
            results = self._yolo_model.predict(image, conf=conf_threshold, verbose=False)
        except Exception as exc:
            logger.error("agri_segmenter_yolo_predict_failed", error=str(exc))
            return []

        instances: list[InstanceMaskResult] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            names = result.names
            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                class_name = names.get(cls_id, f"class_{cls_id}")
                if cls_id < len(self._class_names):
                    class_name = self._class_names[cls_id]
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                bbox = [x1, y1, x2 - x1, y2 - y1]
                instances.append(
                    InstanceMaskResult(
                        class_id=cls_id,
                        class_name=class_name,
                        confidence=conf,
                        bbox=bbox,
                        mask_rle="",
                    )
                )
        return instances

    def segment_batch(
        self,
        images: list[np.ndarray],
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
    ) -> list[list[InstanceMaskResult]]:
        return [self.segment(img, conf_threshold, iou_threshold) for img in images]

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        input_h, input_w = self._input_height, self._input_width
        img_h, img_w = image.shape[:2]
        scale = min(input_w / img_w, input_h / img_h)
        nw, nh = int(img_w * scale), int(img_h * scale)

        import cv2

        resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)

        canvas = np.full((input_h, input_w, 3), 114, dtype=np.uint8)
        dx = (input_w - nw) // 2
        dy = (input_h - nh) // 2
        canvas[dy : dy + nh, dx : dx + nw] = resized

        canvas = canvas.astype(np.float32) / 255.0
        canvas = np.transpose(canvas, (2, 0, 1))
        canvas = np.expand_dims(canvas, axis=0)
        return canvas

    def _postprocess(
        self,
        outputs: list[np.ndarray],
        original_shape: tuple[int, int],
        conf_threshold: float,
        iou_threshold: float,
    ) -> list[InstanceMaskResult]:
        predictions = outputs[0][0].transpose()
        protos = outputs[1][0] if len(outputs) > 1 else None

        class_ids = []
        confidences = []
        boxes = []
        mask_coefficients = []

        for pred in predictions:
            scores = pred[4:-32] if protos is not None else pred[4:]
            max_score = scores.max()
            if max_score < conf_threshold:
                continue
            class_id = int(scores.argmax())
            confidences.append(float(max_score))
            class_ids.append(class_id)

            cx, cy, w, h = pred[0], pred[1], pred[2], pred[3]
            x1 = cx - w / 2
            y1 = cy - h / 2
            boxes.append([x1, y1, w, h])

            if protos is not None:
                mask_coefficients.append(pred[-32:])

        if not boxes:
            return []

        indices = self._nms(boxes, confidences, iou_threshold)
        results = []
        orig_h, orig_w = original_shape

        for i in indices:
            box = boxes[i]
            conf = confidences[i]
            cid = class_ids[i]

            x1, y1, w, h = box
            x1_n = max(0, x1) / self._input_width
            y1_n = max(0, y1) / self._input_height
            w_n = min(w, self._input_width - x1) / self._input_width
            h_n = min(h, self._input_height - y1) / self._input_height
            bbox = [x1_n, y1_n, w_n, h_n]

            np.zeros((orig_h, orig_w), dtype=np.uint8)
            mask_rle = ""
            polygon = None

            if protos is not None and i < len(mask_coefficients):
                try:
                    proto = protos
                    coeffs = mask_coefficients[i]
                    masks_pred = np.tensordot(proto, coeffs, axes=([0], [0]))
                    masks_pred = 1.0 / (1.0 + np.exp(-masks_pred))
                    mask_sigmoid = masks_pred.reshape((self._input_height, self._input_width))

                    mask_small = cv2.resize(mask_sigmoid, (orig_w, orig_h))
                    mask_bin = (mask_small > 0.5).astype(np.uint8)

                    bbox_pixels = [
                        int(x1_n * orig_w),
                        int(y1_n * orig_h),
                        int((x1_n + w_n) * orig_w),
                        int((y1_n + h_n) * orig_h),
                    ]
                    bx1, by1, bx2, by2 = bbox_pixels
                    mask_bin[:by1, :] = 0
                    mask_bin[by2:, :] = 0
                    mask_bin[:, :bx1] = 0
                    mask_bin[:, bx2:] = 0

                    try:
                        from pycocotools import mask as mask_utils

                        rle = mask_utils.encode(np.asfortranarray(mask_bin))
                        mask_rle = rle["counts"].decode("ascii") if isinstance(rle["counts"], bytes) else rle["counts"]
                    except ImportError:
                        mask_rle = ""

                    try:
                        from skimage import measure
                        from skimage.measure import approximate_polygon

                        contours = measure.find_contours(mask_bin, 0.5)
                        if contours:
                            largest = max(contours, key=len)
                            simplified = approximate_polygon(largest, tolerance=2.0)
                            polygon = [[float(p[1]) / orig_w, float(p[0]) / orig_h] for p in simplified]
                    except ImportError:
                        polygon = None
                except Exception:
                    np.zeros((orig_h, orig_w), dtype=np.uint8)

            class_name = self._class_names[cid] if cid < len(self._class_names) else f"class_{cid}"

            results.append(
                InstanceMaskResult(
                    class_id=cid,
                    class_name=class_name,
                    confidence=conf,
                    bbox=bbox,
                    mask_rle=mask_rle,
                    polygon=polygon,
                )
            )

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

        keep = []
        while order.size > 0:
            i = order[0]
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

    def is_loaded(self) -> bool:
        return self._session is not None or self._yolo_model is not None


_crop_segmenter: AgriSegmenter | None = None
_health_segmenter: AgriSegmenter | None = None


def _classify_by_dominant_color(
    roi: np.ndarray, class_names: list[str]
) -> tuple[str, float]:
    """Heuristic: map dominant HSV color in a detection ROI to an agri class."""
    if roi is None or roi.size == 0:
        return class_names[0] if class_names else "unknown", 0.3

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    h_mean = float(np.mean(hsv[:, :, 0]))
    s_mean = float(np.mean(hsv[:, :, 1]))
    v_mean = float(np.mean(hsv[:, :, 2]))

    if s_mean < 30:
        if v_mean > 180:
            name = "cotton" if "cotton" in class_names else class_names[0]
        elif v_mean < 60:
            name = "bare_soil" if "bare_soil" in class_names else class_names[-1]
        else:
            name = class_names[0]
        return name, 0.45

    if 25 <= h_mean <= 45 and s_mean > 80:
        if "maize" in class_names:
            return "maize", 0.55
        if "healthy" in class_names:
            return "healthy", 0.6
    elif 35 <= h_mean <= 85 and s_mean > 60:
        if "vegetables" in class_names:
            return "vegetables", 0.5
        if "healthy" in class_names:
            return "healthy", 0.55
    elif h_mean < 15 or h_mean > 170:
        if "drought_stressed" in class_names:
            return "drought_stressed", 0.5
        if "stressed" in class_names:
            return "stressed", 0.45
        if "tobacco" in class_names:
            return "tobacco", 0.45
    elif 10 <= h_mean < 25:
        if "sweet_potato" in class_names:
            return "sweet_potato", 0.45
        if "stressed" in class_names:
            return "stressed", 0.4

    if v_mean < 80 and "diseased" in class_names:
        return "diseased", 0.4
    if v_mean > 200 and "healthy" in class_names:
        return "healthy", 0.5

    return class_names[0], 0.35


class _YoloFallbackSegmenter:
    """Wraps YOLOv8-seg to provide agri-like detections when no trained agri model exists.

    Uses the general-purpose YOLO seg model and applies color heuristics to
    map COCO classes to the requested agri taxonomy (crop type or health status).
    """

    def __init__(self, class_names: list[str]):
        self._class_names = class_names
        self._yolo = None

    def is_loaded(self) -> bool:
        return self._yolo is not None and self._yolo.is_loaded()

    def _ensure_loaded(self) -> bool:
        if self._yolo is not None:
            return self._yolo.is_loaded()
        try:
            from app.ai.yolo_seg import get_yolo_seg_segmenter
            self._yolo = get_yolo_seg_segmenter()
            return self._yolo.is_loaded()
        except Exception:
            return False

    def segment(
        self,
        image: np.ndarray,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
    ) -> list[InstanceMaskResult]:
        if not self._ensure_loaded():
            return []

        import cv2

        img_bytes = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
        instances_raw = self._yolo.detect(img_bytes, conf_threshold=conf_threshold)

        results = []
        for inst in instances_raw:
            coco_name = inst.get("class_name", "")
            bbox_norm = inst.get("bbox", [0, 0, 0, 0])
            h_img, w_img = image.shape[:2]
            x1 = int(bbox_norm[0] * w_img)
            y1 = int(bbox_norm[1] * h_img)
            bw = int(bbox_norm[2] * w_img)
            bh = int(bbox_norm[3] * h_img)
            x2 = min(x1 + bw, w_img)
            y2 = min(y1 + bh, h_img)

            roi = image[max(0, y1):y2, max(0, x1):x2]

            agri_name, agri_conf = _classify_by_dominant_color(roi, self._class_names)
            final_conf = (inst.get("confidence", 0.3) * 0.4 + agri_conf * 0.6)
            final_conf = min(max(final_conf, 0.15), 0.85)

            mask = inst.get("mask")
            polygon = None
            if mask is not None and hasattr(mask, "shape"):
                try:
                    from app.ai.yolo_seg import mask_to_polygon
                    polygon = mask_to_polygon(mask)
                except Exception:
                    pass

            results.append(
                InstanceMaskResult(
                    class_id=self._class_names.index(agri_name) if agri_name in self._class_names else 0,
                    class_name=agri_name,
                    confidence=round(final_conf, 4),
                    bbox=bbox_norm,
                    mask_rle="",
                    polygon=polygon,
                )
            )

        return results


def _build_yolo_fallback(class_names: list[str]) -> _YoloFallbackSegmenter:
    """Create a YOLO-based fallback segmenter for agri tasks."""
    fallback = _YoloFallbackSegmenter(class_names)
    fallback._ensure_loaded()
    if fallback.is_loaded():
        logger.info("agri_yolo_fallback_loaded", classes=len(class_names))
    else:
        logger.warning("agri_yolo_fallback_unavailable")
    return fallback


async def get_agri_crop_segmenter(
    model_path: str | None = None,
    device: str = "cpu",
    db=None,
) -> AgriSegmenter:
    """Return the crop-type segmenter (maize/rice/cassava/... — see
    app.models.agri_taxonomy.CROP_TYPES), preferring an active deployed
    model (ModelType.agri_crop_classification) over the hardcoded default path.
    """
    global _crop_segmenter

    if db is not None:
        try:
            from app.ai.model_inference import _download_artifact, get_active_deployed_model
            from app.models.enums import ModelType

            deployed = await get_active_deployed_model(db, ModelType.agri_crop_classification)
            if deployed is not None:
                local_path = _download_artifact(deployed.artifact_path)
                if local_path:
                    _crop_segmenter = AgriSegmenter(local_path, device, class_names=CROP_TYPES)
                    return _crop_segmenter
        except Exception:
            pass

    if _crop_segmenter is None and model_path:
        _crop_segmenter = AgriSegmenter(model_path, device, class_names=CROP_TYPES)
    elif _crop_segmenter is None:
        _crop_segmenter = AgriSegmenter(class_names=CROP_TYPES)
        if not _crop_segmenter.is_loaded():
            _crop_segmenter = _build_yolo_fallback(CROP_TYPES)
    return _crop_segmenter


async def get_agri_health_segmenter(
    model_path: str | None = None,
    device: str = "cpu",
    db=None,
) -> AgriSegmenter:
    """Return the crop-health segmenter (healthy/stressed/diseased/... — see
    app.models.agri_taxonomy.HEALTH_STATUS_TYPES), preferring an active
    deployed model (ModelType.agri_health_classification) over the hardcoded
    default path.
    """
    global _health_segmenter

    if db is not None:
        try:
            from app.ai.model_inference import _download_artifact, get_active_deployed_model
            from app.models.enums import ModelType

            deployed = await get_active_deployed_model(db, ModelType.agri_health_classification)
            if deployed is not None:
                local_path = _download_artifact(deployed.artifact_path)
                if local_path:
                    _health_segmenter = AgriSegmenter(local_path, device, class_names=HEALTH_STATUS_TYPES)
                    return _health_segmenter
        except Exception:
            pass

    if _health_segmenter is None and model_path:
        _health_segmenter = AgriSegmenter(model_path, device, class_names=HEALTH_STATUS_TYPES)
    elif _health_segmenter is None:
        _health_segmenter = AgriSegmenter(class_names=HEALTH_STATUS_TYPES)
        if not _health_segmenter.is_loaded():
            _health_segmenter = _build_yolo_fallback(HEALTH_STATUS_TYPES)
    return _health_segmenter


def dominant_class_name(instances: list[InstanceMaskResult], default: str) -> str:
    """Mode of class_name across a list of instances, or a default if empty."""
    if not instances:
        return default
    names = [inst.class_name for inst in instances]
    return max(set(names), key=names.count)
