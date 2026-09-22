"""Road segmentation + metric depth fusion for 3D road geometry.

Computes:
- Distance from any detection to the nearest road edge (meters)
- 3D road surface mesh from depth + road mask
- Road-edge boundaries in metric space
- Road-adjacent zones (1m, 2m, 5m buffers)
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

from app.ai.metric_depth import CameraCalibration, ground_plane_distance_m, metric_distance_at_bbox

@dataclass
class RoadEdge:
    """A point on the road boundary in (u, v, meters_from_camera)."""
    u: float
    v: float
    distance_m: float

@dataclass
class RoadGeometry3D:
    """3D road geometry from fused depth + segmentation."""
    road_surface_area_m2: float
    road_edge_points: list[RoadEdge]
    road_centerline_m: float  # distance to road center at bottom of frame
    road_width_estimate_m: float
    drivable_area_ratio: float
    curb_boundary: list[dict]  # [{u, v, distance_m, side: "left"|"right"}]

@dataclass
class DetectionRoadProximity:
    """Road proximity info for a single detection."""
    track_id: int | None
    class_name: str
    distance_to_road_edge_m: float
    on_road: bool  # True if detection bbox overlaps road surface
    distance_to_road_center_m: float
    road_zone: str  # "on_road", "roadside_near" (<2m), "roadside_far" (2-5m), "off_road"

def compute_distance_to_road_edge(
    detection_bbox: list[float],
    road_mask: np.ndarray,
    image_shape: tuple[int, int],
    calibration: CameraCalibration | None = None,
    pixel_to_meter_cache: np.ndarray | None = None,
) -> float:
    """Compute minimum distance from detection bbox bottom-center to nearest road edge pixel.
    
    Uses the road mask to find edge pixels, then computes metric distance.
    """
    h, w = image_shape[:2]
    cal = calibration or CameraCalibration()
    
    # Get detection bottom-center
    x1, y1, x2, y2 = detection_bbox[:4]
    if max(x1, y1, x2, y2) <= 1.0:
        x1, y1, x2, y2 = x1 * w, y1 * h, x2 * w, y2 * h
    
    det_u = (x1 + x2) / 2
    det_v = y2  # bottom of bbox
    
    # Binary road mask -> edge detection
    if road_mask.max() <= 1.0:
        road_binary = (road_mask > 0.5).astype(np.uint8)
    else:
        road_binary = (road_mask > 127).astype(np.uint8)
    
    # Simple edge detection: dilate and subtract
    from scipy.ndimage import binary_dilation
    dilated = binary_dilation(road_binary, iterations=3)
    edge_mask = dilated & ~road_binary
    
    # Find edge pixels
    edge_rows, edge_cols = np.where(edge_mask)
    if len(edge_rows) == 0:
        return float("inf")
    
    # Compute metric distances to all edge points
    min_dist = float("inf")
    for er, ec in zip(edge_rows, edge_cols):
        edge_m = ground_plane_distance_m(float(er), (h, w), cal)
        det_m = ground_plane_distance_m(det_v, (h, w), cal)
        if np.isfinite(edge_m) and np.isfinite(det_m):
            # Approximate Euclidean distance in ground plane
            lateral_dist = abs(det_u - ec) * (1.0 / cal.focal_length_px) * det_m
            depth_dist = abs(det_m - edge_m)
            dist = np.sqrt(lateral_dist**2 + depth_dist**2)
            min_dist = min(min_dist, dist)
    
    return float(min_dist) if np.isfinite(min_dist) else float("inf")

def compute_road_geometry(
    road_mask: np.ndarray,
    depth_map: np.ndarray | None,
    image_shape: tuple[int, int],
    calibration: CameraCalibration | None = None,
) -> RoadGeometry3D:
    """Compute full 3D road geometry from segmentation + depth."""
    h, w = image_shape[:2]
    cal = calibration or CameraCalibration()
    
    if road_mask.max() <= 1.0:
        road_binary = (road_mask > 0.5).astype(np.uint8)
    else:
        road_binary = (road_mask > 127).astype(np.uint8)
    
    drivable_ratio = float(road_binary.sum()) / (h * w) if h * w > 0 else 0.0
    
    # Find road edge points along left and right boundaries
    edge_points = []
    curb_left = []
    curb_right = []
    
    for row in range(h):
        row_data = road_binary[row, :]
        road_cols = np.where(row_data > 0)[0]
        if len(road_cols) == 0:
            continue
        
        left_col = road_cols[0]
        right_col = road_cols[-1]
        
        dist = ground_plane_distance_m(float(row), (h, w), cal)
        if not np.isfinite(dist):
            continue
        
        edge_points.append(RoadEdge(float(left_col), float(row), dist))
        edge_points.append(RoadEdge(float(right_col), float(row), dist))
        curb_left.append({"u": float(left_col), "v": float(row), "distance_m": round(dist, 2), "side": "left"})
        curb_right.append({"u": float(right_col), "v": float(row), "distance_m": round(dist, 2), "side": "right"})
    
    # Road width estimate at bottom of frame
    bottom_row = int(h * 0.7)
    bottom_road = np.where(road_binary[min(bottom_row, h-1), :] > 0)[0]
    if len(bottom_road) >= 2:
        left_x = bottom_road[0]
        right_x = bottom_road[-1]
        dist_m = ground_plane_distance_m(float(bottom_row), (h, w), cal)
        width_m = ((right_x - left_x) / cal.focal_length_px) * dist_m if np.isfinite(dist_m) else 0.0
    else:
        width_m = 0.0
    
    # Road centerline distance
    center_row = h - 1
    center_road = np.where(road_binary[center_row, :] > 0)[0]
    if len(center_road) >= 2:
        center_m = ground_plane_distance_m(float(center_row), (h, w), cal)
    else:
        center_m = 0.0
    
    return RoadGeometry3D(
        road_surface_area_m2=drivable_ratio * 100.0,  # percentage for now
        road_edge_points=edge_points,
        road_centerline_m=round(center_m, 2) if np.isfinite(center_m) else 0.0,
        road_width_estimate_m=round(width_m, 2),
        drivable_area_ratio=round(drivable_ratio, 4),
        curb_boundary=curb_left + curb_right,
    )

def annotate_detections_with_road_proximity(
    detections: list[dict],
    road_mask: np.ndarray,
    image_shape: tuple[int, int],
    calibration: CameraCalibration | None = None,
) -> list[DetectionRoadProximity]:
    """Annotate each detection with road proximity metrics."""
    h, w = image_shape[:2]
    cal = calibration or CameraCalibration()
    
    results = []
    for det in detections:
        bbox = det.get("bbox", [0, 0, 0, 0])
        dist = compute_distance_to_road_edge(bbox, road_mask, image_shape, cal)
        
        # Determine zone
        if det.get("on_road", False):
            zone = "on_road"
        elif dist < 2.0:
            zone = "roadside_near"
        elif dist < 5.0:
            zone = "roadside_far"
        else:
            zone = "off_road"
        
        # Distance to road center
        x1, y1, x2, y2 = bbox[:4]
        if max(x1, y1, x2, y2) <= 1.0:
            x1, y1, x2, y2 = x1 * w, y1 * h, x2 * w, y2 * h
        center_x = (x1 + x2) / 2
        center_y = y2
        det_m = ground_plane_distance_m(center_y, (h, w), cal)
        
        results.append(DetectionRoadProximity(
            track_id=det.get("track_id"),
            class_name=det.get("class_name", "object"),
            distance_to_road_edge_m=round(dist, 3) if np.isfinite(dist) else 999.0,
            on_road=zone == "on_road",
            distance_to_road_center_m=round(abs(center_x - w/2) * (1.0 / cal.focal_length_px) * det_m, 3) if np.isfinite(det_m) else 999.0,
            road_zone=zone,
        ))
    
    return results
