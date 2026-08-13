from __future__ import annotations

import os
import threading
import zipfile

import numpy as np

from app.ai.yolo_detector import Detection, YOLODetector
from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import ModelFormat, ModelType

logger = get_logger("edgevision.model_inference")

_CACHE_DIR = "/tmp/edgevision-model-cache"
_lock = threading.Lock()
_engine_cache: dict[str, BaseEngine] = {}

_lkg_cache: dict[str, BaseEngine] = {}


def _set_lkg(model_type: ModelType, engine: BaseEngine) -> None:
    key = model_type.value
    _lkg_cache[key] = engine


def _get_lkg(model_type: ModelType) -> BaseEngine | None:
    return _lkg_cache.get(model_type.value)


def get_lkg_status() -> dict[str, str]:
    return {k: "loaded" for k in _lkg_cache}


def _resolve_object_key(artifact_path: str) -> str:
    prefix = f"{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/"
    if artifact_path.startswith(prefix):
        return artifact_path[len(prefix):]
    return artifact_path.lstrip("/")


def _download_artifact(artifact_path: str) -> str:
    if os.path.exists(artifact_path):
        return artifact_path

    object_key = _resolve_object_key(artifact_path)
    local_path = os.path.join(_CACHE_DIR, object_key)

    if os.path.exists(local_path):
        return local_path

    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    import minio

    mc = minio.Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )
    mc.fget_object(settings.MINIO_BUCKET, object_key, local_path)
    logger.info("model_artifact_downloaded", object_key=object_key, local_path=local_path)
    return local_path


def _detect_format(path: str) -> ModelFormat:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".onnx":
        return ModelFormat.ONNX
    if ext in (".torchscript", ".ts"):
        return ModelFormat.TORCHSCRIPT
    return ModelFormat.ULTRALYTICS


class BaseEngine:
    def __init__(self, model_type: ModelType | None = None):
        self._metrics_model_type = model_type.value if model_type else "unknown"

    def is_loaded(self) -> bool:
        return False

    def detect(self, image, conf_threshold: float = 0.35) -> list[Detection]:
        return []

    def classify(self, crop) -> dict:
        return {"class_name": "unknown", "confidence": 0.0}

    def _track_inference(self, method: str, func, *args, **kwargs):
        import time

        from app.api.metrics import inference_duration_seconds, inference_requests_total

        start = time.time()
        try:
            result = func(*args, **kwargs)
            inference_requests_total.labels(model_type=self._metrics_model_type, status="success").inc()
            return result
        except Exception:
            inference_requests_total.labels(model_type=self._metrics_model_type, status="failure").inc()
            raise
        finally:
            inference_duration_seconds.labels(model_type=self._metrics_model_type).observe(time.time() - start)


class ONNXEngine(BaseEngine):
    def __init__(self, local_path: str, model_type: ModelType):
        super().__init__(model_type)
        self._local_path = local_path
        self._model_type = model_type
        self._session = None
        self._input_name: str | None = None
        self._output_names: list[str] | None = None
        self._input_width = 640
        self._input_height = 640
        self._load()

    def _load(self) -> None:
        try:
            if zipfile.is_zipfile(self._local_path):
                raise ValueError("Invalid ONNX model file: zip archive detected")

            import onnxruntime
            from onnxruntime import GraphOptimizationLevel, SessionOptions

            options = SessionOptions()
            options.enable_cpu_mem_arena = False
            options.graph_optimization_level = GraphOptimizationLevel.ORT_ENABLE_ALL
            available = onnxruntime.get_available_providers()
            providers = [p for p in ["CUDAExecutionProvider", "CPUExecutionProvider"] if p in available]
            self._session = onnxruntime.InferenceSession(self._local_path, options, providers=providers)
            self._input_name = self._session.get_inputs()[0].name
            self._output_names = [o.name for o in self._session.get_outputs()]
            logger.info("onnx_engine_loaded", path=self._local_path, model_type=self._model_type.value)
        except Exception as exc:
            logger.error("onnx_engine_load_failed", error=str(exc), path=self._local_path)
            self._session = None

    def is_loaded(self) -> bool:
        return self._session is not None

    def detect(self, image, conf_threshold: float = 0.35) -> list[Detection]:
        return self._track_inference(
            "detect", self._detect_impl, image, conf_threshold
        )

    def _detect_impl(self, image, conf_threshold: float = 0.35) -> list[Detection]:
        if self._session is None:
            return []
        try:
            import cv2

            img = np.array(image) if not isinstance(image, np.ndarray) else image
            orig_h, orig_w = img.shape[:2]
            scale = min(self._input_width / orig_w, self._input_height / orig_h)
            nw, nh = int(orig_w * scale), int(orig_h * scale)
            resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
            canvas = np.full((self._input_height, self._input_width, 3), 114, dtype=np.uint8)
            dx = (self._input_width - nw) // 2
            dy = (self._input_height - nh) // 2
            canvas[dy:dy + nh, dx:dx + nw] = resized
            blob = np.transpose(canvas.astype(np.float32) / 255.0, (2, 0, 1))[np.newaxis]

            outputs = self._session.run(self._output_names, {self._input_name: blob})

            detections: list[Detection] = []
            predictions = outputs[0][0].transpose()
            for pred in predictions:
                scores = pred[4:]
                max_score = float(scores.max())
                if max_score < conf_threshold:
                    continue
                cls_id = int(scores.argmax())
                cx, cy, w, h = pred[0], pred[1], pred[2], pred[3]
                x1 = (cx - w / 2 - dx) / scale
                y1 = (cy - h / 2 - dy) / scale
                x2 = (cx + w / 2 - dx) / scale
                y2 = (cy + h / 2 - dy) / scale
                detections.append(Detection(
                    class_name=f"class_{cls_id}",
                    confidence=max_score,
                    x1=max(0, x1),
                    y1=max(0, y1),
                    x2=min(orig_w, x2),
                    y2=min(orig_h, y2),
                ))
            return detections
        except Exception as exc:
            logger.error("onnx_engine_detect_failed", error=str(exc))
            return []

    def classify(self, crop) -> dict:
        return {"class_name": "unknown", "confidence": 0.0}


