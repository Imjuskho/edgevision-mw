from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.frontier_capabilities import TrajectoryPrediction

logger = logging.getLogger(__name__)


def predict_trajectory(
    track_history: list[dict],
    prediction_horizons: list[float] | None = None,
) -> list[dict]:
    """Predict future positions for a tracked object using kinematic models.

    Each entry in track_history must contain:
        x, y, z: current position (metres)
        vx, vy, vz: velocity (m/s)
        timestamp: frame timestamp (ISO string or datetime)

    Returns a list of prediction dicts, one per horizon, each containing:
        time_ahead, position {x,y,z}, method, confidence
    """
    if prediction_horizons is None:
        prediction_horizons = list(settings.TRAJECTORY_PREDICTION_HORIZONS)

    if not track_history:
        return []

    current = track_history[-1]
    px = float(current.get("x", 0.0))
    py = float(current.get("y", 0.0))
    pz = float(current.get("z", 0.0))
    vx = float(current.get("vx", 0.0))
    vy = float(current.get("vy", 0.0))
    vz = float(current.get("vz", 0.0))

    # Estimate acceleration from last two frames when available
    ax, ay, az = 0.0, 0.0, 0.0
    if len(track_history) >= 2:
        prev = track_history[-2]
        dt_prev = _time_delta_seconds(prev, current)
        if dt_prev > 0:
            prev_vx = float(prev.get("vx", 0.0))
            prev_vy = float(prev.get("vy", 0.0))
            prev_vz = float(prev.get("vz", 0.0))
            ax = (vx - prev_vx) / dt_prev
            ay = (vy - prev_vy) / dt_prev
            az = (vz - prev_vz) / dt_prev

    speed = math.sqrt(vx * vx + vy * vy + vz * vz)
    has_accel = abs(ax) > 0.01 or abs(ay) > 0.01 or abs(az) > 0.01

    # --- Kalman filter prediction (primary) ---
    kalman_preds = _kalman_predict(track_history, prediction_horizons)

    predictions: list[dict] = []
    for horizon in prediction_horizons:
        # If Kalman produced a result, use it as the primary prediction
        kalman_pos = kalman_preds.get(horizon)
        if kalman_pos is not None:
            cx, cy, cz = kalman_pos
            method = "kalman_filter"
            confidence = max(0.1, 0.92 - horizon * 0.10)
        elif has_accel and len(track_history) >= 3:
            # Constant-acceleration model when acceleration is significant
            cx = px + vx * horizon + 0.5 * ax * horizon * horizon
            cy = py + vy * horizon + 0.5 * ay * horizon * horizon
            cz = pz + vz * horizon + 0.5 * az * horizon * horizon
            method = "constant_acceleration"
            confidence = max(0.1, 0.9 - horizon * 0.12)
        else:
            # Constant-velocity model
            cx = px + vx * horizon
            cy = py + vy * horizon
            cz = pz + vz * horizon
            method = "constant_velocity"
            confidence = max(0.1, 0.95 - horizon * 0.15)

        # Confidence degrades with speed (fast objects harder to predict)
        if speed > 5.0:
            confidence *= max(0.3, 1.0 - (speed - 5.0) * 0.05)

        predictions.append(
            {
                "time_ahead": horizon,
                "position": {"x": round(cx, 4), "y": round(cy, 4), "z": round(cz, 4)},
                "method": method,
                "confidence": round(confidence, 4),
            }
        )

    return predictions


