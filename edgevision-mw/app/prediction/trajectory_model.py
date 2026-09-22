"""F3 Predictive Trajectory Modeling.

Consumes ``TrackEventState.trajectory`` (a ``deque`` of
``centroid_x, centroid_y, timestamp`` tuples, max 32 entries) and projects
forward 1-5 seconds using:

* **Physics-based baseline** — constant-velocity (CV) and constant-acceleration
  (CA) models, identical kinematics to ``app.services.trajectory_prediction``
  but operating directly on the pixel-coordinate ring buffer.
* **Learned sequence model** — a small numpy-only LSTM that can be loaded
  behind the ``LEARNED_TRAJECTORY_MODEL`` feature flag.  No PyTorch/TensorFlow
  dependency at runtime; weights are serialized numpy ``.npz`` files.

Predicted polylines are fused with the road/curb segmentation mask (from
``app.ai.road_segmenter``) to compute *predicted time-to-road-intersection*
(P-TTI).  Alerts are confidence-gated: a ``RuleTrigger`` is only emitted
when the intersection confidence exceeds the per-rule threshold.

Extends the ``EventRule`` schema in ``app.ai.events`` with a new
``predictive_intersection`` rule type.
"""

from __future__ import annotations

import logging
import math
import os
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.ai.events import (
    CONFIDENCE_DROP,
    DISTANCE,
    DWELL,
    PRESENCE,
    EventRule,
    PerceptionEvent,
    TrackEventState,
    VALID_RULE_TYPES,
    _fire,
)
from app.core.config import settings

# frozen=True is required because EventRule is frozen.
FrozenDC = lambda cls: dataclass(cls, frozen=True)

logger = logging.getLogger(__name__)

# New rule type constant
PREDICTIVE_INTERSECTION = "predictive_intersection"
VALID_RULE_TYPES_WITH_PREDICTION = frozenset(
    {DWELL, PRESENCE, CONFIDENCE_DROP, DISTANCE, PREDICTIVE_INTERSECTION}
)

# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

_LEARNED_MODEL_FLAG: bool = (
    os.environ.get("LEARNED_TRAJECTORY_MODEL", "false").lower()
    in ("1", "true", "yes", "on")
)


def _learned_model_enabled() -> bool:
    return _LEARNED_MODEL_FLAG


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PredictedPoint:
    """A single point on a predicted trajectory."""

    t: float
    x: float
    y: float
    confidence: float = 1.0


@dataclass(frozen=True)
class PredictiveIntersectionRule(EventRule):
    """Extended EventRule for predictive-intersection evaluation.

    Adds ``confidence_threshold`` for confidence-gated alerting and
    ``prediction_horizon`` to cap the forward projection window.
    """

    confidence_threshold: float = 0.5
    prediction_horizon: float = 5.0
    min_trajectory_points: int = 4

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_type", PREDICTIVE_INTERSECTION)

    def to_dict(self) -> dict:  # type: ignore[override]
        base = super().to_dict()
        base["rule_type"] = PREDICTIVE_INTERSECTION
        base["confidence_threshold"] = self.confidence_threshold
        base["prediction_horizon"] = self.prediction_horizon
        base["min_trajectory_points"] = self.min_trajectory_points
        return base

    @classmethod
    def from_dict(cls, raw: dict) -> "PredictiveIntersectionRule":
        return cls(
            rule_id=str(raw.get("rule_id", "pred_intersection")),
            rule_type=PREDICTIVE_INTERSECTION,
            name=str(raw.get("name", "Predictive Road Intersection")),
            enabled=bool(raw.get("enabled", True)),
            class_names=tuple(
                str(v) for v in (raw.get("class_names") or ())
            ),
            taxonomy_labels=tuple(
                str(v) for v in (raw.get("taxonomy_labels") or ())
            ),
            min_confidence=float(raw.get("min_confidence", 0.0)),
            confidence_threshold=float(raw.get("confidence_threshold", 0.5)),
            prediction_horizon=float(raw.get("prediction_horizon", 5.0)),
            min_trajectory_points=int(raw.get("min_trajectory_points", 4)),
            cooldown_seconds=float(raw.get("cooldown_seconds", 30.0)),
            auto_save=bool(raw.get("auto_save", True)),
            alert=bool(raw.get("alert", True)),
            pre_frames=int(raw.get("pre_frames", 6)),
            post_frames=int(raw.get("post_frames", 4)),
        )


