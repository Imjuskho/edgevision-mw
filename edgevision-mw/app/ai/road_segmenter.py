from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from onnxruntime import GraphOptimizationLevel, InferenceSession, SessionOptions

from app.core.logging import get_logger

logger = get_logger("edgevision.road_segmenter")


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


ROAD_CLASS_NAMES = [
    "good_road", "pothole", "crack", "dust_road",
    "gravel_road", "road_marking", "shoulder",
]

ROAD_CLASS_COUNT = len(ROAD_CLASS_NAMES)


@dataclass
class LetterboxParams:
    scale: float
    dx: int
    dy: int
    nw: int
    nh: int
    orig_w: int
    orig_h: int


def is_coco_seg_model(model_path: str) -> bool:
    """Return True when an ONNX seg model is COCO-pretrained (not road)."""
    path = Path(model_path)
    if not path.exists() or path.suffix.lower() != ".onnx":
        return False
    try:
        import onnxruntime as ort

        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        meta = session.get_modelmeta().custom_metadata_map or {}
        description = str(meta.get("description", "")).lower()
        if "coco" in description:
            return True
        names_raw = meta.get("names", "")
        if isinstance(names_raw, str) and names_raw:
            # COCO models expose 80 classes; road models expose 7.
            if names_raw.count(":") >= 79 or "person" in names_raw:
                return True
    except Exception as exc:
        logger.warning("road_seg_coco_check_failed", model_path=model_path, error=str(exc))
    return False


def is_valid_road_seg_model(model_path: str) -> bool:
    """A road segmentation model must exist, be ONNX, and not be COCO-pretrained."""
    path = Path(model_path)
    if not path.exists():
        return False
    if path.suffix.lower() == ".pt":
        logger.warning("road_seg_pt_rejected", model_path=model_path)
        return False
    if path.suffix.lower() != ".onnx":
        return False
    if is_coco_seg_model(str(path)):
        logger.error("road_seg_coco_model_rejected", model_path=model_path)
        return False
    return True


