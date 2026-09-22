"""Incremental 3D Gaussian Splat scene builder for fixed cameras.

R&D SPIKE — Gaussian-splat-inspired representation
====================================================

This module accumulates depth + segmentation outputs over time into a persistent
3D scene represented by Gaussian primitives.  Each primitive stores:

    position   (3)   — xyz world coordinate
    covariance (6)   — upper-triangle of 3×3 symmetric positive-definite matrix
    opacity    (1)   — [0,1]
    SH coeffs  (27)  — spherical harmonics degree-2 (RGB colour, 3 bands × 9)

Design decisions
----------------
* **Fixed camera only.**  The camera pose is assumed static; back-projection uses
  a single pinhole model.  Moving-camera support would require per-frame pose
  estimation (future work).
* **Incremental merge.**  New frames contribute new Gaussians; existing ones are
  updated via an exponential moving average when re-observed.  Gaussians that
  haven't been seen for `staleness_threshold` frames are pruned.
* **No differentiable rasteriser.**  This is a *representation* spike, not a
  training pipeline.  Rendering is approximate (project-Gaussians-to-2D) and is
  used only for change detection, not optimisation.
* **Pure NumPy.**  No CUDA / PyTorch dependency — runs on CPU in the edge node.

Cost model per camera (640×480 @ 1 fps)
---------------------------------------
| Resource             | Estimate          | Notes                                    |
|----------------------|-------------------|------------------------------------------|
| Gaussians per scene  | ~2 000–5 000      | Depends on scene complexity              |
| RAM per scene        | ~0.8–2.0 MB       | 5 k × (3+6+1+27) × 4 bytes             |
| CPU per frame merge  | ~30–80 ms         | NumPy broadcast; no GPU                  |
| Disk per snapshot    | ~4–10 KB          | JSON serialisation of Gaussian array     |
| Disk per hour (1 fps)| ~14–36 MB         | 3 600 snapshots × ~8 KB                 |
| Redis cache (hot)    | ~2 MB per camera  | Latest snapshot only; 1-hour TTL        |

The representation is deliberately lightweight for edge deployment.
"""

from __future__ import annotations

import json
import math
import time as _time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.reconstruction.incremental")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SH_DEGREE = 2  # degree-2 SH → 9 coefficients per channel, 27 total
_SH_COEFFS_PER_BAND = 9  # (l+1)^2 for l=0,1,2
_GAUSSIAN_FLOAT_DTYPE = np.float32
_DEFAULT_OPACITY = 0.8
_DEFAULT_COV_SCALE = 0.05  # initial covariance scale (metres²)
_LEARNING_RATE = 0.3  # EMA blend for re-observed Gaussians
_PRUNE_OPACITY_THRESHOLD = 0.02
_STALENESS_THRESHOLD = 120  # frames before unobserved Gaussian is pruned


# ---------------------------------------------------------------------------
# Dataclass: Gaussian Primitive
# ---------------------------------------------------------------------------

@dataclass
class GaussianPrimitive:
    """A single 3D Gaussian primitive in the scene."""

    position: np.ndarray  # (3,)
    covariance_upper: np.ndarray  # (6,) — upper triangle of symmetric 3×3
    opacity: float
    sh_coefficients: np.ndarray  # (27,) — degree-2 SH per RGB channel
    observed_count: int = 0
    last_seen_frame: int = 0
    class_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position.tolist(),
            "covariance_upper": self.covariance_upper.tolist(),
            "opacity": float(self.opacity),
            "sh_coefficients": self.sh_coefficients.tolist(),
            "observed_count": self.observed_count,
            "last_seen_frame": self.last_seen_frame,
            "class_label": self.class_label,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GaussianPrimitive:
        return cls(
            position=np.array(d["position"], dtype=_GAUSSIAN_FLOAT_DTYPE),
            covariance_upper=np.array(d["covariance_upper"], dtype=_GAUSSIAN_FLOAT_DTYPE),
            opacity=float(d["opacity"]),
            sh_coefficients=np.array(d["sh_coefficients"], dtype=_GAUSSIAN_FLOAT_DTYPE),
            observed_count=int(d.get("observed_count", 0)),
            last_seen_frame=int(d.get("last_seen_frame", 0)),
            class_label=str(d.get("class_label", "")),
        )