# Register the new rule type in the valid set (patch at import time).
# This is intentional: downstream code that checks ``rule_type in VALID_RULE_TYPES``
# will now accept the new type.
try:
    import app.ai.events as _events_mod

    _events_mod.VALID_RULE_TYPES = VALID_RULE_TYPES_WITH_PREDICTION  # type: ignore[attr-defined]
except Exception:
    pass


@dataclass
class ConfidenceGatedAlert:
    """An alert that only fires when confidence >= threshold."""

    alert_id: str
    rule_id: str
    track_id: int
    predicted_tti: float
    confidence: float
    threshold: float
    trajectory: list[PredictedPoint]
    road_intersection_point: tuple[float, float] | None = None

    @property
    def should_fire(self) -> bool:
        return self.confidence >= self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule_id,
            "track_id": self.track_id,
            "predicted_tti": round(self.predicted_tti, 4),
            "confidence": round(self.confidence, 4),
            "threshold": round(self.threshold, 4),
            "should_fire": self.should_fire,
            "road_intersection_point": (
                {
                    "x": round(self.road_intersection_point[0], 4),
                    "y": round(self.road_intersection_point[1], 4),
                }
                if self.road_intersection_point
                else None
            ),
            "trajectory_length": len(self.trajectory),
        }


# ---------------------------------------------------------------------------
# Physics-based predictors
# ---------------------------------------------------------------------------


def _extract_positions(
    trajectory: deque,
) -> np.ndarray | None:
    """Extract an (N, 3) array of [x, y, t] from a TrackEventState trajectory deque.

    Returns None if fewer than 2 points are available.
    """
    if len(trajectory) < 2:
        return None
    pts = np.array(trajectory, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] < 3:
        return None
    return pts[:, :3]  # x, y, t


def predict_constant_velocity(
    positions: np.ndarray,
    horizons: list[float],
) -> list[PredictedPoint]:
    """Project forward using constant-velocity model.

    Args:
        positions: (N, 3) array of [x, y, t].
        horizons: seconds ahead to predict.

    Returns:
        List of PredictedPoint, one per horizon.
    """
    n = len(positions)
    # Use last two frames to estimate velocity
    dx = positions[-1, 0] - positions[-2, 0]
    dy = positions[-1, 1] - positions[-2, 1]
    dt = positions[-1, 2] - positions[-2, 2]
    if dt <= 0:
        dt = 1.0 / 30.0  # assume 30 fps fallback

    vx = dx / dt
    vy = dy / dt
    x0, y0 = positions[-1, 0], positions[-1, 1]

    results: list[PredictedPoint] = []
    base_confidence = max(0.1, 0.95 - 0.15 * (n / 32.0))
    for h in horizons:
        results.append(
            PredictedPoint(
                t=round(h, 3),
                x=round(x0 + vx * h, 4),
                y=round(y0 + vy * h, 4),
                confidence=round(base_confidence, 4),
            )
        )
    return results


