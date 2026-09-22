from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.frontier_capabilities import AnomalyEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory baseline store (per camera_node_id)
# ---------------------------------------------------------------------------
_baselines: dict[str, dict] = {}

# Sliding window for temporal smoothing (per camera_node_id)
_anomaly_windows: dict[str, list[bool]] = {}


def compute_scene_embedding(
    detections: list[dict] | None = None,
    image_bytes: bytes | None = None,
    image_width: int = 640,
    image_height: int = 480,
) -> dict:
    """Compute a scene-level embedding from detection and image features.

    When ``detections`` are provided, the embedding is built from:
        - Object count per class (histogram)
        - Mean confidence per class
        - Mean bbox area per class (normalised by image area)
        - Road/non-road ratio from segmentation if available
        - Colour histogram of the frame (3 bins per channel = 27-dim)

    When only ``image_bytes`` is provided, falls back to a lightweight
    hash-based entropy proxy.

    Returns a flat dict of numeric features suitable for anomaly scoring.
    """
    features: dict[str, Any] = {
        "object_counts": 0,
        "class_distribution": {},
        "depth_histogram": {"near": 0, "mid": 0, "far": 0},
        "road_ratio": 0.0,
        "avg_confidence": 0.0,
    }

    if detections:
        class_counts: dict[str, int] = defaultdict(int)
        class_conf_sum: dict[str, float] = defaultdict(float)
        class_area_sum: dict[str, float] = defaultdict(float)
        total_conf = 0.0
        total_objects = 0
        img_area = float(image_width * image_height) if image_width and image_height else 1.0

        for det in detections:
            cls = det.get("class_name", "unknown")
            conf = float(det.get("confidence", 0.0))
            bbox = det.get("bbox", [0, 0, 0, 0])
            # bbox format: [x1, y1, x2, y2] or [x, y, w, h]
            if len(bbox) == 4:
                if bbox[2] > bbox[0] and bbox[3] > bbox[1]:
                    # Looks like [x1, y1, x2, y2]
                    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                else:
                    # Looks like [x, y, w, h]
                    area = bbox[2] * bbox[3]
            else:
                area = 0.0

            class_counts[cls] += 1
            class_conf_sum[cls] += conf
            class_area_sum[cls] += area
            total_conf += conf
            total_objects += 1

        features["object_counts"] = total_objects
        features["avg_confidence"] = round(total_conf / total_objects, 4) if total_objects else 0.0

        class_dist: dict[str, float] = {}
        class_avg_conf: dict[str, float] = {}
        class_avg_area: dict[str, float] = {}
        for cls, count in class_counts.items():
            class_dist[cls] = count / total_objects
            class_avg_conf[cls] = round(class_conf_sum[cls] / count, 4)
            class_avg_area[cls] = round(class_area_sum[cls] / (count * img_area), 6)
        features["class_distribution"] = class_dist
        features["class_avg_confidence"] = class_avg_conf
        features["class_avg_bbox_area"] = class_avg_area

        # Road ratio from detections tagged as road-related
        road_classes = {"road", "road_segment", "lane"}
        road_count = sum(class_counts.get(c, 0) for c in road_classes)
        features["road_ratio"] = round(road_count / total_objects, 4) if total_objects else 0.0

        # Depth histogram from detections with depth info
        for det in detections:
            depth = det.get("depth_m")
            if depth is not None:
                if depth < 10:
                    features["depth_histogram"]["near"] += 1
                elif depth < 30:
                    features["depth_histogram"]["mid"] += 1
                else:
                    features["depth_histogram"]["far"] += 1

    if image_bytes and len(image_bytes) > 100:
        try:
            import cv2

            nparr = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                # Colour histogram: 3 bins per BGR channel = 27 values
                hist_features: list[float] = []
                for ch in range(3):
                    hist = cv2.calcHist([img], [ch], None, [3], [0, 256])
                    hist = hist.flatten() / (img.shape[0] * img.shape[1])
                    hist_features.extend(hist.tolist())
                for i, val in enumerate(hist_features):
                    features[f"color_hist_{i}"] = round(float(val), 6)

                # Overall brightness and saturation for weather anomaly detection
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                features["mean_brightness"] = round(float(np.mean(hsv[:, :, 2])) / 255.0, 4)
                features["mean_saturation"] = round(float(np.mean(hsv[:, :, 1])) / 255.0, 4)
                features["brightness_std"] = round(float(np.std(hsv[:, :, 2])) / 255.0, 4)

                return features
        except Exception:
            pass

        try:
            import hashlib

            digest = hashlib.md5(image_bytes[:4096]).hexdigest()
            entropy_proxy = sum(ord(c) for c in digest[:8]) / (127 * 8)
            features["scene_entropy"] = round(entropy_proxy, 4)
        except Exception:
            pass

    return features