class TrainedModelEngine(BaseEngine):
    def __init__(self, local_path: str, model_type: ModelType):
        super().__init__(model_type)
        self._local_path = local_path
        self._model_type = model_type
        self._model = None
        self._load()

    def _load(self) -> None:
        try:
            from ultralytics import YOLO

            self._model = YOLO(self._local_path)
            logger.info(
                "trained_model_loaded",
                path=self._local_path,
                model_type=self._model_type.value,
            )
        except Exception as exc:
            logger.error("trained_model_load_failed", error=str(exc), path=self._local_path)
            self._model = None

    def is_loaded(self) -> bool:
        return self._model is not None

    def detect(self, image, conf_threshold: float = 0.35) -> list[Detection]:
        return self._track_inference(
            "detect", self._detect_impl, image, conf_threshold
        )

    def _detect_impl(self, image, conf_threshold: float = 0.35) -> list[Detection]:
        if self._model is None:
            return []
        try:
            results = self._model.predict(image, conf=conf_threshold, verbose=False)
        except Exception as exc:
            logger.error("trained_model_detect_failed", error=str(exc))
            return []

        detections: list[Detection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            names = result.names
            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                detections.append(
                    Detection(
                        class_name=names.get(cls_id, f"class_{cls_id}"),
                        confidence=conf,
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                    )
                )
        return detections

    def classify(self, crop) -> dict:
        return self._track_inference("classify", self._classify_impl, crop)

    def _classify_impl(self, crop) -> dict:
        if self._model is None or crop is None or getattr(crop, "size", 0) == 0:
            return {"class_name": "unknown", "confidence": 0.0}
        try:
            results = self._model.predict(crop, verbose=False)
        except Exception as exc:
            logger.error("trained_model_classify_failed", error=str(exc))
            return {"class_name": "unknown", "confidence": 0.0}

        if not results:
            return {"class_name": "unknown", "confidence": 0.0}

        result = results[0]

        if getattr(result, "probs", None) is not None:
            top1 = int(result.probs.top1)
            conf = float(result.probs.top1conf)
            return {"class_name": result.names.get(top1, f"class_{top1}"), "confidence": conf}

        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return {"class_name": "unknown", "confidence": 0.0}
        best_idx = int(boxes.conf.argmax())
        cls_id = int(boxes.cls[best_idx])
        conf = float(boxes.conf[best_idx])
        return {"class_name": result.names.get(cls_id, f"class_{cls_id}"), "confidence": conf}


class SimpleFallbackEngine(BaseEngine):
    """Minimal placeholder engine used when no trained or local YOLO model can be loaded."""

    def __init__(self, model_type: ModelType):
        super().__init__(model_type)

    def is_loaded(self) -> bool:
        # This engine does not perform real inference. Treat it as unloaded so
        # callers can detect the absence of a valid model and fail fast.
        return False

    def detect(self, image, conf_threshold: float = 0.35) -> list[Detection]:
        return []

    def classify(self, crop) -> dict:
        return {"class_name": "unknown", "confidence": 0.0}


def _build_engine(local_path: str, model_type: ModelType) -> BaseEngine:
    fmt = _detect_format(local_path)
    if fmt == ModelFormat.ONNX:
        return ONNXEngine(local_path, model_type)
    return TrainedModelEngine(local_path, model_type)


def get_trained_engine(artifact_path: str, model_type: ModelType) -> BaseEngine:
    with _lock:
        cached = _engine_cache.get(artifact_path)
        if cached is not None:
            return cached

    local_path = _download_artifact(artifact_path)

    with _lock:
        cached = _engine_cache.get(artifact_path)
        if cached is not None:
            return cached
        engine = _build_engine(local_path, model_type)
        if engine.is_loaded():
            _set_lkg(model_type, engine)
        _engine_cache[artifact_path] = engine
        return engine


def clear_cache() -> None:
    with _lock:
        _engine_cache.clear()


async def get_active_deployed_model(db, model_type: ModelType):
    from sqlalchemy import select

    from app.models.deployed_model import DeployedModel

    result = await db.execute(
        select(DeployedModel).where(
            DeployedModel.model_type == model_type,
            DeployedModel.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


def _get_local_fallback_engine(model_type: ModelType) -> BaseEngine | None:
    candidates: list[str] = []
    if model_type == ModelType.object_detection:
        candidates = ["yolov8n.pt", "yolov8x.pt"]
    elif model_type == ModelType.classification:
        candidates = ["yolov8n-cls.pt", "yolov8x.pt"]
    elif model_type == ModelType.road_segmentation:
        candidates = ["yolov8n-seg.pt", "yolov8x.pt"]
    else:
        candidates = ["yolov8x.pt"]

    config_paths = [
        settings.YOLOV8X_PATH,
        settings.YOLOV8_SEG_MODEL_PATH,
        settings.ROAD_SEG_MODEL_PATH,
        settings.AGRI_CROP_SEG_MODEL_PATH,
        settings.AGRI_HEALTH_SEG_MODEL_PATH,
    ]
    for configured_path in config_paths:
        if configured_path and os.path.exists(configured_path):
            engine = YOLODetector(configured_path)
            if engine.is_loaded():
                _set_lkg(model_type, engine)
                return engine

    roots = [
        os.getcwd(),
        os.path.dirname(__file__),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
        os.path.join(os.getcwd(), "frontend", "public", "models"),
    ]

    for root in roots:
        for candidate in candidates:
            candidate_path = os.path.join(root, candidate)
            if os.path.exists(candidate_path):
                engine = YOLODetector(candidate_path)
                if engine.is_loaded():
                    _set_lkg(model_type, engine)
                    return engine

    for candidate in candidates:
        engine = YOLODetector(candidate)
        if engine.is_loaded():
            _set_lkg(model_type, engine)
            return engine

    logger.warning(
        "local_fallback_engine_unavailable",
        model_type=model_type.value,
        candidates=candidates,
    )
    return SimpleFallbackEngine(model_type)


async def get_active_engine(db, model_type: ModelType) -> BaseEngine | None:
    lkg = _get_lkg(model_type)
    if lkg is not None:
        return lkg

    if db is None:
        fallback = _get_local_fallback_engine(model_type)
        if fallback is not None:
            logger.info(
                "falling_back_to_local_model_without_db",
                model_type=model_type.value,
            )
            return fallback
        return None

    try:
        deployed = await get_active_deployed_model(db, model_type)
    except Exception as exc:
        logger.warning(
            "active_deployed_model_lookup_failed",
            model_type=model_type.value,
            error=str(exc),
        )
        deployed = None

    if deployed is None:
        fallback = _get_local_fallback_engine(model_type)
        if fallback is not None:
            logger.info(
                "falling_back_to_local_model",
                model_type=model_type.value,
            )
            return fallback
        return None

    try:
        engine = get_trained_engine(deployed.artifact_path, model_type)
        if engine is not None and engine.is_loaded():
            return engine
    except Exception as exc:
        logger.error(
            "active_engine_load_failed",
            error=str(exc),
            deployed_model_id=str(deployed.id),
        )
        engine = None

    lkg = _get_lkg(model_type)
    if lkg is not None:
        logger.warning(
            "falling_back_to_lkg",
            model_type=model_type.value,
        )
        return lkg

    fallback = _get_local_fallback_engine(model_type)
    if fallback is not None:
        logger.info(
            "falling_back_to_local_model_after_deployment_error",
            model_type=model_type.value,
        )
        return fallback
    return None