def predict_constant_acceleration(
    positions: np.ndarray,
    horizons: list[float],
) -> list[PredictedPoint]:
    """Project forward using constant-acceleration model.

    Requires at least 3 points.  Falls back to CV if insufficient.
    """
    if len(positions) < 3:
        return predict_constant_velocity(positions, horizons)

    # Compute velocity at last two frames
    dt1 = positions[-1, 2] - positions[-2, 2]
    dt2 = positions[-2, 2] - positions[-3, 2]
    if dt1 <= 0:
        dt1 = 1.0 / 30.0
    if dt2 <= 0:
        dt2 = 1.0 / 30.0

    vx1 = (positions[-1, 0] - positions[-2, 0]) / dt1
    vy1 = (positions[-1, 1] - positions[-2, 1]) / dt1
    vx2 = (positions[-2, 0] - positions[-3, 0]) / dt2
    vy2 = (positions[-2, 1] - positions[-3, 1]) / dt2

    ax = (vx1 - vx2) / ((dt1 + dt2) / 2.0)
    ay = (vy1 - vy2) / ((dt1 + dt2) / 2.0)

    x0, y0 = positions[-1, 0], positions[-1, 1]
    n = len(positions)
    has_accel = abs(ax) > 0.5 or abs(ay) > 0.5
    base_confidence = max(0.1, 0.90 - 0.12 * (n / 32.0)) if has_accel else max(0.1, 0.95 - 0.15 * (n / 32.0))

    results: list[PredictedPoint] = []
    for h in horizons:
        cx = x0 + vx1 * h + 0.5 * ax * h * h
        cy = y0 + vy1 * h + 0.5 * ay * h * h
        results.append(
            PredictedPoint(
                t=round(h, 3),
                x=round(cx, 4),
                y=round(cy, 4),
                confidence=round(base_confidence, 4),
            )
        )
    return results


# ---------------------------------------------------------------------------
# Learned sequence model (numpy-only LSTM)
# ---------------------------------------------------------------------------


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))


def _tanh(x: np.ndarray) -> np.ndarray:
    return np.tanh(x)