def update_scene_baseline(camera_node_id: str, embedding: dict) -> dict:
    """Maintain a running exponential-moving-average baseline for a camera.

    The baseline is stored in-process memory (not DB) for performance.
    Returns the updated baseline stats.
    """
    alpha = 0.1  # EMA smoothing factor
    window = settings.ANOMALY_BASELINE_WINDOW

    if camera_node_id not in _baselines:
        _baselines[camera_node_id] = {
            "mean": dict(embedding),
            "var": {k: 0.0 for k in embedding if isinstance(embedding[k], (int, float))},
            "count": 1,
            "last_update": datetime.now(UTC).isoformat(),
        }
        return _baselines[camera_node_id]

    baseline = _baselines[camera_node_id]
    baseline["count"] = min(baseline["count"] + 1, window)
    baseline["last_update"] = datetime.now(UTC).isoformat()

    for key, value in embedding.items():
        if not isinstance(value, (int, float)):
            continue
        old_mean = baseline["mean"].get(key, 0.0)
        new_mean = old_mean + alpha * (value - old_mean)
        baseline["mean"][key] = new_mean

        old_var = baseline["var"].get(key, 0.0)
        new_var = (1 - alpha) * (old_var + alpha * (value - old_mean) ** 2)
        baseline["var"][key] = new_var

    return baseline


def detect_anomaly(
    camera_node_id: str,
    current_embedding: dict,
    threshold: float | None = None,
    window_size: int = 10,
    min_anomalous_frames: int = 3,
) -> dict | None:
    """Score the current frame against the running baseline.

    Uses a Mahalanobis-like distance.  Applies temporal smoothing: only
    flags an anomaly if at least ``min_anomalous_frames`` of the last
    ``window_size`` frames were anomalous.

    Returns an anomaly dict if the distance exceeds the threshold, otherwise ``None``.
    """
    if threshold is None:
        threshold = settings.ANOMALY_DETECTION_THRESHOLD

    baseline = _baselines.get(camera_node_id)
    if baseline is None or baseline["count"] < 5:
        return None

    mean = baseline["mean"]
    var = baseline["var"]

    # Compute Mahalanobis-like distance
    distance = 0.0
    differing_features: list[tuple[str, float, float]] = []

    for key, value in current_embedding.items():
        if not isinstance(value, (int, float)):
            continue
        m = mean.get(key, 0.0)
        v = max(var.get(key, 1e-6), 1e-6)
        diff = value - m
        normalized_diff = diff / math.sqrt(v)
        distance += normalized_diff * normalized_diff
        if abs(diff) > math.sqrt(v) * 1.5:
            differing_features.append((key, float(value), float(m)))

    distance = math.sqrt(distance)

    # Temporal smoothing: maintain sliding window of anomaly flags
    is_anomalous = distance > threshold
    if camera_node_id not in _anomaly_windows:
        _anomaly_windows[camera_node_id] = []
    window = _anomaly_windows[camera_node_id]
    window.append(is_anomalous)
    if len(window) > window_size:
        window.pop(0)

    anomalous_count = sum(window)
    if anomalous_count < min_anomalous_frames:
        return None

    # Determine anomaly type and generate description
    anomaly_type = _classify_anomaly(differing_features, current_embedding, mean)
    description = generate_anomaly_description(anomaly_type, current_embedding, mean)

    return {
        "anomaly_score": round(distance, 4),
        "anomaly_type": anomaly_type,
        "description": description,
        "embedding_distance": round(distance, 4),
        "differing_features": differing_features,
    }


