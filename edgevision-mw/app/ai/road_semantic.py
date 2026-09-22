"""Semantic road-scene analysis on top of road surface instance segmentation.

The road ONNX model emits *instance* masks for seven surface classes
(``good_road``, ``pothole``, ``crack``, ``dust_road``, ``gravel_road``,
``road_marking``, ``shoulder``).  This module fuses those instances into a
*semantic* scene:

* drivable surface — union of paved/unpaved road + marking masks
* hazards — potholes and cracks, with per-hazard contact distance
* sidewalk / curb — geometric boundary heuristics (no trained classes)
* road-edge distance — forward free-space to the end of the drivable region,
  converted to meters with the flat-ground metric calibration
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.ai.metric_depth import CameraCalibration, ground_plane_distance_m
from app.core.logging import get_logger

logger = get_logger("edgevision.road_semantic")

DRIVABLE_CLASS_IDS = frozenset({0, 3, 4, 5})  # good_road, dust_road, gravel_road, road_marking
HAZARD_CLASS_IDS = frozenset({1, 2})  # pothole, crack
BOUNDARY_CLASS_IDS = frozenset({6})  # shoulder

DRIVABLE_NAMES = frozenset({"good_road", "dust_road", "gravel_road", "road_marking"})
HAZARD_NAMES = frozenset({"pothole", "crack"})
BOUNDARY_NAMES = frozenset({"shoulder"})

_SIDE_BAND = 0.25  # outer quarter of the frame width used for sidewalk/curb bands
_CENTER_BAND = (0.3, 0.7)
_BOUNDARY_STD_PX = 18.0
_MIN_CENTER_COVERAGE = 0.25


def decode_mask_rle(mask_rle: str | None, shape: tuple[int, int]) -> np.ndarray | None:
    """Decode a pycocotools RLE counts string to a bool mask."""
    if not mask_rle:
        return None
    try:
        from pycocotools import mask as mask_utils

        rle = {"size": [int(shape[0]), int(shape[1])], "counts": str(mask_rle).encode("ascii")}
        decoded = mask_utils.decode(rle)
        return decoded.astype(bool)
    except Exception:
        return None


@dataclass
class RoadSceneAnalysis:
    has_road: bool
    drivable_ratio: float = 0.0
    drivable_class_ids: list[int] = field(default_factory=list)
    hazards: list[dict] = field(default_factory=list)
    sidewalk_present: bool = False
    sidewalk_regions: list[dict] = field(default_factory=list)
    curb_present: bool = False
    curb_method: str = "not_detected"
    road_continuous_fraction: float = 0.0
    road_edge_distance_m: float | None = None
    road_edge_quality: str = "no_drivable_region"
    mask_quality: str = "none"
    method: str = "instance_fusion"

    def to_dict(self) -> dict:
        return {
            "has_road": self.has_road,
            "drivable_ratio": round(self.drivable_ratio, 4),
            "drivable_class_ids": sorted(self.drivable_class_ids),
            "hazards": self.hazards,
            "sidewalk_present": self.sidewalk_present,
            "sidewalk_regions": self.sidewalk_regions,
            "curb_present": self.curb_present,
            "curb_method": self.curb_method,
            "road_continuous_fraction": round(self.road_continuous_fraction, 4),
            "road_edge_distance_m": round(self.road_edge_distance_m, 3)
            if self.road_edge_distance_m is not None
            else None,
            "road_edge_quality": self.road_edge_quality,
            "mask_quality": self.mask_quality,
            "method": self.method,
        }


def _get(inst, name: str, default=None):
    if isinstance(inst, dict):
        return inst.get(name, default)
    return getattr(inst, name, default)


def _merge_mask_quality(current: str, incoming: str) -> str:
    """Aggregate mask quality across instances: any bbox_fill degrades to bbox_fill."""
    if incoming == "bbox_fill":
        return "bbox_fill"
    if incoming == "rle":
        return current if current == "bbox_fill" else "rle"
    return current


def _as_mask(inst, image_shape: tuple[int, int]) -> tuple[np.ndarray | None, str]:
    mask = decode_mask_rle(_get(inst, "mask_rle"), image_shape)
    if mask is not None:
        return mask, "rle"
    bbox = _get(inst, "bbox")
    if not bbox:
        return None, "none"
    h, w = image_shape[:2]
    x1, y1, bw, bh = [float(v) for v in bbox[:4]]
    mask = np.zeros((h, w), dtype=bool)
    x1i, x2i = max(0, int(x1 * w)), min(w, int((x1 + bw) * w))
    y1i, y2i = max(0, int(y1 * h)), min(h, int((y1 + bh) * h))
    if x2i > x1i and y2i > y1i:
        mask[y1i:y2i, x1i:x2i] = True
    return mask, "bbox_fill"


def _road_boundary(
    drivable: np.ndarray,
    lower: int,
) -> tuple[float, int | None]:
    """Return ``(continuous_fraction, boundary_row)`` for the center band.

    ``continuous_fraction`` is the share of center-band columns whose drivable
    region reaches the image bottom (road continues out of frame).  When some
    columns end early, ``boundary_row`` is the closest (minimum) row where the
    drivable region ends — the forward road edge.
    """
    h, w = drivable.shape
    c0, c1 = max(0, int(_CENTER_BAND[0] * w)), min(w, int(_CENTER_BAND[1] * w))
    if c1 <= c0:
        return 0.0, None
    band = drivable[:, c0:c1]
    col_max = np.zeros(c1 - c0, dtype=int)
    for i in range(c1 - c0):
        col = band[:, i]
        rows = np.nonzero(col)[0]
        col_max[i] = rows[-1] if rows.size else -1
    active = col_max >= 0
    if not active.any():
        return 0.0, None
    continuous = np.count_nonzero(active & (col_max >= h - 1)) / (c1 - c0)
    finite = col_max[active & (col_max < h - 1)]
    boundary_row = int(finite.min()) if finite.size else None
    return float(continuous), boundary_row


def _detect_boundary_structures(
    drivable: np.ndarray,
    lower: int,
) -> tuple[bool, bool, str, list[dict]]:
    """Geometric sidewalk/curb heuristics from the drivable mask.

    Sidewalk: an outer quarter-width band below the horizon that is mostly
    non-drivable while the center band is mostly drivable.
    Curb: the leftmost/rightmost drivable boundary columns are stable across
    rows (a near-vertical edge) with non-drivable area outside.
    """
    h, w = drivable.shape
    if lower >= h:
        return False, False, "not_detected", []
    low = drivable[lower:, :]

    left_w = max(1, int(_SIDE_BAND * w))
    center_mean = float(low[:, int(_CENTER_BAND[0] * w) : int(_CENTER_BAND[1] * w)].mean()) if w > 2 else 0.0
    has_road = center_mean >= _MIN_CENTER_COVERAGE

    sidewalk_present = False
    sidewalk_regions: list[dict] = []
    if has_road:
        left_cov = float(low[:, :left_w].mean()) if left_w else 0.0
        right_cov = float(low[:, -left_w:].mean()) if left_w else 0.0
        for side, cov in (("left", left_cov), ("right", right_cov)):
            if cov < _MIN_CENTER_COVERAGE:
                sidewalk_present = True
                sidewalk_regions.append(
                    {"side": side, "coverage": round(cov, 4), "method": "geometric_boundary"}
                )

    curb_present = False
    if has_road:
        leftmost = np.full(h - lower, -1, dtype=int)
        rightmost = np.full(h - lower, -1, dtype=int)
        for j, row in enumerate(low):
            cols = np.nonzero(row)[0]
            if cols.size:
                leftmost[j] = cols[0]
                rightmost[j] = cols[-1]
        valid = leftmost >= 0
        if valid.sum() >= 8:
            lm = leftmost[valid]
            rm = rightmost[valid]
            left_ok = float(np.std(lm)) <= _BOUNDARY_STD_PX and (lm.mean() > 0 or float(np.std(lm)) < 4)
            right_ok = float(np.std(rm)) <= _BOUNDARY_STD_PX and (rm.mean() < w - 1 or float(np.std(rm)) < 4)
            if left_ok and right_ok:
                curb_present = True
    curb_method = "geometric_boundary" if curb_present else "not_detected"
    return sidewalk_present, curb_present, curb_method, sidewalk_regions


def analyze_road_scene(
    instances: list,
    image_shape: tuple[int, int],
    metric_map: np.ndarray | None = None,
    calibration: CameraCalibration | None = None,
) -> RoadSceneAnalysis:
    """Build a semantic road scene from instance segmentation results."""
    cal = calibration or CameraCalibration()
    h, w = image_shape[:2]
    lower = max(0, min(h - 1, int(cal.horizon_row(h))))

    drivable = np.zeros((h, w), dtype=bool)
    has_road = False
    drivable_ids: set[int] = set()
    hazards: list[dict] = []
    mask_quality = "none"

    for inst in instances:
        cid = _get(inst, "class_id")
        cname = _get(inst, "class_name")
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            cid = None
        if cid in DRIVABLE_CLASS_IDS or (cname and cname in DRIVABLE_NAMES):
            mask, quality = _as_mask(inst, image_shape)
            if mask is not None:
                drivable |= mask
                has_road = True
                drivable_ids.add(cid if cid is not None else -1)
                mask_quality = _merge_mask_quality(mask_quality, quality)
        elif cid in HAZARD_CLASS_IDS or (cname and cname in HAZARD_NAMES):
            mask, quality = _as_mask(inst, image_shape)
            if mask is not None:
                rows = np.nonzero(mask.any(axis=1))[0]
                bottom_row = int(rows[-1]) if rows.size else 0
                dist = None
                if metric_map is not None:
                    row = min(h - 1, bottom_row)
                    value = float(metric_map[row, w // 2])
                    dist = round(value, 3) if np.isfinite(value) else None
                hazards.append(
                    {
                        "class_id": cid,
                        "class_name": cname or "",
                        "confidence": _get(inst, "confidence"),
                        "bbox": _get(inst, "bbox"),
                        "contact_row": bottom_row,
                        "distance_m": dist,
                        "distance_quality": "metric_ground_plane" if dist is not None else "unavailable",
                        "mask_quality": quality,
                    }
                )

    drivable_ratio = 0.0
    road_continuous_fraction = 0.0
    road_edge_distance_m = None
    road_edge_quality = "no_drivable_region" if not has_road else "no_metric_map"

    if has_road:
        if lower < h:
            drivable_ratio = float(drivable[lower:, :].mean())
        road_continuous_fraction, boundary_row = _road_boundary(drivable, lower)
        if boundary_row is not None:
            if metric_map is not None:
                row = min(h - 1, boundary_row)
                value = float(metric_map[row, w // 2])
                if np.isfinite(value):
                    road_edge_distance_m = value
                    road_edge_quality = "metric_ground_plane"
            else:
                distance = ground_plane_distance_m(boundary_row, h, cal)
                if np.isfinite(distance):
                    road_edge_distance_m = distance
                    road_edge_quality = "calibration_ground_plane"
        else:
            road_edge_quality = "road_continuous"

    sidewalk_present, curb_present, curb_method, sidewalk_regions = _detect_boundary_structures(
        drivable, lower
    )

    return RoadSceneAnalysis(
        has_road=has_road,
        drivable_ratio=drivable_ratio,
        drivable_class_ids=sorted(drivable_ids),
        hazards=hazards,
        sidewalk_present=sidewalk_present,
        sidewalk_regions=sidewalk_regions,
        curb_present=curb_present,
        curb_method=curb_method,
        road_continuous_fraction=road_continuous_fraction,
        road_edge_distance_m=road_edge_distance_m,
        road_edge_quality=road_edge_quality,
        mask_quality=mask_quality,
    )