def _kalman_predict(
    track_history: list[dict],
    horizons: list[float],
    process_noise: float = 0.5,
    measurement_noise: float = 1.0,
) -> dict[float, tuple[float, float, float]]:
    """Run a linear Kalman filter over track_history and predict at horizons.

    State vector: [x, y, vx, vy]
    Transition model: constant velocity
    Returns dict mapping horizon -> (x, y, z) predicted position.
    """
    if len(track_history) < 2:
        return {}

    try:
        from scipy.linalg import inv
    except ImportError:
        return {}

    # Build state from the last measurement
    last = track_history[-1]
    prev = track_history[-2]
    dt = _time_delta_seconds(prev, last)
    if dt <= 0:
        return {}

    x = float(last.get("x", 0.0))
    y = float(last.get("y", 0.0))
    vx = float(last.get("vx", 0.0))
    vy = float(last.get("vy", 0.0))

    # State: [x, y, vx, vy]
    state = np.array([x, y, vx, vy], dtype=np.float64)

    # State transition matrix F (constant velocity): [x, y, vx, vy] -> [x+vx*dt, y+vy*dt, vx, vy]
    F = np.array([
        [1.0, 0.0, dt, 0.0],
        [0.0, 1.0, 0.0, dt],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=np.float64)

    # Measurement matrix H (we observe x, y)
    H = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
    ], dtype=np.float64)

    # Process noise covariance Q
    q = process_noise
    Q = np.array([
        [dt**4 / 4, 0.0, dt**3 / 2, 0.0],
        [0.0, dt**4 / 4, 0.0, dt**3 / 2],
        [dt**3 / 2, 0.0, dt**2, 0.0],
        [0.0, dt**3 / 2, 0.0, dt**2],
    ], dtype=np.float64) * q

    # Measurement noise covariance R
    R = np.eye(2, dtype=np.float64) * measurement_noise

    # Initial covariance (large uncertainty on velocity)
    P = np.diag([1.0, 1.0, 10.0, 10.0]).astype(np.float64)

    # --- Filter update through track history ---
    for i in range(len(track_history)):
        if i == 0:
            continue

        step = track_history[i]
        if i == 0:
            dt_step = dt
        else:
            dt_step = _time_delta_seconds(track_history[i - 1], step)
            if dt_step <= 0:
                dt_step = dt

        F_step = np.array([
            [1.0, 0.0, dt_step, 0.0],
            [0.0, 1.0, 0.0, dt_step],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float64)

        Q_step = np.array([
            [dt_step**4 / 4, 0.0, dt_step**3 / 2, 0.0],
            [0.0, dt_step**4 / 4, 0.0, dt_step**3 / 2],
            [dt_step**3 / 2, 0.0, dt_step**2, 0.0],
            [0.0, dt_step**3 / 2, 0.0, dt_step**2],
        ], dtype=np.float64) * q

        # Predict
        state = F_step @ state
        P = F_step @ P @ F_step.T + Q_step

        # Update with measurement
        z = np.array([float(step.get("x", 0.0)), float(step.get("y", 0.0))], dtype=np.float64)
        y_innov = z - H @ state
        S = H @ P @ H.T + R
        try:
            K = P @ H.T @ inv(S)
        except Exception:
            continue
        state = state + K @ y_innov
        P = (np.eye(4, dtype=np.float64) - K @ H) @ P

    # --- Predict forward at each horizon ---
    results: dict[float, tuple[float, float, float]] = {}
    z_pred = float(last.get("z", 0.0))
    for h in horizons:
        F_h = np.array([
            [1.0, 0.0, h, 0.0],
            [0.0, 1.0, 0.0, h],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=np.float64)
        predicted_state = F_h @ state
        results[h] = (float(predicted_state[0]), float(predicted_state[1]), z_pred)

    return results


def check_road_intersection(
    predicted_positions: list[dict],
    road_mask: dict | None,
    lane_boundaries: list | None,
) -> tuple[bool, float | None, float]:
    """Check whether a predicted trajectory crosses road geometry.

    Uses lane boundaries (list of line segments) to detect intersection.
    Each lane boundary segment: {"start": {"x","y"}, "end": {"x","y"}}.

    Returns (will_intersect, time_to_intersection, confidence).
    """
    if not predicted_positions:
        return False, None, 0.0

    if lane_boundaries is None:
        lane_boundaries = []

    if not lane_boundaries:
        # Fall back to road_mask bounding box if available
        if road_mask is None:
            return False, None, 0.0
        road_bbox = road_mask.get("bbox")
        if road_bbox is None:
            return False, None, 0.0
        min_x = float(road_bbox.get("min_x", 0))
        max_x = float(road_bbox.get("max_x", 0))
        min_y = float(road_bbox.get("min_y", 0))
        max_y = float(road_bbox.get("max_y", 0))
        segments = [
            {"start": {"x": min_x, "y": min_y}, "end": {"x": max_x, "y": min_y}},
            {"start": {"x": max_x, "y": min_y}, "end": {"x": max_x, "y": max_y}},
            {"start": {"x": max_x, "y": max_y}, "end": {"x": min_x, "y": max_y}},
            {"start": {"x": min_x, "y": max_y}, "end": {"x": min_x, "y": min_y}},
        ]
        lane_boundaries = segments

    threshold_m = settings.TRAJECTORY_ROAD_INTERSECTION_THRESHOLD_M
    for pred in predicted_positions:
        pos = pred.get("position", {"x": 0, "y": 0, "z": 0})
        t_ahead = pred.get("time_ahead", 0.0)
        px = float(pos.get("x", 0))
        py = float(pos.get("y", 0))

        for seg in lane_boundaries:
            sx = float(seg["start"]["x"])
            sy = float(seg["start"]["y"])
            ex = float(seg["end"]["x"])
            ey = float(seg["end"]["y"])

            dist = _point_segment_distance(px, py, sx, sy, ex, ey)
            if dist <= threshold_m:
                confidence = max(0.3, 1.0 - t_ahead * 0.1)
                return True, t_ahead, round(confidence, 4)

    return False, None, 0.0


async def store_trajectory_prediction(
    db: AsyncSession,
    track_id: int,
    frame_timestamp: datetime,
    current_state: dict,
    predictions: list[dict],
    road_intersection: tuple[bool, float | None, float],
) -> TrajectoryPrediction:
    """Persist a trajectory prediction to the database."""
    predicted_positions = [p["position"] for p in predictions]
    predicted_times = [p["time_ahead"] for p in predictions]
    will_intersect, tti, confidence = road_intersection

    # Compute heading from velocity
    vx = float(current_state.get("vx", 0.0))
    vy = float(current_state.get("vy", 0.0))
    heading_rad = math.atan2(vy, vx) if (vx != 0.0 or vy != 0.0) else 0.0

    # Determine best prediction method from predictions
    method = predictions[0].get("method", "constant_velocity") if predictions else "constant_velocity"

    record = TrajectoryPrediction(
        track_id=track_id,
        frame_timestamp=frame_timestamp,
        current_position={
            "x": float(current_state.get("x", 0.0)),
            "y": float(current_state.get("y", 0.0)),
            "z": float(current_state.get("z", 0.0)),
        },
        current_velocity={
            "vx": vx,
            "vy": vy,
            "vz": float(current_state.get("vz", 0.0)),
        },
        heading_rad=heading_rad,
        predicted_positions=predicted_positions,
        predicted_times=predicted_times,
        time_to_road_intersection=tti,
        will_intersect_road=will_intersect,
        intersection_confidence=confidence,
        class_name=current_state.get("class_name"),
        prediction_method=method,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info("Stored trajectory prediction for track %d at %s", track_id, frame_timestamp.isoformat())
    return record


async def get_recent_predictions(
    db: AsyncSession,
    camera_node_id: str,
    minutes: int = 5,
) -> list[TrajectoryPrediction]:
    """Retrieve recent trajectory predictions for a camera node."""
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
    result = await db.execute(
        select(TrajectoryPrediction)
        .where(
            TrajectoryPrediction.created_at >= cutoff,
        )
        .order_by(TrajectoryPrediction.created_at.desc())
        .limit(500)
    )
    return list(result.scalars().all())


async def get_prediction_accuracy(
    db: AsyncSession,
    track_id: int,
    ground_truth_positions: list[tuple[float, float, float]] | None = None,
) -> dict:
    """Compare past predictions with actual positions.

    If ground_truth_positions is provided (list of (timestamp, x, y) tuples),
    compute ADE (Average Displacement Error) and FDE (Final Displacement Error).

    Otherwise, use velocity-consistency metric (marked as estimated).

    Returns statistics on prediction error per horizon.
    """

    result = await db.execute(
        select(TrajectoryPrediction)
        .where(TrajectoryPrediction.track_id == track_id)
        .order_by(TrajectoryPrediction.frame_timestamp.desc())
        .limit(100)
    )
    predictions = list(result.scalars().all())

    if not predictions:
        return {
            "track_id": track_id,
            "num_predictions": 0,
            "horizon_accuracy": {},
        }

    has_ground_truth = ground_truth_positions is not None and len(ground_truth_positions) > 0

    horizon_errors: dict[float, list[float]] = {}
    ade_errors: list[float] = []
    fde_errors: list[float] = []

    for pred in predictions:
        actuals = pred.predicted_positions
        times = pred.predicted_times
        if not actuals or not times:
            continue

        if has_ground_truth:
            # Compute real ADE/FDE against ground truth
            pred_ts = pred.frame_timestamp.timestamp()
            gt_times = np.array([gt[0] for gt in ground_truth_positions])
            gt_positions = np.array([(gt[1], gt[2]) for gt in ground_truth_positions])

            for predicted, t in zip(actuals, times, strict=False):
                target_ts = pred_ts + t
                # Find closest ground truth timestamp
                idx = int(np.argmin(np.abs(gt_times - target_ts)))
                gt_x, gt_y = gt_positions[idx]
                error = math.sqrt(
                    (float(predicted.get("x", 0)) - gt_x) ** 2
                    + (float(predicted.get("y", 0)) - gt_y) ** 2
                )
                horizon_errors.setdefault(t, []).append(error)
                ade_errors.append(error)
                if t == max(times):
                    fde_errors.append(error)
        else:
            # Fallback: velocity-consistency metric
            for _i, (predicted, t) in enumerate(zip(actuals, times, strict=False)):
                current_pos = pred.current_position
                vel = pred.current_velocity
                expected = {
                    "x": float(current_pos.get("x", 0)) + float(vel.get("vx", 0)) * t,
                    "y": float(current_pos.get("y", 0)) + float(vel.get("vy", 0)) * t,
                }
                error = math.sqrt(
                    (float(predicted.get("x", 0)) - expected["x"]) ** 2
                    + (float(predicted.get("y", 0)) - expected["y"]) ** 2
                )
                horizon_errors.setdefault(t, []).append(error)

    horizon_accuracy = {}
    for t, errors in sorted(horizon_errors.items()):
        horizon_accuracy[str(t)] = {
            "mean_error_m": round(sum(errors) / len(errors), 4) if errors else 0.0,
            "max_error_m": round(max(errors), 4) if errors else 0.0,
            "sample_count": len(errors),
        }

    response: dict = {
        "track_id": track_id,
        "num_predictions": len(predictions),
        "horizon_accuracy": horizon_accuracy,
        "estimated": not has_ground_truth,
    }

    if has_ground_truth:
        response["ADE"] = round(float(np.mean(ade_errors)), 4) if ade_errors else 0.0
        response["FDE"] = round(float(np.mean(fde_errors)), 4) if fde_errors else 0.0

    return response


def detect_dwell_events(
    positions: list[tuple[float, float, float]],
    radius: float = 2.0,
    min_duration: float = 30.0,
) -> list[dict]:
    """Detect when an object stays within a radius for more than a threshold duration.

    Args:
        positions: List of (timestamp, x, y) tuples sorted by time.
        radius: Maximum distance from center to be considered "within" the area (metres).
        min_duration: Minimum dwell duration in seconds.

    Returns:
        List of dwell event dicts with start_time, end_time, center_position, duration.
    """
    if len(positions) < 2:
        return []

    events: list[dict] = []
    start_idx = 0

    while start_idx < len(positions) - 1:
        center_x = positions[start_idx][1]
        center_y = positions[start_idx][2]
        end_idx = start_idx

        # Extend window while positions stay within radius of the center
        for j in range(start_idx + 1, len(positions)):
            dx = positions[j][1] - center_x
            dy = positions[j][2] - center_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= radius:
                end_idx = j
            else:
                break

        duration = positions[end_idx][0] - positions[start_idx][0]
        if duration >= min_duration:
            # Compute centroid of all points in the dwell window
            window = positions[start_idx:end_idx + 1]
            cx = sum(p[1] for p in window) / len(window)
            cy = sum(p[2] for p in window) / len(window)
            events.append({
                "start_time": positions[start_idx][0],
                "end_time": positions[end_idx][0],
                "center_position": {"x": round(cx, 4), "y": round(cy, 4)},
                "duration": round(duration, 2),
            })

        start_idx = max(end_idx + 1, start_idx + 1)

    return events


def detect_loitering(
    positions: list[tuple[float, float, float]],
    radius: float = 5.0,
    min_visits: int = 3,
    min_total_duration: float = 60.0,
    visit_gap_threshold: float = 10.0,
) -> list[dict]:
    """Detect repeated visits to the same area (loitering pattern).

    Args:
        positions: List of (timestamp, x, y) tuples sorted by time.
        radius: Radius defining "same area" (metres).
        min_visits: Minimum number of distinct visits to flag loitering.
        min_total_duration: Minimum total time spent in the area across all visits.
        visit_gap_threshold: Minimum gap (seconds) between visits to count as distinct.

    Returns:
        List of loitering event dicts with visit_count, total_duration, area_center.
    """
    if len(positions) < 2:
        return []

    # Cluster positions into visits using simple proximity grouping
    visits: list[dict] = []
    current_cluster: list[tuple[float, float, float]] = [positions[0]]

    for i in range(1, len(positions)):
        prev_x = current_cluster[-1][1]
        prev_y = current_cluster[-1][2]
        dx = positions[i][1] - prev_x
        dy = positions[i][2] - prev_y
        dist = math.sqrt(dx * dx + dy * dy)
        gap = positions[i][0] - current_cluster[-1][0]

        if dist <= radius and gap <= visit_gap_threshold * 2:
            current_cluster.append(positions[i])
        else:
            if len(current_cluster) >= 2:
                visits.append({
                    "center_x": sum(p[1] for p in current_cluster) / len(current_cluster),
                    "center_y": sum(p[2] for p in current_cluster) / len(current_cluster),
                    "start_time": current_cluster[0][0],
                    "end_time": current_cluster[-1][0],
                    "duration": current_cluster[-1][0] - current_cluster[0][0],
                })
            current_cluster = [positions[i]]

    if len(current_cluster) >= 2:
        visits.append({
            "center_x": sum(p[1] for p in current_cluster) / len(current_cluster),
            "center_y": sum(p[2] for p in current_cluster) / len(current_cluster),
            "start_time": current_cluster[0][0],
            "end_time": current_cluster[-1][0],
            "duration": current_cluster[-1][0] - current_cluster[0][0],
        })

    if len(visits) < min_visits:
        return []

    # Group visits into loitering events by proximity of visit centers
    loitering_events: list[dict] = []
    used: set[int] = set()

    for i in range(len(visits)):
        if i in used:
            continue
        cluster_visits = [visits[i]]
        used.add(i)

        for j in range(i + 1, len(visits)):
            if j in used:
                continue
            dx = visits[j]["center_x"] - visits[i]["center_x"]
            dy = visits[j]["center_y"] - visits[i]["center_y"]
            if math.sqrt(dx * dx + dy * dy) <= radius * 2:
                cluster_visits.append(visits[j])
                used.add(j)

        if len(cluster_visits) >= min_visits:
            total_dur = sum(v["duration"] for v in cluster_visits)
            if total_dur >= min_total_duration:
                avg_cx = sum(v["center_x"] for v in cluster_visits) / len(cluster_visits)
                avg_cy = sum(v["center_y"] for v in cluster_visits) / len(cluster_visits)
                loitering_events.append({
                    "visit_count": len(cluster_visits),
                    "total_duration": round(total_dur, 2),
                    "area_center": {"x": round(avg_cx, 4), "y": round(avg_cy, 4)},
                    "first_visit": cluster_visits[0]["start_time"],
                    "last_visit": cluster_visits[-1]["end_time"],
                })

    return loitering_events


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _time_delta_seconds(a: dict, b: dict) -> float:
    """Compute time difference in seconds between two frame dicts."""
    ts_a = a.get("timestamp")
    ts_b = b.get("timestamp")
    if ts_a is None or ts_b is None:
        return 0.0

    def _to_dt(val):
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        return datetime.now(UTC)

    dt_a = _to_dt(ts_a)
    dt_b = _to_dt(ts_b)
    delta = (dt_b - dt_a).total_seconds()
    return max(delta, 0.001)


def _point_segment_distance(px: float, py: float, sx: float, sy: float, ex: float, ey: float) -> float:
    """Minimum distance from point (px,py) to line segment (sx,sy)-(ex,ey)."""
    dx = ex - sx
    dy = ey - sy
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return math.sqrt((px - sx) ** 2 + (py - sy) ** 2)

    t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / len_sq))
    proj_x = sx + t * dx
    proj_y = sy + t * dy
    return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