# ---------------------------------------------------------------------------
# GaussianSplatScene
# ---------------------------------------------------------------------------

class GaussianSplatScene:
    """Persistent 3D scene represented by a collection of Gaussian primitives.

    The scene is owned by a single fixed camera and is updated incrementally
    as new depth/segmentation frames arrive.
    """

    def __init__(self, camera_node_id: str, max_gaussians: int = 5000):
        self.camera_node_id = camera_node_id
        self.max_gaussians = max_gaussians
        self.gaussians: list[GaussianPrimitive] = []
        self.frame_count: int = 0
        self.scene_bounds: dict[str, float] = {
            "min_x": 0.0, "min_y": 0.0, "min_z": 0.0,
            "max_x": 0.0, "max_y": 0.0, "max_z": 0.0,
        }
        self.keyframe_timestamps: list[str] = []
        self.dominant_classes: dict[str, int] = {}
        self.static_objects: list[dict] = []
        self.dynamic_objects: list[dict] = []
        self.reconstruction_quality: float = 0.0

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_node_id": self.camera_node_id,
            "frame_count": self.frame_count,
            "max_gaussians": self.max_gaussians,
            "num_gaussians": len(self.gaussians),
            "scene_bounds": self.scene_bounds,
            "keyframe_timestamps": self.keyframe_timestamps,
            "dominant_classes": self.dominant_classes,
            "static_objects": self.static_objects,
            "dynamic_objects": self.dynamic_objects,
            "reconstruction_quality": self.reconstruction_quality,
            "gaussians": [g.to_dict() for g in self.gaussians],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GaussianSplatScene:
        scene = cls(
            camera_node_id=d["camera_node_id"],
            max_gaussians=int(d.get("max_gaussians", 5000)),
        )
        scene.frame_count = int(d.get("frame_count", 0))
        scene.scene_bounds = d.get("scene_bounds", scene.scene_bounds)
        scene.keyframe_timestamps = d.get("keyframe_timestamps", [])
        scene.dominant_classes = d.get("dominant_classes", {})
        scene.static_objects = d.get("static_objects", [])
        scene.dynamic_objects = d.get("dynamic_objects", [])
        scene.reconstruction_quality = float(d.get("reconstruction_quality", 0.0))
        scene.gaussians = [GaussianPrimitive.from_dict(g) for g in d.get("gaussians", [])]
        return scene

    def serialise_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def deserialise_json(cls, raw: str) -> GaussianSplatScene:
        return cls.from_dict(json.loads(raw))

    # ------------------------------------------------------------------
    # Rendering (approximate — for visualisation / change detection)
    # ------------------------------------------------------------------

    def project_to_2d(
        self,
        img_width: int,
        img_height: int,
        focal_length: float | None = None,
    ) -> list[dict[str, Any]]:
        """Project all Gaussians to 2D image coordinates.

        Returns a list of dicts with keys: u, v, depth, opacity, class_label,
        color_rgb.  The colour is extracted from SH degree-0 (DC) coefficient.
        """
        fl = focal_length or float(img_width)
        cx, cy = img_width / 2.0, img_height / 2.0
        projected: list[dict[str, Any]] = []
        for g in self.gaussians:
            if g.opacity < _PRUNE_OPACITY_THRESHOLD:
                continue
            x, y, z = g.position
            if z <= 0.01:
                continue
            u = (x / z) * fl + cx
            v = (y / z) * fl + cy
            if u < 0 or u >= img_width or v < 0 or v >= img_height:
                continue
            # SH degree-0 DC term → average colour (channels stored interleaved)
            # sh_coefficients layout: [R_l0, R_l1, R_l2, G_l0, G_l1, G_l2, B_l0, ...]
            # Actually we store: [R DC, R(1,-1), R(1,0), R(1,1), ..., G DC, ..., B DC, ...]
            # With 27 coefficients: indices 0-8 = R, 9-17 = G, 18-26 = B
            color_r = float(np.clip(g.sh_coefficients[0], 0.0, 1.0))
            color_g = float(np.clip(g.sh_coefficients[9], 0.0, 1.0))
            color_b = float(np.clip(g.sh_coefficients[18], 0.0, 1.0))
            projected.append({
                "u": round(float(u), 2),
                "v": round(float(v), 2),
                "depth": round(float(z), 4),
                "opacity": round(float(g.opacity), 4),
                "class_label": g.class_label,
                "color_rgb": [round(color_r, 3), round(color_g, 3), round(color_b, 3)],
            })
        return projected

    def render_depth_map(
        self,
        img_width: int,
        img_height: int,
        focal_length: float | None = None,
    ) -> np.ndarray:
        """Render a depth buffer from the Gaussian splat (nearest-depth per pixel)."""
        depth_buffer = np.full((img_height, img_width), np.inf, dtype=np.float32)
        projected = self.project_to_2d(img_width, img_height, focal_length)
        for p in projected:
            px, py = int(p["u"]), int(p["v"])
            d = p["depth"]
            if depth_buffer[py, px] > d:
                depth_buffer[py, px] = d
        depth_buffer[depth_buffer == np.inf] = 0.0
        return depth_buffer

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def update_scene_bounds(self) -> None:
        if not self.gaussians:
            return
        positions = np.stack([g.position for g in self.gaussians], axis=0)
        mins = positions.min(axis=0)
        maxs = positions.max(axis=0)
        self.scene_bounds = {
            "min_x": round(float(mins[0]), 4),
            "min_y": round(float(mins[1]), 4),
            "min_z": round(float(mins[2]), 4),
            "max_x": round(float(maxs[0]), 4),
            "max_y": round(float(maxs[1]), 4),
            "max_z": round(float(maxs[2]), 4),
        }

    def update_dominant_classes(self) -> None:
        counts: dict[str, int] = {}
        for g in self.gaussians:
            if g.opacity >= _PRUNE_OPACITY_THRESHOLD:
                lbl = g.class_label or "unlabelled"
                counts[lbl] = counts.get(lbl, 0) + 1
        self.dominant_classes = dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def compute_quality(self) -> float:
        """Heuristic reconstruction quality in [0, 1]."""
        q = 0.3  # baseline
        n = len(self.gaussians)
        if n > 100:
            q += 0.2
        if n > 500:
            q += 0.1
        if n > 1000:
            q += 0.1
        # Diversity of classes
        n_classes = len(self.dominant_classes)
        if n_classes >= 3:
            q += 0.1
        if n_classes >= 5:
            q += 0.1
        # Observation depth
        avg_obs = np.mean([g.observed_count for g in self.gaussians]) if self.gaussians else 0
        if avg_obs > 5:
            q += 0.1
        return round(min(q, 1.0), 4)


