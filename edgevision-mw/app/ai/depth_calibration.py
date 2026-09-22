"""Per-camera depth calibration for converting relative depth to metric meters.

Depth-Anything-V2 outputs relative depth on an arbitrary [0, 1] scale with no
fixed relationship to physical distance.  This module provides:

1. **Piecewise-linear calibration** — fit against 3+ known reference distances
   to handle the non-linearity common in relative-depth models (near-field and
   far-field can scale differently).
2. **Single-point linear calibration** — quick anchor from one known distance.
3. **Validation gate** — require measured error within tolerance at near/mid/far
   ranges before a camera is marked "calibrated."
4. **Drift detection** — compare current readings against stored reference
   objects to catch mounting shifts over time.

Design
------
- Calibration is per-camera (mounting-specific, not global).
- Stored as a serialisable dict for persistence in any backend (Redis, DB, file).
- Pure NumPy — no external optimisation dependencies.
- All distances in meters.  Relative depth is the model's normalised output.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.depth_calibration")

# Validation tolerances
_DEFAULT_TOLERANCE_NEAR_M = 0.5   # ±0.5 m at < 3 m
_DEFAULT_TOLERANCE_MID_M = 1.5    # ±1.5 m at 3–8 m
_DEFAULT_TOLERANCE_FAR_M = 3.0    # ±3.0 m at 8+ m
_DEFAULT_MAX_ERROR_PCT = 20.0     # 20% max relative error

# Drift detection
_DRIFT_WARN_THRESHOLD_PCT = 15.0
_DRIFT_FAIL_THRESHOLD_PCT = 25.0


# ---------------------------------------------------------------------------
# Calibration data structures
# ---------------------------------------------------------------------------

@dataclass
class CalibrationPoint:
    """A single calibration measurement: relative depth → known real distance."""

    relative_depth: float
    real_distance_m: float
    label: str = ""


@dataclass
class CameraDepthCalibration:
    """Per-camera depth calibration state.

    Supports two modes:
    - **linear**: single scale factor (``real_m = scale * relative_depth + offset``).
    - **piecewise**: piecewise-linear interpolation through 3+ calibration points.
    """

    camera_id: str
    mode: str = "uncalibrated"  # "uncalibrated" | "linear" | "piecewise"
    scale: float = 1.0
    offset: float = 0.0
    calibration_points: list[CalibrationPoint] = field(default_factory=list)
    calibrated_at: float = 0.0  # epoch timestamp
    validation_passed: bool = False
    validation_results: list[dict] = field(default_factory=list)
    tolerance_near_m: float = _DEFAULT_TOLERANCE_NEAR_M
    tolerance_mid_m: float = _DEFAULT_TOLERANCE_MID_M
    tolerance_far_m: float = _DEFAULT_TOLERANCE_FAR_M
    max_error_pct: float = _DEFAULT_MAX_ERROR_PCT
    drift_references: list[dict] = field(default_factory=list)
    last_drift_check: float = 0.0

    # --- Serialisation ---

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "mode": self.mode,
            "scale": self.scale,
            "offset": self.offset,
            "calibration_points": [
                {"relative_depth": p.relative_depth, "real_distance_m": p.real_distance_m, "label": p.label}
                for p in self.calibration_points
            ],
            "calibrated_at": self.calibrated_at,
            "validation_passed": self.validation_passed,
            "validation_results": self.validation_results,
            "tolerance_near_m": self.tolerance_near_m,
            "tolerance_mid_m": self.tolerance_mid_m,
            "tolerance_far_m": self.tolerance_far_m,
            "max_error_pct": self.max_error_pct,
            "drift_references": self.drift_references,
            "last_drift_check": self.last_drift_check,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CameraDepthCalibration:
        points = [
            CalibrationPoint(**p) for p in d.get("calibration_points", [])
        ]
        return cls(
            camera_id=d["camera_id"],
            mode=d.get("mode", "uncalibrated"),
            scale=d.get("scale", 1.0),
            offset=d.get("offset", 0.0),
            calibration_points=points,
            calibrated_at=d.get("calibrated_at", 0.0),
            validation_passed=d.get("validation_passed", False),
            validation_results=d.get("validation_results", []),
            tolerance_near_m=d.get("tolerance_near_m", _DEFAULT_TOLERANCE_NEAR_M),
            tolerance_mid_m=d.get("tolerance_mid_m", _DEFAULT_TOLERANCE_MID_M),
            tolerance_far_m=d.get("tolerance_far_m", _DEFAULT_TOLERANCE_FAR_M),
            max_error_pct=d.get("max_error_pct", _DEFAULT_MAX_ERROR_PCT),
            drift_references=d.get("drift_references", []),
            last_drift_check=d.get("last_drift_check", 0.0),
        )

    @property
    def is_calibrated(self) -> bool:
        return self.mode != "uncalibrated" and self.validation_passed


# ---------------------------------------------------------------------------
# Calibration computation
# ---------------------------------------------------------------------------

def compute_linear_calibration(points: list[CalibrationPoint]) -> tuple[float, float]:
    """Compute a single linear scale factor from calibration points.

    Uses least-squares fit: ``real_m = scale * relative_depth + offset``.

    Returns ``(scale, offset)``.  With a single point, offset is forced to 0.
    """
    if not points:
        return 1.0, 0.0

    if len(points) == 1:
        rd = points[0].relative_depth
        if abs(rd) < 1e-8:
            return 1.0, 0.0
        return points[0].real_distance_m / rd, 0.0

    xs = np.array([p.relative_depth for p in points], dtype=np.float64)
    ys = np.array([p.real_distance_m for p in points], dtype=np.float64)

    # Least-squares: y = scale * x + offset
    # Normal equations: [sum(x^2), sum(x); sum(x), n] [scale; offset] = [sum(x*y); sum(y)]
    n = len(xs)
    sum_x = float(xs.sum())
    sum_y = float(ys.sum())
    sum_xx = float((xs * xs).sum())
    sum_xy = float((xs * ys).sum())

    det = sum_xx * n - sum_x * sum_x
    if abs(det) < 1e-12:
        # Degenerate: all points at same relative depth
        return sum_y / max(sum_x, 1e-8), 0.0

    scale = (sum_xy * n - sum_x * sum_y) / det
    offset = (sum_xx * sum_y - sum_x * sum_xy) / det
    return float(scale), float(offset)


def compute_piecewise_calibration(
    points: list[CalibrationPoint],
) -> list[tuple[float, float, float]]:
    """Compute piecewise-linear segments from calibration points.

    Returns a list of ``(relative_depth_start, scale, offset)`` tuples,
    one per segment.  Segments are sorted by relative_depth ascending.
    """
    if len(points) < 2:
        return []

    sorted_pts = sorted(points, key=lambda p: p.relative_depth)
    segments = []
    for i in range(len(sorted_pts) - 1):
        rd0 = sorted_pts[i].relative_depth
        rd1 = sorted_pts[i + 1].relative_depth
        d0 = sorted_pts[i].real_distance_m
        d1 = sorted_pts[i + 1].real_distance_m

        if abs(rd1 - rd0) < 1e-8:
            scale = 0.0
        else:
            scale = (d1 - d0) / (rd1 - rd0)
        offset = d0 - scale * rd0
        segments.append((rd0, scale, offset))

    return segments


def calibrate_camera(
    camera_id: str,
    points: list[CalibrationPoint],
    *,
    prefer_piecewise: bool = True,
    min_points_piecewise: int = 3,
) -> CameraDepthCalibration:
    """Create or update a camera calibration from reference measurements.

    If ``prefer_piecewise`` is True and enough points are provided, a
    piecewise-linear fit is used (better for non-linear depth models).
    Otherwise a single linear scale is fitted.
    """
    cal = CameraDepthCalibration(camera_id=camera_id, calibration_points=points)
    cal.calibrated_at = time.time()

    if prefer_piecewise and len(points) >= min_points_piecewise:
        cal.mode = "piecewise"
        scale, offset = compute_linear_calibration(points)
        cal.scale = scale
        cal.offset = offset
    elif len(points) >= 1:
        cal.mode = "linear"
        scale, offset = compute_linear_calibration(points)
        cal.scale = scale
        cal.offset = offset
    else:
        cal.mode = "uncalibrated"
        return cal

    logger.info(
        "depth_calibration_computed",
        camera=camera_id,
        mode=cal.mode,
        n_points=len(points),
        scale=round(cal.scale, 4),
        offset=round(cal.offset, 4),
    )
    return cal


def relative_to_metric(
    relative_depth: float,
    calibration: CameraDepthCalibration,
) -> float | None:
    """Convert a single relative depth value to metric meters.

    Returns ``None`` when the camera is uncalibrated.
    """
    if calibration.mode == "uncalibrated":
        return None

    if calibration.mode == "piecewise" and calibration.calibration_points:
        sorted_pts = sorted(calibration.calibration_points, key=lambda p: p.relative_depth)
        segments = compute_piecewise_calibration(sorted_pts)
        if not segments:
            return calibration.scale * relative_depth + calibration.offset

        # Find the right segment
        for rd_start, scale, offset in segments:
            if relative_depth >= rd_start:
                last_scale, last_offset = scale, offset
        else:
            # Extrapolate from last segment
            return last_scale * relative_depth + last_offset

        # Interpolate within segment
        for i, (rd_start, scale, offset) in enumerate(segments):
            if i + 1 < len(segments):
                rd_end = segments[i + 1][0]
                if rd_start <= relative_depth < rd_end:
                    return scale * relative_depth + offset
            else:
                return scale * relative_depth + offset

    return calibration.scale * relative_depth + calibration.offset


def relative_to_metric_array(
    depth_map: np.ndarray,
    calibration: CameraDepthCalibration,
) -> np.ndarray | None:
    """Convert an entire relative depth map to metric meters.

    Returns ``None`` when the camera is uncalibrated.
    """
    if calibration.mode == "uncalibrated":
        return None

    if calibration.mode == "piecewise" and calibration.calibration_points:
        sorted_pts = sorted(calibration.calibration_points, key=lambda p: p.relative_depth)
        segments = compute_piecewise_calibration(sorted_pts)

        if segments:
            result = np.empty_like(depth_map, dtype=np.float64)
            for i, (rd_start, scale, offset) in enumerate(segments):
                if i + 1 < len(segments):
                    rd_end = segments[i + 1][0]
                    mask = (depth_map >= rd_start) & (depth_map < rd_end)
                else:
                    mask = depth_map >= rd_start
                result[mask] = scale * depth_map[mask] + offset
            return result.astype(np.float32)

    return (calibration.scale * depth_map + calibration.offset).astype(np.float32)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_calibration(
    calibration: CameraDepthCalibration,
    test_points: list[CalibrationPoint],
) -> CameraDepthCalibration:
    """Validate a calibration against measured test distances.

    Test points should span near (<3 m), mid (3-8 m), and far (8+ m) ranges.
    The camera is marked ``validation_passed`` only if all points are within
    their range-specific tolerance AND the overall error is below
    ``max_error_pct``.
    """
    if calibration.mode == "uncalibrated":
        calibration.validation_passed = False
        calibration.validation_results = [{"error": "camera not calibrated"}]
        return calibration

    results = []
    all_pass = True

    for tp in test_points:
        predicted = relative_to_metric(tp.relative_depth, calibration)
        if predicted is None:
            results.append({
                "label": tp.label,
                "real_m": tp.real_distance_m,
                "predicted_m": None,
                "error_m": None,
                "error_pct": None,
                "passed": False,
            })
            all_pass = False
            continue

        error_m = abs(predicted - tp.real_distance_m)
        error_pct = (error_m / max(tp.real_distance_m, 0.01)) * 100.0

        # Range-specific tolerance
        if tp.real_distance_m < 3.0:
            tolerance = calibration.tolerance_near_m
        elif tp.real_distance_m < 8.0:
            tolerance = calibration.tolerance_mid_m
        else:
            tolerance = calibration.tolerance_far_m

        passed = error_m <= tolerance and error_pct <= calibration.max_error_pct
        if not passed:
            all_pass = False

        results.append({
            "label": tp.label,
            "real_m": round(tp.real_distance_m, 3),
            "predicted_m": round(predicted, 3),
            "error_m": round(error_m, 3),
            "error_pct": round(error_pct, 1),
            "tolerance_m": round(tolerance, 3),
            "passed": passed,
        })

    calibration.validation_results = results
    calibration.validation_passed = all_pass

    logger.info(
        "depth_calibration_validated",
        camera=calibration.camera_id,
        n_points=len(test_points),
        passed=all_pass,
        max_error_pct=round(max((r.get("error_pct") or 0) for r in results), 1),
    )
    return calibration


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

def add_drift_reference(
    calibration: CameraDepthCalibration,
    relative_depth: float,
    real_distance_m: float,
    label: str = "reference",
) -> None:
    """Store a reference point for ongoing drift detection."""
    calibration.drift_references.append({
        "relative_depth": relative_depth,
        "real_distance_m": real_distance_m,
        "label": label,
        "recorded_at": time.time(),
    })


def check_drift(
    calibration: CameraDepthCalibration,
    current_relative_depth: float,
    reference_label: str | None = None,
) -> dict[str, Any]:
    """Check if a current reading has drifted from a stored reference.

    Returns ``{"drifted": bool, "status": "ok"|"warn"|"fail", "details": ...}``.
    """
    if not calibration.drift_references:
        return {"drifted": False, "status": "ok", "details": "no_references"}

    calibration.last_drift_check = time.time()

    # Find matching reference
    ref = None
    for r in calibration.drift_references:
        if reference_label and r["label"] == reference_label:
            ref = r
            break
    if ref is None:
        ref = calibration.drift_references[-1]  # use latest

    expected_m = ref["real_distance_m"]
    predicted_m = relative_to_metric(current_relative_depth, calibration)
    if predicted_m is None:
        return {"drifted": False, "status": "ok", "details": "uncalibrated"}

    error_pct = abs(predicted_m - expected_m) / max(expected_m, 0.01) * 100.0

    if error_pct >= _DRIFT_FAIL_THRESHOLD_PCT:
        status = "fail"
        drifted = True
    elif error_pct >= _DRIFT_WARN_THRESHOLD_PCT:
        status = "warn"
        drifted = True
    else:
        status = "ok"
        drifted = False

    return {
        "drifted": drifted,
        "status": status,
        "reference_label": ref["label"],
        "expected_m": round(expected_m, 3),
        "predicted_m": round(predicted_m, 3),
        "error_pct": round(error_pct, 1),
    }


# ---------------------------------------------------------------------------
# In-memory per-camera store (process-wide singleton)
# ---------------------------------------------------------------------------

_calibrations: dict[str, CameraDepthCalibration] = {}
_store_lock_events: list[str] = []


def store_calibration(calibration: CameraDepthCalibration) -> None:
    """Store a calibration in the process-wide in-memory store."""
    _calibrations[camera_id_key(calibration.camera_id)] = calibration


def load_calibration(camera_id: str) -> CameraDepthCalibration:
    """Load a calibration from the in-memory store, or return uncalibrated."""
    key = camera_id_key(camera_id)
    if key in _calibrations:
        return _calibrations[key]
    return CameraDepthCalibration(camera_id=camera_id)


def camera_id_key(camera_id: str) -> str:
    return camera_id.strip().lower()