class NumpyLSTMCell:
    """Minimal single-layer LSTM cell using only numpy.

    State size: 2 (x, y per direction) × 2 (hidden + cell) = 4 per hidden unit.
    """

    def __init__(self, input_dim: int, hidden_dim: int):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        # Combined weight matrix for all 4 gates: [input, forget, cell_candidate, output]
        fan_in = input_dim + hidden_dim
        scale = np.sqrt(2.0 / fan_in)
        self.W = np.random.randn(4 * hidden_dim, fan_in).astype(np.float64) * scale
        self.b = np.zeros(4 * hidden_dim, dtype=np.float64)
        # Initialize forget gate bias to 1.0 (common practice)
        self.b[hidden_dim : 2 * hidden_dim] = 1.0

    def forward(
        self, x: np.ndarray, h_prev: np.ndarray, c_prev: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Single time-step forward pass.

        Args:
            x: (input_dim,) input vector.
            h_prev: (hidden_dim,) previous hidden state.
            c_prev: (hidden_dim,) previous cell state.

        Returns:
            (h_new, c_new) each (hidden_dim,).
        """
        combined = np.concatenate([x, h_prev])
        gates = self.W @ combined + self.b
        i_g = _sigmoid(gates[: self.hidden_dim])
        f_g = _sigmoid(gates[self.hidden_dim : 2 * self.hidden_dim])
        c_cand = _tanh(gates[2 * self.hidden_dim : 3 * self.hidden_dim])
        o_g = _sigmoid(gates[3 * self.hidden_dim :])
        c_new = f_g * c_prev + i_g * c_cand
        h_new = o_g * _tanh(c_new)
        return h_new, c_new


class NumpyTrajectoryLSTM:
    """Small LSTM sequence model for trajectory prediction.

    Architecture:
        Input:  (x, y, dt) per timestep — 3 features
        LSTM:   1 layer, 32 hidden units
        Output: Linear projection -> 2 * horizon_count (x, y per horizon)

    Weights are loaded from a ``.npz`` file when available; otherwise
    random initialization is used (untrained baseline).
    """

    def __init__(
        self,
        input_dim: int = 3,
        hidden_dim: int = 32,
        seq_len: int = 32,
        num_horizons: int = 5,
    ):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.seq_len = seq_len
        self.num_horizons = num_horizons

        self.cell = NumpyLSTMCell(input_dim, hidden_dim)
        # Output head: hidden_dim -> 2 * num_horizons
        self.W_out = np.random.randn(2 * num_horizons, hidden_dim).astype(np.float64) * 0.01
        self.b_out = np.zeros(2 * num_horizons, dtype=np.float64)
        self._loaded = False

    def load_weights(self, path: str | None = None) -> bool:
        """Load pre-trained weights from a ``.npz`` file.

        Expected keys: ``W``, ``b`` (LSTM), ``W_out``, ``b_out`` (head).
        Returns True on success.
        """
        if path is None:
            path = os.environ.get("TRAJECTORY_LSTM_WEIGHTS", "")
        if not path or not os.path.isfile(path):
            return False
        try:
            data = np.load(path)
            self.cell.W = data["W"].astype(np.float64)
            self.cell.b = data["b"].astype(np.float64)
            self.W_out = data["W_out"].astype(np.float64)
            self.b_out = data["b_out"].astype(np.float64)
            self._loaded = True
            logger.info("trajectory_lstm_weights_loaded", path=path)
            return True
        except Exception as exc:
            logger.warning("trajectory_lstm_weights_failed", path=path, error=str(exc))
            return False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def predict(
        self,
        positions: np.ndarray,
        horizons: list[float],
    ) -> list[PredictedPoint]:
        """Run the LSTM over the trajectory and return predicted positions.

        Args:
            positions: (N, 3) array of [x, y, t].
            horizons: seconds ahead to predict.

        Returns:
            List of PredictedPoint.
        """
        n = len(positions)
        if n < 2:
            return predict_constant_velocity(positions, horizons)

        # Normalize timestamps relative to the first point
        t0 = positions[0, 2]
        ts = positions[:, 2] - t0

        # Build input features: (x, y, dt) where dt is inter-frame delta
        dx = np.diff(positions[:, 0])
        dy = np.diff(positions[:, 1])
        dt = np.diff(ts)
        dt = np.where(dt > 0, dt, 1.0 / 30.0)

        features = np.column_stack([
            positions[1:, 0],
            positions[1:, 1],
            dt,
        ]).astype(np.float64)  # (N-1, 3)

        # Normalize features for numerical stability
        mean = features.mean(axis=0, keepdims=True)
        std = features.std(axis=0, keepdims=True)
        std = np.where(std > 1e-6, std, 1.0)
        features_norm = (features - mean) / std

        # Run through LSTM
        h = np.zeros(self.hidden_dim, dtype=np.float64)
        c = np.zeros(self.hidden_dim, dtype=np.float64)
        for step in range(min(len(features_norm), self.seq_len)):
            h, c = self.cell.forward(features_norm[step], h, c)

        # Output projection
        raw_out = self.W_out @ h + self.b_out  # (2 * num_horizons,)
        xy_deltas = raw_out.reshape(self.num_horizons, 2)

        # Scale predictions back to real coordinates
        last_x, last_y = positions[-1, 0], positions[-1, 1]
        mean_x, mean_y = mean[0, 0], mean[0, 1]
        std_x, std_y = std[0, 0], std[0, 1]

        base_confidence = max(0.1, 0.85 - 0.10 * (n / 32.0))
        results: list[PredictedPoint] = []
        for i, h_ahead in enumerate(horizons):
            pred_x = last_x + xy_deltas[i, 0] * std_x + mean_x
            pred_y = last_y + xy_deltas[i, 1] * std_y + mean_y
            # Decay confidence for longer horizons
            conf = base_confidence * max(0.3, 1.0 - h_ahead * 0.12)
            results.append(
                PredictedPoint(
                    t=round(h_ahead, 3),
                    x=round(float(pred_x), 4),
                    y=round(float(pred_y), 4),
                    confidence=round(float(conf), 4),
                )
            )
        return results


# Singleton learned model instance
_learned_model: NumpyTrajectoryLSTM | None = None


def _get_learned_model() -> NumpyTrajectoryLSTM | None:
    global _learned_model
    if not _learned_model_enabled():
        return None
    if _learned_model is None:
        _learned_model = NumpyTrajectoryLSTM()
        _learned_model.load_weights()
    return _learned_model if _learned_model.is_loaded else None


# ---------------------------------------------------------------------------
# Road fusion: predicted time-to-road-intersection
# ---------------------------------------------------------------------------


def fuse_with_road_mask(
    predicted: list[PredictedPoint],
    road_mask: dict | None,
    lane_boundaries: list[dict] | None = None,
) -> tuple[bool, float | None, float, tuple[float, float] | None]:
    """Check whether a predicted trajectory crosses road geometry.

    Mirrors the logic in ``app.services.trajectory_prediction.check_road_intersection``
    but operates on ``PredictedPoint`` objects and returns the intersection
    coordinate for downstream alerting.

    Args:
        predicted: list of PredictedPoint along the predicted trajectory.
        road_mask: dict with ``bbox`` key (``min_x, max_x, min_y, max_y``)
            or ``polygons`` list of vertex lists.
        lane_boundaries: list of segment dicts with ``start``/``end`` keys.

    Returns:
        (will_intersect, time_to_intersection, confidence, intersection_xy)
    """
    if not predicted:
        return False, None, 0.0, None

    if lane_boundaries is None:
        lane_boundaries = []

    # Build effective boundaries from road mask if no explicit lanes provided
    if not lane_boundaries:
        if road_mask is None:
            return False, None, 0.0, None

        road_bbox = road_mask.get("bbox")
        if road_bbox is not None:
            min_x = float(road_bbox.get("min_x", 0))
            max_x = float(road_bbox.get("max_x", 0))
            min_y = float(road_bbox.get("min_y", 0))
            max_y = float(road_bbox.get("max_y", 0))
            lane_boundaries = [
                {"start": {"x": min_x, "y": min_y}, "end": {"x": max_x, "y": min_y}},
                {"start": {"x": max_x, "y": min_y}, "end": {"x": max_x, "y": max_y}},
                {"start": {"x": max_x, "y": max_y}, "end": {"x": min_x, "y": max_y}},
                {"start": {"x": min_x, "y": max_y}, "end": {"x": min_x, "y": min_y}},
            ]

        # Also try polygon-based road mask
        polygons = road_mask.get("polygons") or []
        for poly in polygons:
            if len(poly) >= 3:
                for i in range(len(poly)):
                    j = (i + 1) % len(poly)
                    lane_boundaries.append({
                        "start": {"x": float(poly[i][0]), "y": float(poly[i][1])},
                        "end": {"x": float(poly[j][0]), "y": float(poly[j][1])},
                    })

    if not lane_boundaries:
        return False, None, 0.0, None

    threshold_m = settings.TRAJECTORY_ROAD_INTERSECTION_THRESHOLD_M

    for pred in predicted:
        px, py = pred.x, pred.y
        for seg in lane_boundaries:
            sx = float(seg["start"]["x"])
            sy = float(seg["start"]["y"])
            ex = float(seg["end"]["x"])
            ey = float(seg["end"]["y"])

            dist = _point_to_segment_distance(px, py, sx, sy, ex, ey)
            if dist <= threshold_m:
                confidence = max(0.3, pred.confidence * (1.0 - pred.t * 0.08))
                intersection_pt = _project_point_on_segment(px, py, sx, sy, ex, ey)
                return True, pred.t, round(confidence, 4), intersection_pt

    return False, None, 0.0, None


def _point_to_segment_distance(
    px: float, py: float, sx: float, sy: float, ex: float, ey: float
) -> float:
    """Minimum distance from point (px, py) to segment (sx,sy)-(ex,ey)."""
    dx = ex - sx
    dy = ey - sy
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return math.sqrt((px - sx) ** 2 + (py - sy) ** 2)
    t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / len_sq))
    proj_x = sx + t * dx
    proj_y = sy + t * dy
    return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)


def _project_point_on_segment(
    px: float, py: float, sx: float, sy: float, ex: float, ey: float
) -> tuple[float, float]:
    """Return the closest point on segment to the query point."""
    dx = ex - sx
    dy = ey - sy
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return (sx, sy)
    t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / len_sq))
    return (sx + t * dx, sy + t * dy)


# ---------------------------------------------------------------------------
# Main predictor orchestrator
# ---------------------------------------------------------------------------


class TrajectoryPredictor:
    """High-level API for predictive trajectory modeling.

    Usage::

        predictor = TrajectoryPredictor()
        alerts = predictor.evaluate_frame(detections, road_mask, rules)
    """

    def __init__(self) -> None:
        self._learned = _get_learned_model()

    def predict_trajectory(
        self,
        state: TrackEventState,
        horizons: list[float] | None = None,
    ) -> list[PredictedPoint]:
        """Predict future positions for a single tracked object.

        Selects the best available model: learned LSTM (if enabled and loaded)
        > constant-acceleration > constant-velocity.
        """
        if horizons is None:
            horizons = list(settings.TRAJECTORY_PREDICTION_HORIZONS)

        positions = _extract_positions(state.trajectory)
        if positions is None:
            return []

        n = len(positions)

        # Learned model path (if enabled)
        if self._learned is not None and n >= 4:
            try:
                learned_pred = self._learned.predict(positions, horizons)
                # Fuse confidence: weight by number of observations
                obs_weight = min(1.0, n / 16.0)
                for p in learned_pred:
                    p.confidence = round(p.confidence * obs_weight, 4)
                return learned_pred
            except Exception as exc:
                logger.warning("learned_trajectory_fallback", error=str(exc))

        # Physics fallback: prefer CA when enough data and acceleration present
        if n >= 3:
            # Quick check for meaningful acceleration
            dt1 = float(positions[-1, 2] - positions[-2, 2])
            dt2 = float(positions[-2, 2] - positions[-3, 2])
            if dt1 > 0 and dt2 > 0:
                vx1 = (positions[-1, 0] - positions[-2, 0]) / dt1
                vx2 = (positions[-2, 0] - positions[-3, 0]) / dt2
                vy1 = (positions[-1, 1] - positions[-2, 1]) / dt1
                vy2 = (positions[-2, 1] - positions[-3, 1]) / dt2
                avg_dt = (dt1 + dt2) / 2.0
                ax = abs(vx1 - vx2) / avg_dt
                ay = abs(vy1 - vy2) / avg_dt
                if ax > 0.5 or ay > 0.5:
                    return predict_constant_acceleration(positions, horizons)

        return predict_constant_velocity(positions, horizons)

    def fuse_and_assess(
        self,
        predicted: list[PredictedPoint],
        road_mask: dict | None,
        lane_boundaries: list[dict] | None = None,
    ) -> tuple[bool, float | None, float, tuple[float, float] | None]:
        """Fuse predicted trajectory with road geometry."""
        return fuse_with_road_mask(predicted, road_mask, lane_boundaries)

    def evaluate_predictive_intersection(
        self,
        rule: PredictiveIntersectionRule,
        state: TrackEventState,
        road_mask: dict | None,
        lane_boundaries: list[dict] | None = None,
        now: float | None = None,
    ) -> PerceptionEvent | None:
        """Evaluate a predictive_intersection rule against a track.

        1. Predict trajectory forward up to ``rule.prediction_horizon``.
        2. Fuse with road mask to get P-TTI and intersection confidence.
        3. Apply confidence-gated alerting: only emit if confidence >= threshold.
        """
        if not rule.enabled or now is None:
            return None

        # Require minimum trajectory history
        if len(state.trajectory) < rule.min_trajectory_points:
            return None

        # Filter horizons to rule horizon
        all_horizons = list(settings.TRAJECTORY_PREDICTION_HORIZONS)
        horizons = [h for h in all_horizons if h <= rule.prediction_horizon]
        if not horizons:
            horizons = [rule.prediction_horizon]

        predicted = self.predict_trajectory(state, horizons)
        if not predicted:
            return None

        will_intersect, tti, confidence, intersection_pt = self.fuse_and_assess(
            predicted, road_mask, lane_boundaries
        )

        if not will_intersect:
            return None

        # Confidence-gated alerting
        if confidence < rule.confidence_threshold:
            logger.debug(
                "predictive_intersection_below_threshold",
                track_id=state.track_id,
                rule_id=rule.rule_id,
                confidence=confidence,
                threshold=rule.confidence_threshold,
            )
            return None

        return _fire(
            state,
            rule,
            now,
            confidence,
            duration_seconds=tti,
            details={
                "predicted_tti": round(tti, 4) if tti is not None else None,
                "intersection_confidence": round(confidence, 4),
                "confidence_threshold": rule.confidence_threshold,
                "prediction_horizon": rule.prediction_horizon,
                "trajectory_points": len(predicted),
                "intersection_point": (
                    {"x": round(intersection_pt[0], 4), "y": round(intersection_pt[1], 4)}
                    if intersection_pt
                    else None
                ),
                "model": "learned_lstm" if self._learned is not None and self._learned.is_loaded else "physics",
            },
        )

    def make_confidence_gated_alert(
        self,
        rule: PredictiveIntersectionRule,
        state: TrackEventState,
        predicted: list[PredictedPoint],
        tti: float | None,
        confidence: float,
        intersection_pt: tuple[float, float] | None,
    ) -> ConfidenceGatedAlert:
        """Create a ``ConfidenceGatedAlert`` data object (for external consumers)."""
        from uuid import uuid4

        return ConfidenceGatedAlert(
            alert_id=uuid4().hex,
            rule_id=rule.rule_id,
            track_id=state.track_id,
            predicted_tti=tti if tti is not None else float("inf"),
            confidence=confidence,
            threshold=rule.confidence_threshold,
            trajectory=predicted,
            road_intersection_point=intersection_pt,
        )


# ---------------------------------------------------------------------------
# Extended EventEngine mixin
# ---------------------------------------------------------------------------


def evaluate_predictive_rules(
    predictor: TrajectoryPredictor,
    rules: list[EventRule],
    state: TrackEventState,
    road_mask: dict | None,
    lane_boundaries: list[dict] | None,
    now: float,
) -> list[PerceptionEvent]:
    """Evaluate any ``predictive_intersection`` rules in the rule set.

    Call this from ``EventEngine._evaluate_rule`` or as a post-pass after
    the standard rule evaluation loop.
    """
    events: list[PerceptionEvent] = []
    for rule in rules:
        if (
            isinstance(rule, PredictiveIntersectionRule)
            and rule.rule_type == PREDICTIVE_INTERSECTION
            and rule.enabled
        ):
            event = predictor.evaluate_predictive_intersection(
                rule, state, road_mask, lane_boundaries, now
            )
            if event is not None:
                events.append(event)
    return events


# ---------------------------------------------------------------------------
# Convenience: full-frame evaluation (mirrors EventEngine.update pattern)
# ---------------------------------------------------------------------------


def predict_and_alert(
    detections: list[dict],
    rules: list[EventRule],
    road_mask: dict | None = None,
    lane_boundaries: list[dict] | None = None,
    track_states: dict[int, TrackEventState] | None = None,
    now: float | None = None,
) -> list[PerceptionEvent]:
    """End-to-end predictive trajectory evaluation for a single frame.

    This function is designed to be called alongside (or after)
    ``EventEngine.update()``.  It only processes tracks that have sufficient
    trajectory history and only evaluates ``predictive_intersection`` rules.

    Args:
        detections: list of detection dicts (for building/updating TrackEventStates).
        rules: full rule set (predictive rules are filtered internally).
        road_mask: road segmentation mask dict.
        lane_boundaries: optional explicit lane boundary segments.
        track_states: existing TrackEventState dict (mutated in place).
        now: current timestamp (defaults to ``time.time()``).

    Returns:
        List of PerceptionEvent from predictive rules.
    """
    import time as _time

    if now is None:
        now = _time.time()

    if track_states is None:
        track_states = {}

    predictor = TrajectoryPredictor()
    events: list[PerceptionEvent] = []

    for det in detections:
        track_id = det.get("track_id")
        if track_id is None:
            continue
        try:
            track_id = int(track_id)
        except (TypeError, ValueError):
            continue

        state = track_states.get(track_id)
        if state is None:
            continue  # Track must already exist in EventEngine state

        # Run predictive evaluation
        predictive_events = evaluate_predictive_rules(
            predictor, rules, state, road_mask, lane_boundaries, now
        )
        events.extend(predictive_events)

    return events