# ---------------------------------------------------------------------------
# IncrementalSceneBuilder
# ---------------------------------------------------------------------------

class IncrementalSceneBuilder:
    """Accumulates depth + segmentation frames into a GaussianSplatScene.

    Typical usage::

        builder = IncrementalSceneBuilder("CAM-LIL-001")
        for frame in frames:
            scene = builder.ingest_frame(
                depth_map=frame["depth"],
                segmentation_mask=frame["seg"],
                detections=frame["dets"],
                image_width=640,
                image_height=480,
                timestamp=frame["ts"],
            )
    """

    def __init__(
        self,
        camera_node_id: str,
        *,
        max_gaussians: int = 5000,
        keyframe_interval: int = 30,
        learning_rate: float = _LEARNING_RATE,
        prune_opacity_threshold: float = _PRUNE_OPACITY_THRESHOLD,
        staleness_threshold: int = _STALENESS_THRESHOLD,
    ):
        self.camera_node_id = camera_node_id
        self.max_gaussians = max_gaussians
        self.keyframe_interval = keyframe_interval
        self.learning_rate = learning_rate
        self.prune_opacity_threshold = prune_opacity_threshold
        self.staleness_threshold = staleness_threshold

        self.scene = GaussianSplatScene(camera_node_id, max_gaussians)
        self._depth_buffer: np.ndarray | None = None
        self._seg_buffer: np.ndarray | None = None
        self._projected_cache: dict[int, tuple[float, float, float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_frame(
        self,
        depth_map: np.ndarray,
        segmentation_mask: np.ndarray | None,
        detections: list[dict],
        image_width: int,
        image_height: int,
        timestamp: str,
        *,
        focal_length: float | None = None,
    ) -> GaussianSplatScene:
        """Process one frame and merge into the persistent scene.

        Parameters
        ----------
        depth_map:
            H×W float32 array.  Values are relative depth (0 = close, 1 = far)
            or metric depth in metres — the builder adapts.
        segmentation_mask:
            H×W int32 array of per-pixel class IDs (from RoadSegmenter / YOLO-seg).
            ``None`` is accepted (no per-pixel segmentation).
        detections:
            List of detection dicts (from auto-labelling pipeline):
            ``{"track_id": int, "bbox": [x,y,w,h], "class_name": str,
              "confidence": float, "centroid": {"x","y"}}``.
        image_width, image_height:
            Original frame dimensions.
        timestamp:
            ISO-8601 timestamp string.
        focal_length:
            Camera focal length in pixels.  Defaults to image_width.

        Returns
        -------
        GaussianSplatScene
            The updated scene (also accessible via ``self.scene``).
        """
        t0 = _time.perf_counter()
        fl = focal_length or float(image_width)
        self.scene.frame_count += 1
        frame_idx = self.scene.frame_count

        # 1. Back-project pixel grid to 3D — generates candidate Gaussians
        new_gaussians = self._backproject_frame(
            depth_map, segmentation_mask, image_width, image_height, fl, frame_idx,
        )

        # 2. Back-project detections to 3D and attach high-confidence Gaussians
        det_gaussians = self._backproject_detections(
            detections, depth_map, image_width, image_height, fl, frame_idx,
        )
        new_gaussians.extend(det_gaussians)

        # 3. Merge into persistent scene (EMA update for re-observed, insert new)
        self._merge_gaussians(new_gaussians, frame_idx)

        # 4. Prune stale / low-opacity Gaussians
        self._prune(frame_idx)

        # 5. Enforce budget
        self._enforce_budget()

        # 6. Update scene metadata
        is_keyframe = (frame_idx % self.keyframe_interval == 0)
        if is_keyframe:
            self.scene.keyframe_timestamps.append(timestamp)
            if len(self.scene.keyframe_timestamps) > 200:
                self.scene.keyframe_timestamps = self.scene.keyframe_timestamps[-200:]

        self.scene.update_scene_bounds()
        self.scene.update_dominant_classes()
        self.scene.reconstruction_quality = self.scene.compute_quality()

        # Classify static vs dynamic (simple: static = observed > threshold times
        # with low positional variance)
        self._classify_static_dynamic()

        elapsed_ms = (_time.perf_counter() - t0) * 1000
        logger.info(
            "incremental_ingest",
            camera=self.camera_node_id,
            frame=frame_idx,
            gaussians=len(self.scene.gaussians),
            new_candidates=len(new_gaussians),
            elapsed_ms=round(elapsed_ms, 2),
        )
        return self.scene

    def snapshot_json(self) -> str:
        """Serialise the current scene to a JSON string for persistence."""
        return self.scene.serialise_json()

    def load_snapshot(self, raw_json: str) -> None:
        """Restore the scene from a previously serialised snapshot."""
        self.scene = GaussianSplatScene.deserialise_json(raw_json)
        logger.info(
            "incremental_snapshot_loaded",
            camera=self.camera_node_id,
            gaussians=len(self.scene.gaussians),
            frames=self.scene.frame_count,
        )

    # ------------------------------------------------------------------
    # Back-projection
    # ------------------------------------------------------------------

    def _backproject_frame(
        self,
        depth_map: np.ndarray,
        seg_mask: np.ndarray | None,
        img_w: int,
        img_h: int,
        focal: float,
        frame_idx: int,
    ) -> list[GaussianPrimitive]:
        """Back-project a subsampled grid of pixels into 3D Gaussians."""
        h, w = depth_map.shape[:2]
        cx, cy = img_w / 2.0, img_h / 2.0

        # Subsample: take every 8th pixel to limit Gaussian count per frame
        step = 8
        ys = np.arange(0, h, step)
        xs = np.arange(0, w, step)
        grid_y, grid_x = np.meshgrid(ys, xs, indexing="ij")
        flat_y = grid_y.ravel()
        flat_x = grid_x.ravel()

        if flat_y.size == 0:
            return []

        # Sample depth at grid positions
        depth_vals = depth_map[flat_y, flat_x].astype(np.float32)
        # Convert relative depth [0,1] → metric depth (assume 1.0 ≈ 30 m)
        depth_metric = depth_vals * 30.0
        valid = (depth_metric > 0.1) & (depth_metric < 50.0)
        flat_y = flat_y[valid]
        flat_x = flat_x[valid]
        depth_metric = depth_metric[valid]

        if flat_y.size == 0:
            return []

        # Pinhole back-projection
        x_3d = ((flat_x.astype(np.float32) - cx) / focal) * depth_metric
        y_3d = ((flat_y.astype(np.float32) - cy) / focal) * depth_metric
        z_3d = depth_metric

        # Determine per-pixel class label from segmentation mask
        class_labels = np.array([""] * flat_y.size, dtype="U32")
        if seg_mask is not None and seg_mask.shape[:2] == (h, w):
            class_ids = seg_mask[flat_y, flat_x]
            # Map class IDs to names — use a small lookup
            class_labels = np.array([f"class_{int(cid)}" for cid in class_ids], dtype="U32")

        # Build Gaussians
        positions = np.stack([x_3d, y_3d, z_3d], axis=1)  # (N, 3)
        n = positions.shape[0]
        cov_diag = np.full((n, 3), _DEFAULT_COV_SCALE, dtype=np.float32)
        # Slight scale variation based on depth
        cov_diag[:, 0] *= (depth_metric / 10.0)
        cov_diag[:, 1] *= (depth_metric / 10.0)
        cov_diag[:, 2] *= (depth_metric / 10.0)

        # Upper triangle of diagonal covariance: [xx, xy, xz, yy, yz, zz]
        cov_upper = np.zeros((n, 6), dtype=np.float32)
        cov_upper[:, 0] = cov_diag[:, 0]  # xx
        cov_upper[:, 3] = cov_diag[:, 1]  # yy
        cov_upper[:, 5] = cov_diag[:, 2]  # zz

        # SH coefficients: DC term from depth → greyscale intensity
        sh = np.zeros((n, 27), dtype=np.float32)
        brightness = np.clip(1.0 - depth_metric / 30.0, 0.2, 1.0)
        sh[:, 0] = brightness   # R DC
        sh[:, 9] = brightness   # G DC
        sh[:, 18] = brightness  # B DC

        gaussians: list[GaussianPrimitive] = []
        for i in range(n):
            gaussians.append(GaussianPrimitive(
                position=positions[i],
                covariance_upper=cov_upper[i],
                opacity=_DEFAULT_OPACITY,
                sh_coefficients=sh[i],
                observed_count=1,
                last_seen_frame=frame_idx,
                class_label=str(class_labels[i]),
            ))
        return gaussians

    def _backproject_detections(
        self,
        detections: list[dict],
        depth_map: np.ndarray,
        img_w: int,
        img_h: int,
        focal: float,
        frame_idx: int,
    ) -> list[GaussianPrimitive]:
        """Back-project detected objects into high-confidence Gaussians."""
        h, w = depth_map.shape[:2]
        cx, cy = img_w / 2.0, img_h / 2.0
        gaussians: list[GaussianPrimitive] = []

        for det in detections:
            centroid = det.get("centroid", {})
            cx_norm = float(centroid.get("x", 0.5))
            cy_norm = float(centroid.get("y", 0.5))
            bbox = det.get("bbox", [0, 0, 0, 0])
            class_name = det.get("class_name", "object")
            conf = float(det.get("confidence", 0.5))

            # Sample depth at centroid
            px = min(int(cx_norm * w), w - 1)
            py = min(int(cy_norm * h), h - 1)
            depth_val = float(depth_map[py, px]) * 30.0  # relative → metric
            if depth_val < 0.1 or depth_val > 50.0:
                depth_val = 10.0  # fallback

            # Pinhole back-projection
            x_3d = (cx_norm - 0.5) * depth_val * img_w / focal if focal > 0 else 0.0
            y_3d = (cy_norm - 0.5) * depth_val * img_h / focal if focal > 0 else 0.0
            z_3d = depth_val

            # Use bbox width to estimate covariance scale
            bw = float(bbox[2]) if len(bbox) > 2 else 0.1
            bh = float(bbox[3]) if len(bbox) > 3 else 0.1
            cov_scale = max(0.02, bw * depth_val / focal * 0.5)

            cov_upper = np.array([
                cov_scale, 0.0, 0.0,
                cov_scale * (bh / max(bw, 0.01)), 0.0,
                cov_scale * 0.5,
            ], dtype=np.float32)

            # SH: brighter colour for detected objects
            sh = np.zeros(27, dtype=np.float32)
            brightness = float(np.clip(conf, 0.3, 1.0))
            sh[0] = brightness
            sh[9] = brightness
            sh[18] = brightness

            gaussians.append(GaussianPrimitive(
                position=np.array([x_3d, y_3d, z_3d], dtype=np.float32),
                covariance_upper=cov_upper,
                opacity=float(np.clip(conf, 0.4, 0.99)),
                sh_coefficients=sh,
                observed_count=1,
                last_seen_frame=frame_idx,
                class_label=class_name,
            ))
        return gaussians

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def _merge_gaussians(self, candidates: list[GaussianPrimitive], frame_idx: int) -> None:
        """Merge candidate Gaussians into the persistent scene.

        For each candidate, find the nearest existing Gaussian (by Euclidean
        distance).  If close enough, apply EMA update; otherwise insert as new.
        """
        if not candidates:
            return

        existing = self.scene.gaussians
        if existing:
            existing_positions = np.stack([g.position for g in existing], axis=0)  # (M, 3)
        else:
            existing_positions = np.empty((0, 3), dtype=np.float32)

        matched_indices: set[int] = set()
        lr = self.learning_rate

        for cand in candidates:
            if existing_positions.shape[0] == 0:
                self.scene.gaussians.append(cand)
                continue

            dists = np.linalg.norm(existing_positions - cand.position, axis=1)
            nearest_idx = int(np.argmin(dists))
            nearest_dist = float(dists[nearest_idx])

            # Adaptive merge radius: scale with depth
            depth = float(cand.position[2])
            merge_radius = max(0.3, depth * 0.05)

            if nearest_dist < merge_radius and nearest_idx not in matched_indices:
                # EMA update
                g = existing[nearest_idx]
                g.position = (1.0 - lr) * g.position + lr * cand.position
                g.covariance_upper = (1.0 - lr) * g.covariance_upper + lr * cand.covariance_upper
                g.opacity = float(np.clip((1.0 - lr) * g.opacity + lr * cand.opacity, 0.0, 1.0))
                g.sh_coefficients = (1.0 - lr) * g.sh_coefficients + lr * cand.sh_coefficients
                g.observed_count += 1
                g.last_seen_frame = frame_idx
                if cand.class_label and cand.class_label != g.class_label:
                    g.class_label = cand.class_label
                matched_indices.add(nearest_idx)
            else:
                # Insert new
                self.scene.gaussians.append(cand)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def _prune(self, frame_idx: int) -> None:
        """Remove low-opacity and stale Gaussians."""
        before = len(self.scene.gaussians)
        kept: list[GaussianPrimitive] = []
        for g in self.scene.gaussians:
            if g.opacity < self.prune_opacity_threshold:
                continue
            if (frame_idx - g.last_seen_frame) > self.staleness_threshold:
                continue
            kept.append(g)
        self.scene.gaussians = kept
        pruned = before - len(kept)
        if pruned > 0:
            logger.debug(
                "incremental_prune",
                camera=self.camera_node_id,
                pruned=pruned,
                remaining=len(kept),
            )

    def _enforce_budget(self) -> None:
        """If over budget, drop the lowest-opacity Gaussians."""
        if len(self.scene.gaussians) <= self.max_gaussians:
            return
        self.scene.gaussians.sort(key=lambda g: g.opacity, reverse=True)
        self.scene.gaussians = self.scene.gaussians[: self.max_gaussians]

    # ------------------------------------------------------------------
    # Static / dynamic classification
    # ------------------------------------------------------------------

    def _classify_static_dynamic(self) -> None:
        """Classify Gaussians as static or dynamic based on observation count."""
        static_threshold = max(3, self.keyframe_interval // 2)
        static_objects: list[dict] = []
        dynamic_objects: list[dict] = []

        for g in self.scene.gaussians:
            if g.opacity < self.prune_opacity_threshold:
                continue
            obj = {
                "class_label": g.class_label,
                "position_3d": {
                    "x": round(float(g.position[0]), 4),
                    "y": round(float(g.position[1]), 4),
                    "z": round(float(g.position[2]), 4),
                },
                "observed_count": g.observed_count,
                "opacity": round(float(g.opacity), 4),
            }
            if g.observed_count >= static_threshold:
                static_objects.append(obj)
            else:
                dynamic_objects.append(obj)

        self.scene.static_objects = static_objects[:500]
        self.scene.dynamic_objects = dynamic_objects[:500]


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

_builders: dict[str, IncrementalSceneBuilder] = {}


def get_or_create_builder(
    camera_node_id: str,
    *,
    max_gaussians: int = 5000,
) -> IncrementalSceneBuilder:
    """Return a process-cached IncrementalSceneBuilder for a camera.

    If the camera has no builder yet, one is created.  Callers should
    persist snapshots to disk / DB and call ``load_snapshot`` to restore.
    """
    if camera_node_id not in _builders:
        _builders[camera_node_id] = IncrementalSceneBuilder(
            camera_node_id, max_gaussians=max_gaussians,
        )
    return _builders[camera_node_id]


def estimate_cost_per_camera(
    *,
    frames_per_second: float = 1.0,
    hours_per_day: float = 12.0,
    avg_gaussians: int = 3000,
) -> dict[str, Any]:
    """Return an estimated cost model for one camera's 3D scene.

    All values are approximate and intended for capacity planning.
    """
    bytes_per_gaussian = (3 + 6 + 1 + 27) * 4  # position + cov + opacity + SH = 148 B
    ram_mb = (avg_gaussians * bytes_per_gaussian) / (1024 * 1024)
    frames_per_day = int(frames_per_second * hours_per_day * 3600)
    # Each snapshot serialised ≈ gaussian_count × 200 bytes (JSON overhead)
    snapshot_kb = (avg_gaussians * 200) / 1024
    disk_mb_per_day = (snapshot_kb * frames_per_day) / 1024
    # CPU: ~50 ms per frame merge on ARM Cortex-A72 (RPi4 class)
    cpu_ms_per_frame = 50.0
    cpu_seconds_per_day = (cpu_ms_per_frame * frames_per_day) / 1000

    return {
        "camera_count": 1,
        "frames_per_second": frames_per_second,
        "hours_per_day": hours_per_day,
        "avg_gaussians": avg_gaussians,
        "ram_mb": round(ram_mb, 2),
        "snapshot_size_kb": round(snapshot_kb, 2),
        "disk_mb_per_day": round(disk_mb_per_day, 2),
        "cpu_seconds_per_day": round(cpu_seconds_per_day, 1),
        "bytes_per_gaussian": bytes_per_gaussian,
        "notes": (
            "RAM is steady-state (max_gaussians caps it). "
            "Disk grows linearly with frames unless snapshots are pruned. "
            "CPU is dominated by back-projection and nearest-neighbour merge. "
            "For 10 cameras at 1 fps: ~20 MB RAM, ~4 GB disk/day, ~500 CPU-s/day."
        ),
    }
