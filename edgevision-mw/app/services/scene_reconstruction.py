from __future__ import annotations

import json
import logging
import math
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.frontier_capabilities import SceneReconstruction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Position cache — Redis-backed with in-memory fallback
# ---------------------------------------------------------------------------
_redis_client = None
_use_redis_cache = False
_position_cache: dict[str, dict[int, list[dict]]] = {}


def _init_cache() -> None:
    """Attempt to connect to Redis for position caching; fall back to in-memory."""
    global _redis_client, _use_redis_cache
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        _use_redis_cache = True
        logger.info("Scene position cache using Redis")
    except Exception:
        _use_redis_cache = False
        logger.warning(
            "Redis unavailable for scene position cache — falling back to in-memory dict"
        )


_init_cache()


async def _cache_get(camera_id: str, track_id: int) -> list[dict]:
    """Retrieve position history for a camera+track pair."""
    if _use_redis_cache and _redis_client is not None:
        key = f"scene_pos:{camera_id}:{track_id}"
        try:
            raw = await _redis_client.get(key)
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass
        return []
    cam = _position_cache.setdefault(camera_id, {})
    return cam.get(track_id, [])


async def _cache_set(camera_id: str, track_id: int, value: list[dict]) -> None:
    """Store position history for a camera+track pair with 1-hour TTL."""
    if _use_redis_cache and _redis_client is not None:
        key = f"scene_pos:{camera_id}:{track_id}"
        try:
            await _redis_client.set(key, json.dumps(value), ex=3600)
            return
        except Exception:
            pass
    cam = _position_cache.setdefault(camera_id, {})
    cam[track_id] = value


async def _cache_get_all(camera_id: str) -> dict[int, list[dict]]:
    """Return all track histories for a camera."""
    if _use_redis_cache and _redis_client is not None:
        pattern = f"scene_pos:{camera_id}:*"
        try:
            result: dict[int, list[dict]] = {}
            async for raw_key in _redis_client.scan_iter(match=pattern, count=200):
                track_id = int(raw_key.rsplit(":", 1)[-1])
                raw_val = await _redis_client.get(raw_key)
                if raw_val is not None:
                    result[track_id] = json.loads(raw_val)
            return result
        except Exception:
            pass
    return dict(_position_cache.get(camera_id, {}))