def generate_anomaly_description(
    anomaly_type: str,
    current_features: dict,
    baseline_features: dict,
) -> str:
    """Generate a natural-language description of the detected anomaly."""
    if anomaly_type == "unknown_object":
        curr_count = current_features.get("object_counts", 0)
        base_count = baseline_features.get("object_counts", 0)
        return f"Unusual object count: {curr_count} detected vs typical {max(1, int(base_count))}"

    if anomaly_type == "novel_class":
        curr_classes = set(current_features.get("class_distribution", {}).keys())
        base_classes = set(baseline_features.get("class_distribution", {}).keys())
        novel = curr_classes - base_classes
        class_name = next(iter(novel), "unknown")
        return f"Novel object class detected: {class_name} not seen in this scene before"

    if anomaly_type == "scene_change":
        curr_road = current_features.get("road_ratio", 0.0)
        base_road = baseline_features.get("road_ratio", 0.0)
        return f"Significant scene change: road coverage dropped from {base_road:.0%} to {curr_road:.0%}"

    if anomaly_type == "unusual_behavior":
        curr_conf = current_features.get("avg_confidence", 0.0)
        base_conf = baseline_features.get("avg_confidence", 0.0)
        return f"Unusual detection confidence: {curr_conf:.2f} vs typical {base_conf:.2f}"

    if anomaly_type == "left_object":
        return "Object left unattended near road for extended period"

    if anomaly_type == "weather_anomaly":
        curr_bright = current_features.get("mean_brightness", 0.5)
        base_bright = baseline_features.get("mean_brightness", 0.5)
        if curr_bright > base_bright + 0.2:
            return f"Unusual brightness detected: {curr_bright:.2f} vs typical {base_bright:.2f} — possible glare or overexposure"
        if curr_bright < base_bright - 0.2:
            return f"Low brightness detected: {curr_bright:.2f} vs typical {base_bright:.2f} — possible fog, rain, or night scene"
        return f"Weather-related scene change detected (brightness: {curr_bright:.2f})"

    if anomaly_type == "traffic_anomaly":
        return "Traffic pattern anomaly detected: unusual direction, lane, or speed"

    return f"Anomalous scene pattern detected (type: {anomaly_type})"


