"""Monocular 3D bounding box estimation with optional depth map."""

from __future__ import annotations

import math

import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.mono_3d")

_3D_CLASSES = frozenset(
    {
        "car",
        "truck",
        "bus",
        "motorcycle",
        "bicycle",
        "person",
        "car_private",
        "truck_freight",
        "minibus",
        "motorcycle_kabaza",
        "bicycle_private",
        "pedestrian_roadside",
    }
)

_CLASS_PRIORS: dict[str, tuple[float, float, float]] = {
    "car": (4.5, 1.8, 1.5),
    "car_private": (4.5, 1.8, 1.5),
    "truck": (8.0, 2.5, 3.0),
    "truck_freight": (8.0, 2.5, 3.0),
    "bus": (12.0, 2.5, 3.2),
    "minibus": (6.0, 2.0, 2.5),
    "motorcycle": (2.0, 0.8, 1.2),
    "motorcycle_kabaza": (2.0, 0.8, 1.2),
    "bicycle": (1.8, 0.6, 1.1),
    "bicycle_private": (1.8, 0.6, 1.1),
    "person": (0.5, 0.5, 1.7),
    "pedestrian_roadside": (0.5, 0.5, 1.7),
}

_DEFAULT_PRIOR = (2.0, 1.0, 1.5)
_FOCAL_LENGTH_PX = 700.0
_MAX_YAW_DEG = 60.0


def _class_key(class_name: str, taxonomy_label: str | None) -> str:
    return taxonomy_label or class_name


def _estimate_yaw(
    bbox_xywh: list[float],
    depth_map=None,
    *,
    depth_available: bool = False,
) -> tuple[float, str]:
    """Estimate yaw in radians from depth gradient or aspect ratio."""
    x, y, w, h = bbox_xywh
    aspect = w / h if h > 0 else 1.0

    if depth_map is not None and depth_available:
        try:
            img_h, img_w = depth_map.shape[:2]
            x1 = max(0, int(x * img_w))
            y1 = max(0, int(y * img_h))
            x2 = min(img_w, int((x + w) * img_w))
            y2 = min(img_h, int((y + h) * img_h))
            if x2 > x1 + 2 and y2 > y1 + 2:
                region = depth_map[y1:y2, x1:x2]
                gx = np.gradient(region, axis=1)
                gy = np.gradient(region, axis=0)
                mean_gx = float(np.mean(gx))
                mean_gy = float(np.mean(gy))
                if abs(mean_gx) > 1e-4 or abs(mean_gy) > 1e-4:
                    yaw_rad = math.atan2(mean_gx, -mean_gy)
                    max_rad = math.radians(_MAX_YAW_DEG)
                    yaw_rad = max(-max_rad, min(max_rad, yaw_rad))
                    return yaw_rad, "depth_gradient"
        except Exception:
            pass

    # Aspect-ratio heuristic: wide boxes likely side-on
    if aspect > 1.4:
        yaw_rad = math.radians(min(_MAX_YAW_DEG, (aspect - 1.0) * 30.0))
        return yaw_rad, "aspect_ratio"
    if aspect < 0.7:
        yaw_rad = -math.radians(min(_MAX_YAW_DEG, (1.0 / aspect - 1.0) * 30.0))
        return yaw_rad, "aspect_ratio"
    return 0.0, "axis_aligned"


def _rotate_corners_xz(
    corners: list[list[float]],
    cx: float,
    cy: float,
    yaw: float,
) -> list[list[float]]:
    """Rotate bottom/top face corners around vertical axis (yaw in image x-z plane)."""
    cos_y = math.cos(yaw)
    sin_y = math.sin(yaw)
    rotated = []
    for corner in corners:
        px, py, pz = corner
        dx = px - cx
        dz = pz - (corners[0][2] if corners else 0.5)
        rx = cx + dx * cos_y - dz * sin_y
        rz = (corners[0][2] if corners else 0.5) + dx * sin_y + dz * cos_y
        rotated.append([rx, py, rz])
    return rotated


