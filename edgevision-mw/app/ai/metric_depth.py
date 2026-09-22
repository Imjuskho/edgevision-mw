"""Metric depth calibration from the flat-ground pinhole camera model.

The monocular ONNX model yields *relative* depth (normalized to ``[0, 1]``).
This module converts pixel rows to physical meters using the classic
ground-plane relation ``z = (h * f) / (row - horizon)`` for a camera mounted at
height ``h`` with vertical focal length ``f`` (pixels).  Distances derived this
way are quality-tagged as ``metric_ground_plane`` and feed both 3D boxes and the
perception event engine's ``distance`` rule.

Flat-ground assumptions and their limits (N7):
- The camera is mounted at ``DEFAULT_CAMERA_HEIGHT_M`` (1.5 m) above a flat,
  level ground plane.  Real deployments with hilly terrain, pitch/roll, or
  non-vertical camera mounts violate this and produce biased distances.
- ``DEFAULT_FOCAL_LENGTH_PX`` (700 px) is a generic estimate; calibration errors
  scale distance linearly (10% focal error -> ~10% distance error).
- ``DEFAULT_HORIZON_FRACTION`` (0.35) places the vanishing row at 35% of image
  height; an incorrect horizon shifts the inverse relationship and is the single
  largest error source at long range.
- Outputs must be consumed with their ``distance_quality`` tag; anything not
  tagged ``metric_ground_plane`` is unknown and must not be used for safety.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.metric_depth")

DEFAULT_CAMERA_HEIGHT_M = 1.5
DEFAULT_FOCAL_LENGTH_PX = 700.0
DEFAULT_HORIZON_FRACTION = 0.35

METRIC_QUALITY = "metric_ground_plane"
UNKNOWN_QUALITY = "below_horizon_unknown"


@dataclass(frozen=True)
class CameraCalibration:
    """Camera geometry used for the flat-ground metric conversion."""

    height_m: float = DEFAULT_CAMERA_HEIGHT_M
    focal_length_px: float = DEFAULT_FOCAL_LENGTH_PX
    horizon_fraction: float = DEFAULT_HORIZON_FRACTION
    principal_point_y: float | None = None
    principal_point_x: float | None = None

    def horizon_row(self, image_height: int) -> float:
        if self.principal_point_y is not None:
            return float(self.principal_point_y)
        return float(self.horizon_fraction * image_height)


def ground_plane_distance_m(
    row: float,
    image_height: int,
    calibration: CameraCalibration | None = None,
) -> float:
    """Metric distance (meters) to the flat-ground point imaged at ``row``.

    Returns ``inf`` when the row is at or above the horizon (no ground contact).
    """
    cal = calibration or CameraCalibration()
    horizon = cal.horizon_row(image_height)
    if row <= horizon:
        return float("inf")
    return (cal.height_m * cal.focal_length_px) / (row - horizon)


def metric_depth_map(
    image_shape: tuple[int, int],
    calibration: CameraCalibration | None = None,
) -> np.ndarray:
    """Full-frame metric depth map (meters) under the flat-ground assumption.

    Each column carries the same row-based ground distance.  Rows at or above
    the horizon are zero (unknown).
    """
    cal = calibration or CameraCalibration()
    h, w = image_shape[:2]
    rows = np.arange(h, dtype=np.float32)
    horizon = cal.horizon_row(h)
    below = rows > horizon
    ground = np.zeros(h, dtype=np.float32)
    if below.any():
        ground[below] = (cal.height_m * cal.focal_length_px) / (rows[below] - horizon)
    return np.broadcast_to(ground[:, np.newaxis], (h, w)).copy()


def _coerce_bbox(bbox: list[float], image_shape: tuple[int, int]) -> tuple[float, float, float, float]:
    """Return normalized ``(x1, y1, x2, y2)`` from pixel xyxy or normalized xywh."""
    h, w = image_shape[:2]
    vals = [float(v) for v in (bbox or [])[:4]]
    if len(vals) < 4:
        return (0.0, 0.0, 1.0, 1.0)
    x1, y1, x2, y2 = vals
    if max(x1, y1, x2, y2) > 1.0:
        return (x1 / w, y1 / h, x2 / w, y2 / h)
    return (x1, y1, x1 + x2, y1 + y2)


def metric_distance_at_bbox(
    bbox: list[float],
    image_shape: tuple[int, int],
    calibration: CameraCalibration | None = None,
) -> tuple[float, str]:
    """Metric distance (meters) to the ground contact of a detection bbox.

    The bbox bottom-center row is treated as the object's ground contact point.
    Returns ``(meters, quality)`` where quality is ``metric_ground_plane`` when
    the contact row is below the horizon and ``below_horizon_unknown`` otherwise.
    """
    cal = calibration or CameraCalibration()
    h, _ = image_shape[:2]
    _, _, _, y2 = _coerce_bbox(bbox, image_shape)
    contact_row = max(0.0, y2 * h - 1.0)
    horizon = cal.horizon_row(h)
    if contact_row <= horizon:
        return float("inf"), UNKNOWN_QUALITY
    meters = (cal.height_m * cal.focal_length_px) / (contact_row - horizon)
    return meters, METRIC_QUALITY


def attach_metric_depth(
    detections: list[dict],
    image_shape: tuple[int, int],
    calibration: CameraCalibration | None = None,
) -> list[dict]:
    """Attach ``distance_m``/``distance_quality``/``depth_units`` to detections."""
    if not detections:
        return detections
    cal = calibration or CameraCalibration()
    for det in detections:
        meters, quality = metric_distance_at_bbox(det.get("bbox", []), image_shape, cal)
        det["distance_m"] = round(meters, 3) if np.isfinite(meters) else None
        det["distance_quality"] = quality
        det["depth_units"] = "meters"
    return detections
