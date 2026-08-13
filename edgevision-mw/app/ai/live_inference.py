"""Optimized inference path for live WebSocket annotation."""
from __future__ import annotations

import os

import numpy as np

from app.ai.mono_3d import attach_3d_boxes
from app.ai.scene_objects import enrich_live_detections
from app.ai.yolo_seg import SEG_TO_TAXONOMY, attach_masks_from_instances, get_yolo_seg_segmenter, mask_to_polygon
from app.core.logging import get_logger
from app.models.enums import ModelType

logger = get_logger("edgevision.live_inference")

LIVE_CONF = float(os.environ.get("LIVE_DETECT_CONF", "0.22"))
DEPTH_EVERY_N_FRAMES = int(os.environ.get("LIVE_DEPTH_EVERY_N", "5"))
LIVE_SCENE_ENRICH = os.environ.get("LIVE_SCENE_ENRICH", "0") == "1"


def _as_list4(bbox) -> list[float]:
    if bbox is None:
        return []
    if hasattr(bbox, "tolist"):
        bbox = bbox.tolist()
    return [float(v) for v in bbox[:4]]


def _inst_to_track_dict(inst: dict, img_w: int, img_h: int) -> dict:
    bbox = inst["bbox"]
    if bbox[2] <= 1.0:
        x1 = bbox[0] * img_w
        y1 = bbox[1] * img_h
        x2 = (bbox[0] + bbox[2]) * img_w
        y2 = (bbox[1] + bbox[3]) * img_h
    else:
        x1, y1 = bbox[0], bbox[1]
        x2, y2 = bbox[0] + bbox[2], bbox[1] + bbox[3]

    entry: dict = {
        "bbox": [x1, y1, x2, y2],
        "class_name": inst["class_name"],
        "confidence": inst["confidence"],
    }
    if inst.get("mask") is not None:
        polygon = mask_to_polygon(inst["mask"])
        if polygon:
            entry["mask"] = polygon
            entry["mask_format"] = "polygon"
    return entry


def run_seg_primary_detection(
    frame_bytes: bytes,
    image: np.ndarray,
    tracker,
    model_type: str,
    conf_threshold: float = LIVE_CONF,
) -> tuple[list[dict], list[dict]]:
    """Single-pass YOLOv8-seg detect + track (avoids duplicate YOLO forward pass)."""
    segmenter = get_yolo_seg_segmenter()
    if not segmenter.is_loaded():
        return [], []

    instances = segmenter.detect(frame_bytes, conf_threshold=conf_threshold)
    if not instances:
        return [], instances

    h, w = image.shape[:2]
    det_dicts = [_inst_to_track_dict(inst, w, h) for inst in instances]
    tracked = tracker.update(det_dicts, image=None)
    tracked = attach_masks_from_instances(tracked, instances, w, h)

    seg_capable = model_type in (
        ModelType.object_detection.value,
        ModelType.road_segmentation.value,
        ModelType.agri_crop_classification.value,
        ModelType.agri_health_classification.value,
    )
    if LIVE_SCENE_ENRICH and seg_capable and model_type == ModelType.object_detection.value:
        tracked = enrich_live_detections(tracked, instances, image)

    return tracked, instances


def run_engine_detection(
    engine,
    image: np.ndarray,
    frame_bytes: bytes,
    tracker,
    model_type: str,
    conf_threshold: float = LIVE_CONF,
) -> tuple[list[dict], list]:
    """Fallback when seg ONNX is unavailable."""
    from app.ai.yolo_seg import attach_mask_polygons

    detections = engine.detect(image, conf_threshold=conf_threshold)
    det_dicts = [
        {
            "bbox": [d.x1, d.y1, d.x2, d.y2],
            "class_name": d.class_name,
            "confidence": d.confidence,
        }
        for d in detections
    ]
    tracked = tracker.update(det_dicts, image=None)

    seg_capable = model_type in (
        ModelType.object_detection.value,
        ModelType.road_segmentation.value,
        ModelType.agri_crop_classification.value,
        ModelType.agri_health_classification.value,
    )
    if seg_capable and tracked:
        tracked = attach_mask_polygons(tracked, frame_bytes, conf_threshold=conf_threshold)

    return tracked, detections


def maybe_estimate_depth(
    image: np.ndarray,
    tracked: list[dict],
    model_type: str,
    frame_index: int,
    cached: tuple[np.ndarray | None, bool] | None,
) -> tuple[np.ndarray | None, bool, bool]:
    """Return ``(depth_map, depth_available, from_cache)``."""
    if not tracked or model_type != ModelType.object_detection.value:
        return None, False, True
    if frame_index % DEPTH_EVERY_N_FRAMES != 0 and cached is not None:
        depth_map, depth_available = cached
        return depth_map, depth_available, True

    try:
        from app.ai.depth_estimator import get_depth_estimator

        depth_est = get_depth_estimator()
        depth_map, depth_available = depth_est.estimate_depth_map(image)
        return depth_map, depth_available, False
    except Exception as exc:
        logger.debug("live_depth_skipped", error=str(exc))
        if cached is not None:
            depth_map, depth_available = cached
            return depth_map, depth_available, True
        return None, False, True


def _json_safe(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def build_annotations(tracked: list[dict]) -> list[dict]:
    annotations = []
    for t in tracked:
        bbox = _as_list4(t.get("bbox"))
        if len(bbox) == 4 and bbox[2] > bbox[0]:
            xywh = [bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1]]
        else:
            xywh = bbox

        track_id = t.get("track_id")
        if isinstance(track_id, np.generic):
            track_id = int(track_id)

        ann: dict = {
            "class_name": t["class_name"],
            "taxonomy_label": SEG_TO_TAXONOMY.get(t["class_name"], t.get("taxonomy_label", t["class_name"])),
            "confidence": round(float(t["confidence"]), 4),
            "bbox": [_json_safe(v) for v in xywh],
            "track_id": track_id,
            "mask_format": t.get("mask_format"),
        }
        if t.get("mask"):
            ann["mask"] = _json_safe(t["mask"])
        if t.get("bbox_3d"):
            ann["bbox_3d"] = _json_safe(t["bbox_3d"])
        annotations.append(ann)
    return annotations


def attach_depth_boxes(
    tracked: list[dict],
    image: np.ndarray,
    depth_map: np.ndarray | None,
    depth_available: bool,
) -> list[dict]:
    if not tracked:
        return tracked
    for det in tracked:
        if "taxonomy_label" not in det:
            det["taxonomy_label"] = SEG_TO_TAXONOMY.get(det.get("class_name", ""), det.get("class_name"))
    return attach_3d_boxes(tracked, image, depth_map=depth_map, depth_available=depth_available)