def estimate_3d(
    bbox_xywh: list[float],
    class_name: str,
    image_shape: tuple[int, int],
    depth_map=None,
    taxonomy_label: str | None = None,
    *,
    depth_available: bool = False,
    metric_distance_m: float | None = None,
    metric_distance_quality: str | None = None,
    depth_calibration=None,
    camera_id: str | None = None,
) -> dict | None:
    """Estimate a 3D box from a 2D bbox, class prior, and optional depth map.

    When ``depth_calibration`` (a ``CameraDepthCalibration``) is provided and
    calibrated, the ONNX relative depth is converted to metric meters using the
    stored scale factor — overriding the hardcoded ``2.0 + raw * 20.0`` mapping.
    """
    key = _class_key(class_name, taxonomy_label)
    if key not in _3D_CLASSES and class_name not in _3D_CLASSES:
        return None

    prior_key = key if key in _CLASS_PRIORS else class_name
    length_m, width_m, height_m = _CLASS_PRIORS.get(prior_key, _DEFAULT_PRIOR)

    img_h, img_w = image_shape[:2]
    x, y, w, h = bbox_xywh
    cx = x + w / 2
    cy = y + h / 2

    pixel_height = h * img_h
    if pixel_height <= 1:
        return None
    scale = (height_m * _FOCAL_LENGTH_PX) / pixel_height

    depth = 5.0
    distance_quality = "heuristic_vertical"
    depth_source = "heuristic"
    if metric_distance_m is not None and math.isfinite(metric_distance_m):
        depth = float(metric_distance_m)
        distance_quality = metric_distance_quality or "metric_ground_plane"
        depth_source = "metric_ground_plane"
    elif depth_map is not None:
        try:
            from app.ai.depth_estimator import get_depth_estimator

            raw_depth, depth_quality_raw = get_depth_estimator().depth_at_bbox(depth_map, bbox_xywh)
            # Use calibration if available, otherwise fall back to linear mapping
            if depth_calibration is not None and depth_calibration.is_calibrated:
                from app.ai.depth_calibration import relative_to_metric

                calibrated_m = relative_to_metric(raw_depth, depth_calibration)
                if calibrated_m is not None and math.isfinite(calibrated_m) and calibrated_m > 0:
                    depth = calibrated_m
                    distance_quality = f"depth_calibrated_{depth_calibration.mode}"
                    depth_source = "depth_calibrated"
                else:
                    depth = 2.0 + raw_depth * 20.0
                    distance_quality = depth_quality_raw
                    depth_source = "depth_onnx_uncalibrated"
            else:
                depth = 2.0 + raw_depth * 20.0
                distance_quality = depth_quality_raw
                depth_source = "depth_onnx_uncalibrated"
        except Exception:
            depth = 2.0 + cy * 15.0
            distance_quality = "heuristic_vertical"
    else:
        depth = 2.0 + cy * 15.0
        depth_source = "heuristic_vertical"

    yaw, yaw_source = _estimate_yaw(bbox_xywh, depth_map, depth_available=depth_available)

    half_l = (length_m * _FOCAL_LENGTH_PX) / (2 * depth * img_w)
    half_w = (width_m * _FOCAL_LENGTH_PX) / (2 * depth * img_w)
    half_h = (height_m * _FOCAL_LENGTH_PX) / (2 * depth * img_h)

    z_base = depth
    z_top = depth + half_h * 2

    corners = [
        [cx - half_l, cy + half_h, z_base],
        [cx + half_l, cy + half_h, z_base],
        [cx + half_l, cy - half_h, z_base],
        [cx - half_l, cy - half_h, z_base],
        [cx - half_l, cy + half_h, z_top],
        [cx + half_l, cy + half_h, z_top],
        [cx + half_l, cy - half_h, z_top],
        [cx - half_l, cy - half_h, z_top],
    ]

    if abs(yaw) > 1e-4:
        corners = _rotate_corners_xz(corners, cx, cy, yaw)

    if metric_distance_m is not None and math.isfinite(metric_distance_m):
        limitation = "metric_depth_ground_plane"
        if depth_available:
            limitation = "metric_depth_ground_plane,depth_onnx_yaw_estimated"
    elif depth_source == "depth_calibrated":
        limitation = "depth_calibrated"
        if depth_available:
            limitation = "depth_calibrated,depth_onnx_yaw_estimated"
    else:
        limitation = "depth_onnx_yaw_estimated" if depth_available else "heuristic_prior_no_depth"

    return {
        "corners": [[round(c[0], 4), round(c[1], 4), round(c[2], 4)] for c in corners],
        "dimensions": [round(length_m, 2), round(width_m, 2), round(height_m, 2)],
        "yaw": round(yaw, 4),
        "yaw_source": yaw_source,
        "distance_quality": distance_quality,
        "distance_m": round(depth, 3),
        "depth_source": depth_source,
        "limitation": limitation,
        "depth_available": depth_available,
    }


def _as_list4(bbox) -> list[float]:
    """Coerce bbox (list or ndarray) to a 4-element float list."""
    if bbox is None:
        return []
    if hasattr(bbox, "tolist"):
        bbox = bbox.tolist()
    return [float(v) for v in bbox[:4]]


def _bbox_to_normalized_xywh(bbox, shape: tuple[int, ...]) -> list[float] | None:
    """Convert pixel xyxy or xywh (or normalized xywh) to normalized xywh."""
    values = _as_list4(bbox)
    if len(values) < 4:
        return None

    h, w = shape[:2]
    x, y, third, fourth = values

    # Pixel-space xyxy from tracker: x2 > x1 and values exceed 1.0
    if third > x and (third > 1.0 or fourth > 1.0 or x > 1.0 or y > 1.0):
        x1, y1, x2, y2 = x, y, third, fourth
        return [x1 / w, y1 / h, (x2 - x1) / w, (y2 - y1) / h]

    # Pixel-space xywh
    if third > 1.0 or fourth > 1.0:
        return [x / w, y / h, third / w, fourth / h]

    # Already normalized xywh
    return [x, y, third, fourth]


def attach_3d_boxes(
    detections: list[dict],
    image,
    depth_map=None,
    *,
    depth_available: bool = False,
    depth_calibration=None,
    camera_id: str | None = None,
) -> list[dict]:
    """Attach ``bbox_3d`` to each detection when class is in ``_3D_CLASSES``.

    When ``depth_calibration`` is provided and calibrated, ONNX relative depth
    is converted to metric meters using the per-camera calibration before
    generating 3D cuboids.
    """
    if not detections:
        return detections

    shape = image.shape if hasattr(image, "shape") else (480, 640)
    enriched = []
    for det in detections:
        d = dict(det)
        xywh = _bbox_to_normalized_xywh(d.get("bbox"), shape)
        if xywh is None:
            enriched.append(d)
            continue

        box_3d = estimate_3d(
            xywh,
            d.get("class_name", ""),
            shape,
            depth_map=depth_map,
            taxonomy_label=d.get("taxonomy_label"),
            depth_available=depth_available,
            metric_distance_m=d.get("distance_m"),
            metric_distance_quality=d.get("distance_quality"),
            depth_calibration=depth_calibration,
            camera_id=camera_id,
        )
        if box_3d:
            d["bbox_3d"] = box_3d
        enriched.append(d)
    return enriched