class RoadSegmenter:
    """Road surface instance segmentation supporting ONNX Runtime."""

    def __init__(self, model_path: str | None = None, device: str = "cpu"):
        self._model_path = model_path
        self._device = device
        self._session: InferenceSession | None = None
        self._input_name: str | None = None
        self._output_names: list[str] | None = None
        self._input_width = 640
        self._input_height = 640
        self._letterbox: LetterboxParams | None = None

        if model_path and Path(model_path).exists():
            ext = Path(model_path).suffix.lower()
            if ext == ".onnx":
                if is_valid_road_seg_model(model_path):
                    self._load_model_onnx(model_path)
                else:
                    logger.error("road_segmenter_invalid_model", model_path=model_path)
            elif ext == ".pt":
                logger.error(
                    "road_segmenter_pt_not_supported",
                    model_path=model_path,
                    detail="Use exported road ONNX (models/road_seg/best.onnx)",
                )
            else:
                logger.warning("road_segmenter_unknown_format", model_path=model_path, ext=ext)
        else:
            logger.warning("road_segmenter_no_model", model_path=model_path)

    def _load_model_onnx(self, model_path: str) -> None:
        options = SessionOptions()
        options.enable_cpu_mem_arena = False
        options.graph_optimization_level = GraphOptimizationLevel.ORT_ENABLE_ALL

        try:
            import onnxruntime

            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if self._device == "gpu" else ["CPUExecutionProvider"]
            available = onnxruntime.get_available_providers()
            providers = [p for p in providers if p in available]
            self._session = InferenceSession(model_path, options, providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            self._output_names = [o.name for o in self._session.get_outputs()]
            logger.info("road_segmenter_onnx_loaded", model_path=model_path, device=self._device)
        except Exception as exc:
            logger.error("road_segmenter_onnx_load_failed", error=str(exc), exc_info=True)
            self._session = None

    def segment(
        self,
        image: np.ndarray,
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
    ) -> list[InstanceMaskResult]:
        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            logger.warning("road_segmenter_invalid_input")
            return []
        if image.ndim != 3 or image.shape[2] not in (1, 3, 4):
            logger.warning("road_segmenter_invalid_channels", shape=image.shape)
            return []

        if self._session is None:
            logger.warning("road_segmenter_not_loaded")
            return []

        start = time.perf_counter()

        preprocessed = self._preprocess(image)
        outputs = self._session.run(self._output_names, {self._input_name: preprocessed})
        instances = self._postprocess(outputs, image.shape[:2], conf_threshold, iou_threshold)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug("road_segmenter_onnx_inference", instances=len(instances), latency_ms=round(elapsed_ms, 2))

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

        resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)

        canvas = np.full((input_h, input_w, 3), 114, dtype=np.uint8)
        dx = (input_w - nw) // 2
        dy = (input_h - nh) // 2
        canvas[dy:dy + nh, dx:dx + nw] = resized

        self._letterbox = LetterboxParams(
            scale=scale,
            dx=dx,
            dy=dy,
            nw=nw,
            nh=nh,
            orig_w=img_w,
            orig_h=img_h,
        )

        canvas = canvas.astype(np.float32) / 255.0
        canvas = np.transpose(canvas, (2, 0, 1))
        canvas = np.expand_dims(canvas, axis=0)
        return canvas

    def _model_to_orig(self, cx: float, cy: float, w: float, h: float) -> tuple[float, float, float, float]:
        """Convert model-space center box to original-image pixel x1,y1,x2,y2."""
        lb = self._letterbox
        if lb is None:
            return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        x1 = (cx - w / 2 - lb.dx) / lb.scale
        y1 = (cy - h / 2 - lb.dy) / lb.scale
        x2 = (cx + w / 2 - lb.dx) / lb.scale
        y2 = (cy + h / 2 - lb.dy) / lb.scale
        x1 = max(0.0, min(lb.orig_w, x1))
        y1 = max(0.0, min(lb.orig_h, y1))
        x2 = max(0.0, min(lb.orig_w, x2))
        y2 = max(0.0, min(lb.orig_h, y2))
        return x1, y1, x2, y2

    def _mask_to_orig(self, mask_sigmoid: np.ndarray) -> np.ndarray:
        """Undo letterbox on a model-space mask and resize to original image size."""
        lb = self._letterbox
        if lb is None:
            return cv2.resize(mask_sigmoid, (mask_sigmoid.shape[1], mask_sigmoid.shape[0]))

        mask_2d = mask_sigmoid.reshape((self._input_height, self._input_width))
        cropped = mask_2d[lb.dy:lb.dy + lb.nh, lb.dx:lb.dx + lb.nw]
        return cv2.resize(cropped, (lb.orig_w, lb.orig_h), interpolation=cv2.INTER_LINEAR)

    def _extract_polygon(self, mask_bin: np.ndarray, orig_w: int, orig_h: int) -> list[list[float]] | None:
        try:
            from skimage import measure
            from skimage.measure import approximate_polygon

            contours = measure.find_contours(mask_bin, 0.5)
            if not contours:
                return None
            largest = max(contours, key=len)
            simplified = approximate_polygon(largest, tolerance=2.0)
            return [[float(p[1]) / orig_w, float(p[0]) / orig_h] for p in simplified]
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("road_segmenter_skimage_polygon_failed", error=str(exc))

        contours, _ = cv2.findContours(
            (mask_bin > 0.5).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return None
        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < 10:
            return None
        epsilon = 0.005 * cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, epsilon, True)
        if len(approx) < 3:
            return None
        pts = approx.reshape(-1, 2)
        return [[float(x) / orig_w, float(y) / orig_h] for x, y in pts]

    def _encode_rle(self, mask_bin: np.ndarray) -> str:
        try:
            from pycocotools import mask as mask_utils

            rle = mask_utils.encode(np.asfortranarray(mask_bin))
            counts = rle["counts"]
            return counts.decode("ascii") if isinstance(counts, bytes) else counts
        except ImportError:
            return ""

    def _postprocess(
        self,
        outputs: list[np.ndarray],
        original_shape: tuple[int, int],
        conf_threshold: float,
        iou_threshold: float,
    ) -> list[InstanceMaskResult]:
        predictions = outputs[0][0].transpose()
        protos_raw = outputs[1][0] if len(outputs) > 1 else None
        protos = None
        if protos_raw is not None:
            if protos_raw.ndim == 3:
                protos = protos_raw.reshape(protos_raw.shape[0], -1)
            elif protos_raw.ndim == 4:
                protos = protos_raw[0].reshape(protos_raw.shape[1], -1)
            else:
                protos = protos_raw

        class_ids: list[int] = []
        confidences: list[float] = []
        boxes: list[list[float]] = []
        mask_coefficients: list[np.ndarray] = []

        for pred in predictions:
            scores = pred[4:-32] if protos is not None else pred[4:]
            max_score = float(scores.max())
            if max_score > 1.0:
                max_score = 1.0 / (1.0 + np.exp(-max_score))
            if max_score < conf_threshold:
                continue
            class_id = int(scores.argmax())
            if class_id >= ROAD_CLASS_COUNT:
                continue
            confidences.append(max_score)
            class_ids.append(class_id)

            cx, cy, w, h = pred[0], pred[1], pred[2], pred[3]
            boxes.append([cx, cy, w, h])

            if protos is not None:
                mask_coefficients.append(pred[-32:])

        if not boxes:
            return []

        indices = self._nms(boxes, confidences, iou_threshold)
        results = []
        orig_h, orig_w = original_shape

        for i in indices:
            cx, cy, w, h = boxes[i]
            conf = confidences[i]
            cid = class_ids[i]

            x1, y1, x2, y2 = self._model_to_orig(cx, cy, w, h)
            bbox = [
                x1 / orig_w,
                y1 / orig_h,
                max(0.0, (x2 - x1) / orig_w),
                max(0.0, (y2 - y1) / orig_h),
            ]

            mask_rle = ""
            polygon = None

            if protos is not None and i < len(mask_coefficients):
                try:
                    coeffs = mask_coefficients[i]
                    masks_pred = np.dot(coeffs, protos)
                    masks_pred = 1.0 / (1.0 + np.exp(-np.clip(masks_pred, -50, 50)))
                    mask_sigmoid = masks_pred.reshape((self._input_height // 4, self._input_width // 4))
                    mask_full = cv2.resize(
                        mask_sigmoid,
                        (self._input_width, self._input_height),
                        interpolation=cv2.INTER_LINEAR,
                    )
                    mask_small = self._mask_to_orig(mask_full)
                    mask_bin = (mask_small > 0.5).astype(np.uint8)

                    bx1, by1, bx2, by2 = int(x1), int(y1), int(x2), int(y2)
                    mask_bin[:by1, :] = 0
                    mask_bin[by2:, :] = 0
                    mask_bin[:, :bx1] = 0
                    mask_bin[:, bx2:] = 0

                    mask_rle = self._encode_rle(mask_bin)
                    polygon = self._extract_polygon(mask_bin, orig_w, orig_h)
                except Exception as exc:
                    logger.error("road_segmenter_mask_extract_failed", error=str(exc), exc_info=True)

            class_name = ROAD_CLASS_NAMES[cid] if cid < len(ROAD_CLASS_NAMES) else f"class_{cid}"

            results.append(InstanceMaskResult(
                class_id=cid,
                class_name=class_name,
                confidence=conf,
                bbox=bbox,
                mask_rle=mask_rle,
                polygon=polygon,
            ))

        return results

    def _nms(self, boxes: list[list[float]], scores: list[float], iou_threshold: float) -> list[int]:
        if not boxes:
            return []

        boxes_arr = np.array(boxes)
        scores_arr = np.array(scores)
        cx = boxes_arr[:, 0]
        cy = boxes_arr[:, 1]
        w = boxes_arr[:, 2]
        h = boxes_arr[:, 3]
        x1 = cx - w / 2
        y1 = cy - h / 2
        x2 = cx + w / 2
        y2 = cy + h / 2
        areas = w * h
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
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)

            order = order[1:][iou <= iou_threshold]

        return keep

    def is_loaded(self) -> bool:
        return self._session is not None


_segmenter: RoadSegmenter | None = None


def resolve_road_seg_model_path(explicit_path: str | None = None) -> str | None:
    """Locate a road-trained segmentation ONNX on disk.

    Resolution order:
      1. Explicit path argument / ``ROAD_SEG_MODEL_PATH``
      2. Local ``models/road_seg/best.onnx`` (trained artifact)
      3. ``models/road_seg/best.onnx`` under repo root

    COCO-pretrained ONNX and ``.pt`` weights are explicitly rejected.
    """
    from app.core.config import settings

    repo_root = Path(__file__).resolve().parents[2]
    candidates: list[Path] = []

    for raw in (explicit_path, settings.ROAD_SEG_MODEL_PATH):
        if raw:
            candidates.append(Path(raw))

    candidates.extend([
        repo_root / "models/road_seg/best.onnx",
        repo_root / "models/road_seg/weights/best.onnx",
    ])

    for candidate in candidates:
        if candidate.exists() and is_valid_road_seg_model(str(candidate)):
            return str(candidate)

    return None


async def get_road_segmenter(
    model_path: str | None = None,
    device: str = "cpu",
    db=None,
) -> RoadSegmenter:
    global _segmenter

    if db is not None:
        try:
            from app.ai.model_inference import _download_artifact, get_active_deployed_model
            from app.models.enums import ModelType

            deployed = await get_active_deployed_model(db, ModelType.road_segmentation)
            if deployed is not None:
                local_path = _download_artifact(deployed.artifact_path)
                if local_path and is_valid_road_seg_model(local_path):
                    _segmenter = RoadSegmenter(local_path, device)
                    return _segmenter
                logger.error(
                    "road_segmenter_deployed_model_rejected",
                    artifact_path=deployed.artifact_path,
                    reason="COCO or invalid format — train with scripts/train_road_seg.py",
                )
        except Exception as exc:
            logger.error("road_segmenter_deployed_load_failed", error=str(exc), exc_info=True)

    resolved = resolve_road_seg_model_path(model_path)
    if _segmenter is None or not _segmenter.is_loaded():
        _segmenter = RoadSegmenter(resolved, device) if resolved else RoadSegmenter()
    return _segmenter


def classify_surface_type(instances: list[InstanceMaskResult]) -> str:
    paved_classes = {0, 5, 6}
    unpaved_classes = {3, 4}
    paved_count = sum(1 for i in instances if i.class_id in paved_classes)
    unpaved_count = sum(1 for i in instances if i.class_id in unpaved_classes)
    total = paved_count + unpaved_count
    if total == 0:
        return "unpaved"
    paved_ratio = paved_count / total
    unpaved_ratio = unpaved_count / total
    if paved_ratio > 0.7:
        return "paved"
    if unpaved_ratio > 0.7:
        return "unpaved"
    return "mixed"
