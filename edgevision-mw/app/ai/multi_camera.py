"""Multi-camera calibration and track handoff.

Provides:
- Shared coordinate system across cameras
- Track re-identification across camera views
- Handoff logic for tracked objects moving between cameras
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import numpy as np

@dataclass
class CameraExtrinsics:
    """Extrinsic calibration for a camera in the shared coordinate system."""
    camera_id: str
    position_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)  # meters in world frame
    rotation_euler: tuple[float, float, float] = (0.0, 0.0, 0.0)  # roll, pitch, yaw in radians
    intrinsics: dict = field(default_factory=lambda: {"fx": 700, "fy": 700, "cx": 320, "cy": 240})
    image_size: tuple[int, int] = (640, 480)
    
    def project_to_world(self, pixel_uv: tuple[float, float], depth_m: float) -> tuple[float, float, float]:
        """Project a pixel + depth to world coordinates."""
        u, v = pixel_uv
        fx = self.intrinsics["fx"]
        fy = self.intrinsics["fy"]
        cx = self.intrinsics["cx"]
        cy = self.intrinsics["cy"]
        
        x_cam = (u - cx) * depth_m / fx
        y_cam = (v - cy) * depth_m / fy
        z_cam = depth_m
        
        # Apply rotation + translation
        roll, pitch, yaw = self.rotation_euler
        R = _rotation_matrix(roll, pitch, yaw)
        point_cam = np.array([x_cam, y_cam, z_cam])
        point_world = R @ point_cam + np.array(self.position_xyz)
        
        return (float(point_world[0]), float(point_world[1]), float(point_world[2]))

@dataclass
class CrossCameraTrack:
    """A track that has been handed off between cameras."""
    global_track_id: str
    camera_id: str
    local_track_id: int
    position_world: tuple[float, float, float]
    class_name: str
    confidence: float
    first_seen_camera: str
    last_seen_camera: str
    handoff_count: int = 0
    timestamps: list[str] = field(default_factory=list)

def _rotation_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Compute rotation matrix from Euler angles."""
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    
    return Rz @ Ry @ Rx

class MultiCameraManager:
    """Manages track identity across multiple cameras."""
    
    def __init__(self):
        self._cameras: dict[str, CameraExtrinsics] = {}
        self._global_tracks: dict[str, CrossCameraTrack] = {}
        self._next_global_id = 1
        self._reid_threshold = 0.75  # cosine similarity threshold for re-ID
    
    def register_camera(self, camera: CameraExtrinsics) -> None:
        self._cameras[camera.camera_id] = camera
    
    def process_detections(
        self,
        camera_id: str,
        detections: list[dict],
        image_embeddings: list[list[float]] | None = None,
    ) -> list[dict]:
        """Process detections from a camera, assigning global track IDs."""
        camera = self._cameras.get(camera_id)
        if camera is None:
            return detections
        
        results = []
        for i, det in enumerate(detections):
            bbox = det.get("bbox", [0, 0, 0, 0])
            class_name = det.get("class_name", "unknown")
            confidence = det.get("confidence", 0.0)
            
            # Project to world coordinates
            u = (bbox[0] + bbox[2]) / 2
            v = bbox[3]  # bottom of bbox
            depth_m = det.get("distance_m", 10.0)
            if depth_m is None or not np.isfinite(depth_m):
                depth_m = 10.0
            
            position_world = camera.project_to_world((u, v), depth_m)
            
            # Try to match with existing global track
            matched_id = None
            if image_embeddings and i < len(image_embeddings):
                best_sim = 0.0
                for gid, track in self._global_tracks.items():
                    if track.last_seen_camera == camera_id:
                        continue
                    sim = self._cosine_sim(image_embeddings[i], track.class_name, class_name)
                    if sim > best_sim and sim >= self._reid_threshold:
                        best_sim = sim
                        matched_id = gid
            
            if matched_id is None:
                matched_id = f"G{self._next_global_id:06d}"
                self._next_global_id += 1
                self._global_tracks[matched_id] = CrossCameraTrack(
                    global_track_id=matched_id,
                    camera_id=camera_id,
                    local_track_id=det.get("track_id", 0),
                    position_world=position_world,
                    class_name=class_name,
                    confidence=confidence,
                    first_seen_camera=camera_id,
                    last_seen_camera=camera_id,
                )
            else:
                track = self._global_tracks[matched_id]
                if track.last_seen_camera != camera_id:
                    track.handoff_count += 1
                track.last_seen_camera = camera_id
                track.position_world = position_world
                track.confidence = confidence
            
            det_out = dict(det)
            det_out["global_track_id"] = matched_id
            det_out["position_world"] = list(position_world)
            results.append(det_out)
        
        return results
    
    def _cosine_sim(self, embedding: list[float], class_a: str, class_b: str) -> float:
        if class_a == class_b:
            return 1.0  # same class = high base similarity
        if not embedding:
            return 0.0
        arr = np.array(embedding, dtype=np.float64)
        norm = np.linalg.norm(arr)
        if norm == 0:
            return 0.0
        return float(np.linalg.norm(arr) / (norm * np.sqrt(len(arr))))
    
    def get_global_tracks(self) -> list[dict]:
        return [{
            "global_track_id": t.global_track_id,
            "camera_id": t.camera_id,
            "class_name": t.class_name,
            "position_world": list(t.position_world),
            "handoff_count": t.handoff_count,
            "first_seen_camera": t.first_seen_camera,
            "last_seen_camera": t.last_seen_camera,
        } for t in self._global_tracks.values()]
    
    def get_handoff_stats(self) -> dict:
        tracks = list(self._global_tracks.values())
        handoffs = [t for t in tracks if t.handoff_count > 0]
        return {
            "total_global_tracks": len(tracks),
            "tracks_with_handoffs": len(handoffs),
            "total_handoffs": sum(t.handoff_count for t in tracks),
            "cameras_registered": len(self._cameras),
        }