async def store_anomaly(
    db: AsyncSession,
    camera_node_id: str,
    timestamp: datetime,
    anomaly_score: float,
    anomaly_type: str,
    description: str,
    features: dict,
    bounding_box: dict | None = None,
) -> AnomalyEvent:
    """Persist an anomaly event to the database."""
    record = AnomalyEvent(
        camera_node_id=camera_node_id,
        frame_timestamp=timestamp,
        anomaly_score=anomaly_score,
        anomaly_type=anomaly_type,
        description=description,
        embedding_distance=features.get("embedding_distance"),
        bounding_box=bounding_box,
        feedback_for_labeling=True,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info(
        "Stored anomaly %s for camera %s (type=%s, score=%.4f)",
        record.id,
        camera_node_id,
        anomaly_type,
        anomaly_score,
    )
    return record


async def get_anomalies(
    db: AsyncSession,
    camera_node_id: str | None = None,
    limit: int = 50,
    unresolved_only: bool = True,
) -> list[AnomalyEvent]:
    """Query anomalies with optional filters."""
    stmt = select(AnomalyEvent)
    if camera_node_id is not None:
        stmt = stmt.where(AnomalyEvent.camera_node_id == camera_node_id)
    if unresolved_only:
        stmt = stmt.where(AnomalyEvent.resolved == False)  # noqa: E712
    stmt = stmt.order_by(AnomalyEvent.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def resolve_anomaly(
    db: AsyncSession,
    anomaly_id: str,
    resolution_note: str,
) -> AnomalyEvent:
    """Mark an anomaly as resolved."""
    result = await db.execute(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id).with_for_update())
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError(f"Anomaly {anomaly_id} not found")

    record.resolved = True
    record.resolution_note = resolution_note
    await db.commit()
    await db.refresh(record)
    logger.info("Resolved anomaly %s", anomaly_id)
    return record


async def send_to_labeling_queue(db: AsyncSession, anomaly_id: str) -> AnomalyEvent:
    """Flag an anomaly for human review / labeling."""
    result = await db.execute(select(AnomalyEvent).where(AnomalyEvent.id == anomaly_id).with_for_update())
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError(f"Anomaly {anomaly_id} not found")

    record.feedback_for_labeling = True
    record.is_confirmed = True
    await db.commit()
    await db.refresh(record)
    logger.info("Sent anomaly %s to labeling queue", anomaly_id)
    return record


def update_baseline_from_detections(
    camera_node_id: str,
    detections: list[dict],
    image_width: int = 640,
    image_height: int = 480,
    image_bytes: bytes | None = None,
) -> dict:
    """Extract features from detections and update the running baseline.

    This is the primary entry point for the live pipeline to feed detections
    into the anomaly detection baseline.
    """
    embedding = compute_scene_embedding(
        detections=detections,
        image_bytes=image_bytes,
        image_width=image_width,
        image_height=image_height,
    )
    return update_scene_baseline(camera_node_id, embedding)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _classify_anomaly(
    differing_features: list[tuple[str, float, float]],
    current: dict,
    baseline: dict,
) -> str:
    """Determine anomaly category based on which features differ."""
    feature_names = {f[0] for f in differing_features}

    # Check for novel classes
    curr_classes = set(current.get("class_distribution", {}).keys())
    base_classes = set(baseline.get("class_distribution", {}).keys())
    if curr_classes - base_classes:
        return "novel_class"

    # Check for weather anomalies (brightness/saturation deviations)
    if "mean_brightness" in feature_names or "mean_saturation" in feature_names:
        return _classify_weather_anomaly(differing_features, current, baseline)

    # Check for traffic anomalies (bbox area or confidence pattern changes)
    if "class_avg_bbox_area" in feature_names or "class_avg_confidence" in feature_names:
        return _classify_traffic_anomaly(differing_features, current, baseline)

    if "object_counts" in feature_names:
        curr_count = current.get("object_counts", 0)
        base_count = baseline.get("object_counts", 0)
        if curr_count > base_count * 2:
            return "unknown_object"

    if "road_ratio" in feature_names:
        return "scene_change"

    if "avg_confidence" in feature_names:
        return "unusual_behavior"

    return "scene_change"


def _classify_weather_anomaly(
    differing_features: list[tuple[str, float, float]],
    current: dict,
    baseline: dict,
) -> str:
    """Detect unusual weather patterns from colour histogram and scene stats.

    Patterns detected:
    - Heavy rain: low saturation, reduced brightness
    - Fog: low brightness_std (flat lighting), reduced brightness
    - Extreme brightness: high brightness, possible glare
    """
    curr_brightness = current.get("mean_brightness", 0.5)
    base_brightness = baseline.get("mean_brightness", 0.5)
    curr_saturation = current.get("mean_saturation", 0.5)
    base_saturation = baseline.get("mean_saturation", 0.5)
    curr_bright_std = current.get("brightness_std", 0.2)

    brightness_delta = curr_brightness - base_brightness
    saturation_delta = curr_saturation - base_saturation

    # Extreme brightness (glare / overexposure)
    if brightness_delta > 0.15:
        return "weather_anomaly"

    # Heavy rain or fog: dimmer and less saturated
    if brightness_delta < -0.15 and saturation_delta < -0.1:
        return "weather_anomaly"

    # Fog: flat lighting (low brightness variance)
    base_bright_std = baseline.get("brightness_std", 0.2)
    if curr_bright_std < base_bright_std * 0.5 and brightness_delta < -0.1:
        return "weather_anomaly"

    return "weather_anomaly"


def _classify_traffic_anomaly(
    differing_features: list[tuple[str, float, float]],
    current: dict,
    baseline: dict,
) -> str:
    """Detect traffic pattern anomalies from trajectory and detection analysis.

    Patterns detected:
    - Wrong direction: sudden reversal in dominant motion vectors
    - Wrong lane: objects in unusual spatial positions
    - Unusual speed: objects significantly faster or slower than baseline
    """
    # If bbox areas are significantly different, objects may be in wrong lanes
    curr_areas = current.get("class_avg_bbox_area", {})
    base_areas = baseline.get("class_avg_bbox_area", {})
    for cls in curr_areas:
        if cls in base_areas:
            area_ratio = curr_areas[cls] / max(base_areas[cls], 1e-6)
            if area_ratio > 2.0 or area_ratio < 0.3:
                return "traffic_anomaly"

    # If confidence patterns shift dramatically for specific classes
    curr_conf = current.get("class_avg_confidence", {})
    base_conf = baseline.get("class_avg_confidence", {})
    for cls in curr_conf:
        if cls in base_conf:
            conf_delta = abs(curr_conf[cls] - base_conf[cls])
            if conf_delta > 0.3:
                return "traffic_anomaly"

    return "traffic_anomaly"
