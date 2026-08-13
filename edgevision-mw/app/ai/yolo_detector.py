from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger("edgevision.yolo_detector")


@dataclass
class Detection:
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


class YOLODetector:
    """YOLOv8 detector backed by ultralytics.

    Loads a generic pretrained checkpoint by default (yolov8x.pt for
    detection). Pass model_path to load a specific checkpoint instead — e.g.
    a fine-tuned classification model (yolov8n-cls.pt) for the classify()
    path used by point/box-prompt annotation assist.

    For platform-trained models promoted through the model registry, prefer
    app.ai.model_inference.get_trained_engine, which exposes the same
    detect()/classify() interface backed by a downloaded MinIO artifact.
    """

    def __init__(self, model_path: str | None = None):
        self._model_path = model_path or "yolov8x.pt"
        self._model = None
        self._load()

    def _load(self) -> None:
        try:
            from ultralytics import YOLO

            self._model = YOLO(self._model_path)
            logger.info("yolo_detector_loaded", model_path=self._model_path)
        except Exception as exc:
            logger.error("yolo_detector_load_failed", error=str(exc), model_path=self._model_path)
            self._model = None

    def is_loaded(self) -> bool:
        return self._model is not None

    def detect(self, image, conf_threshold: float = 0.35) -> list[Detection]:
        if self._model is None:
            return []
        try:
            results = self._model.predict(image, conf=conf_threshold, verbose=False)
        except Exception as exc:
            logger.error("yolo_detect_failed", error=str(exc))
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
        if self._model is None or crop is None or getattr(crop, "size", 0) == 0:
            return {"class_name": "unknown", "confidence": 0.0}
        try:
            results = self._model.predict(crop, verbose=False)
        except Exception as exc:
            logger.error("yolo_classify_failed", error=str(exc))
            return {"class_name": "unknown", "confidence": 0.0}

        if not results:
            return {"class_name": "unknown", "confidence": 0.0}

        result = results[0]

        # Classification-head models (e.g. yolov8n-cls) expose .probs
        if getattr(result, "probs", None) is not None:
            top1 = int(result.probs.top1)
            conf = float(result.probs.top1conf)
            return {"class_name": result.names.get(top1, f"class_{top1}"), "confidence": conf}

        # Detection/segmentation models: fall back to the highest-confidence box
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return {"class_name": "unknown", "confidence": 0.0}
        best_idx = int(boxes.conf.argmax())
        cls_id = int(boxes.cls[best_idx])
        conf = float(boxes.conf[best_idx])
        return {"class_name": result.names.get(cls_id, f"class_{cls_id}"), "confidence": conf}