async def create_reconstruction_snapshot(
    db: AsyncSession,
    camera_node_id: str,
    detections: list[dict],
    depth_map: dict,
    road_result: dict,
) -> SceneReconstruction:
    """Build a 3D scene snapshot from 2D detections + depth + road data.

    Each detection dict: {"track_id": int, "bbox": [x,y,w,h], "class_name": str,
                          "confidence": float, "centroid": {"x","y"}}
    depth_map: {"depth_values": list[float], "width": int, "height": int}
    road_result: {"drivable_area_ratio": float, "lane_boundaries": list,
                  "road_mask": dict}
    """
    now = datetime.now(UTC)
    frame_ts = now

    # Convert 2D detections to 3D positions using depth
    depth_values = depth_map.get("depth_values", [])
    img_w = depth_map.get("width", 640)
    img_h = depth_map.get("height", 480)

    objects_3d: list[dict] = []
    for det in detections:
        centroid = det.get("centroid", {"x": 0.5, "y": 0.5})
        cx_norm = float(centroid.get("x", 0.5))
        cy_norm = float(centroid.get("y", 0.5))

        # Sample depth at centroid
        px = min(int(cx_norm * img_w), img_w - 1) if img_w > 0 else 0
        py = min(int(cy_norm * img_h), img_h - 1) if img_h > 0 else 0
        depth_idx = py * img_w + px
        depth_val = float(depth_values[depth_idx]) if depth_idx < len(depth_values) else 10.0

        # Simple pinhole projection (assume focal length ≈ image width)
        focal = float(depth_map.get("focal_length", img_w))
        x_3d = (cx_norm - 0.5) * depth_val * img_w / focal if focal > 0 else 0.0
        y_3d = (cy_norm - 0.5) * depth_val * img_h / focal if focal > 0 else 0.0
        z_3d = depth_val

        obj = {
            "track_id": det.get("track_id"),
            "class_name": det.get("class_name", "object"),
            "confidence": float(det.get("confidence", 0.0)),
            "position_3d": {"x": round(x_3d, 4), "y": round(y_3d, 4), "z": round(z_3d, 4)},
            "bbox_2d": det.get("bbox", []),
        }
        objects_3d.append(obj)

    # Classify static vs dynamic
    static_threshold = settings.SCENE_STATIC_OBJECT_THRESHOLD

    static_objects: list[dict] = []
    dynamic_objects: list[dict] = []

    for obj in objects_3d:
        tid = obj.get("track_id")
        pos = obj["position_3d"]
        if tid is not None:
            history = await _cache_get(camera_node_id, tid)
            history.append(pos)
            if len(history) > 30:
                history = history[-30:]
            await _cache_set(camera_node_id, tid, history)

            if len(history) >= static_threshold:
                # Compute variance of position
                mean_x = sum(p["x"] for p in history) / len(history)
                mean_y = sum(p["y"] for p in history) / len(history)
                var = sum((p["x"] - mean_x) ** 2 + (p["y"] - mean_y) ** 2 for p in history) / len(history)
                if var < 0.5:  # Less than ~0.7m movement
                    static_objects.append(obj)
                    continue

        dynamic_objects.append(obj)

    # Scene bounds
    all_x = [o["position_3d"]["x"] for o in objects_3d] or [0.0]
    all_y = [o["position_3d"]["y"] for o in objects_3d] or [0.0]
    all_z = [o["position_3d"]["z"] for o in objects_3d] or [0.0]
    scene_bounds = {
        "min_x": round(min(all_x), 4),
        "min_y": round(min(all_y), 4),
        "min_z": round(min(all_z), 4),
        "max_x": round(max(all_x), 4),
        "max_y": round(max(all_y), 4),
        "max_z": round(max(all_z), 4),
    }

    # Dominant classes
    class_counts: dict[str, int] = {}
    for obj in objects_3d:
        cn = obj["class_name"]
        class_counts[cn] = class_counts.get(cn, 0) + 1
    dominant_classes = [{"class": cn, "count": cnt} for cn, cnt in sorted(class_counts.items(), key=lambda x: -x[1])]

    # Change events (compare with previous snapshot)
    change_events: list[dict] = []
    prev_result = await db.execute(
        select(SceneReconstruction)
        .where(SceneReconstruction.camera_node_id == camera_node_id)
        .order_by(SceneReconstruction.timestamp.desc())
        .limit(1)
    )
    prev = prev_result.scalar_one_or_none()
    if prev is not None:
        prev_static = prev.static_objects or []
        prev_dynamic = prev.dynamic_objects or []
        prev_all = {o.get("track_id"): o for o in (prev_static + prev_dynamic) if o.get("track_id") is not None}
        curr_all = {o.get("track_id"): o for o in objects_3d if o.get("track_id") is not None}

        prev_ids = set(prev_all.keys())
        curr_ids = set(curr_all.keys())

        for tid in curr_ids - prev_ids:
            obj = curr_all[tid]
            change_events.append(
                {
                    "type": "object_appeared",
                    "description": f"{obj['class_name']} (track {tid}) appeared in scene",
                    "timestamp": now.isoformat(),
                }
            )
        for tid in prev_ids - curr_ids:
            obj = prev_all[tid]
            change_events.append(
                {
                    "type": "object_disappeared",
                    "description": f"{obj['class_name']} (track {tid}) left scene",
                    "timestamp": now.isoformat(),
                }
            )
        for tid in prev_ids & curr_ids:
            pp = prev_all[tid]["position_3d"]
            cp = curr_all[tid]["position_3d"]
            dist = math.sqrt((pp["x"] - cp["x"]) ** 2 + (pp["y"] - cp["y"]) ** 2 + (pp["z"] - cp["z"]) ** 2)
            if dist > 2.0:
                change_events.append(
                    {
                        "type": "significant_movement",
                        "description": (f"{curr_all[tid]['class_name']} (track {tid}) moved {dist:.1f}m"),
                        "timestamp": now.isoformat(),
                    }
                )

    # Reconstruction quality heuristic
    quality = 0.5
    if depth_values:
        quality += 0.2
    if objects_3d:
        quality += 0.1
    if road_result.get("drivable_area_ratio", 0) > 0:
        quality += 0.1
    if len(objects_3d) > 3:
        quality += 0.1
    quality = min(quality, 1.0)

    record = SceneReconstruction(
        camera_node_id=camera_node_id,
        timestamp=frame_ts,
        num_gaussians=len(objects_3d) * 100,  # Approximate from objects
        num_keyframes=max(1, len(objects_3d)),
        scene_bounds=scene_bounds,
        dominant_classes=dominant_classes if dominant_classes else None,
        static_objects=static_objects if static_objects else None,
        dynamic_objects=dynamic_objects if dynamic_objects else None,
        change_events=change_events if change_events else None,
        reconstruction_quality=round(quality, 4),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    logger.info(
        "Created scene reconstruction %s for camera %s (%d objects, %d changes)",
        record.id,
        camera_node_id,
        len(objects_3d),
        len(change_events),
    )
    return record


async def compare_reconstructions(
    prev: SceneReconstruction,
    current: SceneReconstruction,
) -> list[dict]:
    """Detect changes between two reconstruction snapshots."""
    change_events: list[dict] = []

    prev_static = prev.static_objects or []
    prev_dynamic = prev.dynamic_objects or []
    current_static = current.static_objects or []
    current_dynamic = current.dynamic_objects or []

    prev_all = prev_static + prev_dynamic
    curr_all = current_static + current_dynamic

    prev_map = {o.get("track_id"): o for o in prev_all if o.get("track_id") is not None}
    curr_map = {o.get("track_id"): o for o in curr_all if o.get("track_id") is not None}

    prev_ids = set(prev_map.keys())
    curr_ids = set(curr_map.keys())

    for tid in curr_ids - prev_ids:
        obj = curr_map[tid]
        change_events.append(
            {
                "type": "object_appeared",
                "description": f"{obj['class_name']} (track {tid}) appeared in scene",
                "timestamp": current.timestamp.isoformat() if current.timestamp else None,
            }
        )

    for tid in prev_ids - curr_ids:
        obj = prev_map[tid]
        change_events.append(
            {
                "type": "object_disappeared",
                "description": f"{obj['class_name']} (track {tid}) left scene",
                "timestamp": current.timestamp.isoformat() if current.timestamp else None,
            }
        )

    for tid in prev_ids & curr_ids:
        pp = prev_map[tid]["position_3d"]
        cp = curr_map[tid]["position_3d"]
        dist = math.sqrt((pp["x"] - cp["x"]) ** 2 + (pp["y"] - cp["y"]) ** 2 + (pp["z"] - cp["z"]) ** 2)
        if dist > 1.0:
            change_events.append(
                {
                    "type": "significant_movement",
                    "description": (f"{curr_map[tid]['class_name']} (track {tid}) moved {dist:.1f}m"),
                    "timestamp": current.timestamp.isoformat() if current.timestamp else None,
                }
            )

    # Scene bounds change
    if prev.scene_bounds and current.scene_bounds:
        prev_vol = _bounds_volume(prev.scene_bounds)
        curr_vol = _bounds_volume(current.scene_bounds)
        if prev_vol > 0 and abs(curr_vol - prev_vol) / prev_vol > 0.3:
            change_events.append(
                {
                    "type": "scene_bounds_change",
                    "description": (f"Scene volume changed from {prev_vol:.1f} to {curr_vol:.1f} cubic metres"),
                    "timestamp": current.timestamp.isoformat() if current.timestamp else None,
                }
            )

    return change_events


async def get_reconstruction_history(
    db: AsyncSession,
    camera_node_id: str,
    limit: int = 20,
) -> list[SceneReconstruction]:
    """Retrieve recent scene reconstruction snapshots."""
    result = await db.execute(
        select(SceneReconstruction)
        .where(SceneReconstruction.camera_node_id == camera_node_id)
        .order_by(SceneReconstruction.timestamp.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def query_spatial(
    db: AsyncSession,
    camera_node_id: str,
    query_type: str,
    params: dict,
) -> dict:
    """Execute spatial queries against scene reconstructions.

    Supported query types:
        - objects_near_road: objects within X metres of road boundary
        - parking_areas: where vehicles typically park
        - vegetation_growth: compare vegetation masks over time
        - sightline_blockage: objects blocking camera view of road
    """
    latest_result = await db.execute(
        select(SceneReconstruction)
        .where(SceneReconstruction.camera_node_id == camera_node_id)
        .order_by(SceneReconstruction.timestamp.desc())
        .limit(1)
    )
    latest = latest_result.scalar_one_or_none()
    if latest is None:
        return {"query_type": query_type, "results": [], "message": "No reconstructions available"}

    all_objects = (latest.static_objects or []) + (latest.dynamic_objects or [])
    road_bounds = latest.scene_bounds

    if query_type == "objects_near_road":
        max_distance = params.get("max_distance_m", 5.0)
        near_road = []
        for obj in all_objects:
            pos = obj.get("position_3d", {})
            # Approximate road center as midpoint of scene bounds
            if road_bounds:
                road_cx = (float(road_bounds.get("min_x", 0)) + float(road_bounds.get("max_x", 0))) / 2
                dist = abs(float(pos.get("x", 0)) - road_cx)
                if dist <= max_distance:
                    near_road.append(
                        {
                            "track_id": obj.get("track_id"),
                            "class_name": obj.get("class_name"),
                            "distance_to_road_m": round(dist, 2),
                        }
                    )
            else:
                near_road.append(
                    {
                        "track_id": obj.get("track_id"),
                        "class_name": obj.get("class_name"),
                        "distance_to_road_m": None,
                    }
                )
        return {"query_type": "objects_near_road", "results": near_road}

    if query_type == "parking_areas":
        history = await get_reconstruction_history(db, camera_node_id, limit=50)
        vehicle_positions: list[dict] = []
        for snap in history:
            for obj in snap.static_objects or []:
                if obj.get("class_name") in ("car", "truck", "motorcycle", "vehicle"):
                    vehicle_positions.append(obj.get("position_3d", {}))

        if not vehicle_positions:
            return {"query_type": "parking_areas", "results": [], "message": "No parked vehicles found"}

        # Cluster positions (simple grid binning)
        bins: dict[tuple[int, int], int] = {}
        for pos in vehicle_positions:
            bx = int(float(pos.get("x", 0)) / 2.0)
            by = int(float(pos.get("z", 0)) / 2.0)
            bins[(bx, by)] = bins.get((bx, by), 0) + 1

        parking_areas = [
            {"center_x": round(bx * 2.0 + 1.0, 2), "center_z": round(by * 2.0 + 1.0, 2), "visit_count": cnt}
            for (bx, by), cnt in sorted(bins.items(), key=lambda x: -x[1])
            if cnt >= 2
        ]
        return {"query_type": "parking_areas", "results": parking_areas[:10]}

    if query_type == "vegetation_growth":
        history = await get_reconstruction_history(db, camera_node_id, limit=30)
        veg_counts = []
        for snap in history:
            dc = snap.dominant_classes or []
            veg_count = sum(d.get("count", 0) for d in dc if d.get("class") in ("tree", "plant", "vegetation", "grass"))
            veg_counts.append(
                {
                    "timestamp": snap.timestamp.isoformat() if snap.timestamp else None,
                    "vegetation_count": veg_count,
                }
            )

        trend = "stable"
        if len(veg_counts) >= 2:
            first_avg = sum(v["vegetation_count"] for v in veg_counts[: len(veg_counts) // 2]) / max(
                1, len(veg_counts) // 2
            )
            second_avg = sum(v["vegetation_count"] for v in veg_counts[len(veg_counts) // 2 :]) / max(
                1, len(veg_counts) - len(veg_counts) // 2
            )
            if second_avg > first_avg * 1.2:
                trend = "increasing"
            elif second_avg < first_avg * 0.8:
                trend = "decreasing"

        return {"query_type": "vegetation_growth", "trend": trend, "history": veg_counts[-10:]}

    if query_type == "sightline_blockage":
        fov_cone = params.get("fov_cone", {"center_x": 0.0, "center_z": 5.0, "half_angle_rad": 0.5})
        blocked = []
        for obj in all_objects:
            pos = obj.get("position_3d", {})
            ox = float(pos.get("x", 0))
            oz = float(pos.get("z", 0))
            cx = float(fov_cone.get("center_x", 0))
            cz = float(fov_cone.get("center_z", 5))
            dx = ox - cx
            dz = oz - cz
            dist = math.sqrt(dx * dx + dz * dz)
            if dist < 0.5:
                continue
            angle = math.atan2(abs(dx), max(dz, 0.01))
            half_angle = float(fov_cone.get("half_angle_rad", 0.5))
            if angle < half_angle and dist < abs(cz):
                blocked.append(
                    {
                        "track_id": obj.get("track_id"),
                        "class_name": obj.get("class_name"),
                        "distance_m": round(dist, 2),
                        "angle_rad": round(angle, 4),
                    }
                )
        return {"query_type": "sightline_blockage", "blocked_objects": blocked}

    return {"query_type": query_type, "error": f"Unknown query type: {query_type}"}


async def get_scene_summary(db: AsyncSession, camera_node_id: str) -> dict:
    """Return a current scene summary with counts and recent changes."""
    latest_result = await db.execute(
        select(SceneReconstruction)
        .where(SceneReconstruction.camera_node_id == camera_node_id)
        .order_by(SceneReconstruction.timestamp.desc())
        .limit(1)
    )
    latest = latest_result.scalar_one_or_none()
    if latest is None:
        return {
            "camera_node_id": camera_node_id,
            "has_reconstruction": False,
            "static_count": 0,
            "dynamic_count": 0,
            "recent_changes": [],
        }

    static_count = len(latest.static_objects or [])
    dynamic_count = len(latest.dynamic_objects or [])
    recent_changes = latest.change_events or []

    # Count total snapshots
    count_result = await db.execute(
        select(SceneReconstruction).where(SceneReconstruction.camera_node_id == camera_node_id)
    )
    total_snapshots = len(count_result.scalars().all())

    return {
        "camera_node_id": camera_node_id,
        "has_reconstruction": True,
        "reconstruction_id": latest.id,
        "timestamp": latest.timestamp.isoformat() if latest.timestamp else None,
        "static_count": static_count,
        "dynamic_count": dynamic_count,
        "total_objects": static_count + dynamic_count,
        "dominant_classes": latest.dominant_classes or [],
        "recent_changes": recent_changes[-5:],
        "scene_bounds": latest.scene_bounds,
        "reconstruction_quality": latest.reconstruction_quality,
        "total_snapshots": total_snapshots,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _bounds_volume(bounds: dict) -> float:
    """Compute approximate volume from scene bounds."""
    dx = float(bounds.get("max_x", 0)) - float(bounds.get("min_x", 0))
    dy = float(bounds.get("max_y", 0)) - float(bounds.get("min_y", 0))
    dz = float(bounds.get("max_z", 0)) - float(bounds.get("min_z", 0))
    return abs(dx * dy * dz)
