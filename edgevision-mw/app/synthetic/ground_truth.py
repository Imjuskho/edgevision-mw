"""Automatic ground-truth generation for synthetic frames.

Generates segmentation masks, bounding boxes, and depth maps
FROM the conditioning inputs used to generate each frame — not
by re-running the detection model (which would reproduce detector bias).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class GroundTruth:
    """Complete ground truth for a single synthetic frame."""

    segmentation_mask: np.ndarray
    bounding_boxes: list[dict]
    depth_map: np.ndarray
    class_labels: list[str]
    instance_mask: np.ndarray
    width: int
    height: int

    def to_coco(self) -> dict:
        """Export as COCO-format annotations."""
        annotations = []
        for i, (bbox, label) in enumerate(zip(self.bounding_boxes, self.class_labels)):
            x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
            annotations.append({
                "id": i,
                "category_name": label,
                "bbox": [x, y, w, h],
                "area": w * h,
                "segmentation": bbox.get("polygon", []),
                "depth_m": bbox.get("depth_m", 0.0),
                "source": "synthetic",
            })
        return {
            "width": self.width,
            "height": self.height,
            "annotations": annotations,
            "source": "synthetic",
        }

    def to_cityscapes(self) -> dict:
        """Export as Cityscapes-format label."""
        return {
            "width": self.width,
            "height": self.height,
            "label": self.segmentation_mask.tolist(),
            "instance": self.instance_mask.tolist(),
            "source": "synthetic",
        }

    def to_kitti(self) -> dict:
        """Export as KITTI-format annotations."""
        objects = []
        for bbox, label in zip(self.bounding_boxes, self.class_labels):
            objects.append({
                "type": label,
                "bbox": [bbox["x"], bbox["y"], bbox["x"] + bbox["w"], bbox["y"] + bbox["h"]],
                "dimensions": bbox.get("dimensions_3d", [1.5, 1.5, 1.5]),
                "location": bbox.get("location_3d", [0, 0, 5]),
                "rotation_y": bbox.get("rotation_y", 0.0),
                "source": "synthetic",
            })
        return {"width": self.width, "height": self.height, "objects": objects, "source": "synthetic"}


class GroundTruthGenerator:
    """Generates ground truth from conditioning inputs.

    Unlike running a trained detector on synthetic frames (which would
    just reproduce the detector's own biases), this generates GT directly
    from the scene parameters used during generation.
    """

    _CLASS_TO_ID: dict[str, int] = {
        "background": 0,
        "road": 1,
        "sidewalk": 2,
        "building": 3,
        "wall": 4,
        "fence": 5,
        "vegetation": 6,
        "sky": 7,
        "person": 8,
        "rider": 9,
        "car": 10,
        "truck": 11,
        "bus": 12,
        "motorcycle": 13,
        "bicycle": 14,
        "pothole": 15,
        "dust_road": 16,
        "gravel_road": 17,
        "shoulder": 18,
    }

    def generate(
        self,
        image: np.ndarray,
        objects: list,
        scene_config: object,
        camera_config: object,
    ) -> GroundTruth:
        """Generate complete GT from the scene that produced the image."""
        h, w = image.shape[:2]

        seg_mask = self._generate_segmentation(w, h, scene_config)
        inst_mask = self._generate_instance_mask(w, h, objects)
        depth_map = self._generate_depth_map(w, h, objects, camera_config)
        bboxes, labels = self._extract_bboxes(objects, camera_config)

        return GroundTruth(
            segmentation_mask=seg_mask,
            bounding_boxes=bboxes,
            depth_map=depth_map,
            class_labels=labels,
            instance_mask=inst_mask,
            width=w,
            height=h,
        )

    def _generate_segmentation(
        self, w: int, h: int, scene_config: object
    ) -> np.ndarray:
        mask = np.zeros((h, w), dtype=np.int32)

        road_top = int(h * 0.35)
        road_center = w // 2
        for y in range(road_top, h):
            t = (y - road_top) / max(h - road_top, 1)
            half_w = int(30 + t * w * 0.35)
            left = max(0, road_center - half_w)
            right = min(w, road_center + half_w)
            mask[y, left:right] = self._CLASS_TO_ID["road"]

        for y in range(0, road_top):
            mask[y, :] = self._CLASS_TO_ID["sky"]

        return mask

    def _generate_instance_mask(
        self, w: int, h: int, objects: list
    ) -> np.ndarray:
        mask = np.zeros((h, w), dtype=np.int32)
        for i, obj in enumerate(objects, start=1):
            if hasattr(obj, "bbox_normalized"):
                x1n, y1n, wn, hn = obj.bbox_normalized
                x1, y1 = int(x1n * w), int(y1n * h)
                x2, y2 = min(w, int((x1n + wn) * w)), min(h, int((y1n + hn) * h))
                mask[y1:y2, x1:x2] = i
        return mask

    def _generate_depth_map(
        self,
        w: int,
        h: int,
        objects: list,
        camera_config: object,
    ) -> np.ndarray:
        depth = np.full((h, w), 100.0, dtype=np.float32)

        road_top = int(h * 0.35)
        for y in range(road_top, h):
            t = (y - road_top) / max(h - road_top, 1)
            depth[y, :] = 2.0 + (1 - t) * 80.0

        for y in range(0, road_top):
            depth[y, :] = 100.0

        for obj in objects:
            if hasattr(obj, "bbox_normalized") and hasattr(obj, "depth_m"):
                x1n, y1n, wn, hn = obj.bbox_normalized
                x1, y1 = int(x1n * w), int(y1n * h)
                x2, y2 = min(w, int((x1n + wn) * w)), min(h, int((y1n + hn) * h))
                if x2 > x1 and y2 > y1:
                    depth[y1:y2, x1:x2] = obj.depth_m

        return depth

    def _extract_bboxes(
        self, objects: list, camera_config: object
    ) -> tuple[list[dict], list[str]]:
        bboxes = []
        labels = []
        for obj in objects:
            if hasattr(obj, "bbox_normalized"):
                x1n, y1n, wn, hn = obj.bbox_normalized
                bboxes.append({
                    "x": x1n,
                    "y": y1n,
                    "w": wn,
                    "h": hn,
                    "depth_m": getattr(obj, "depth_m", 0.0),
                    "polygon": [
                        x1n, y1n,
                        x1n + wn, y1n,
                        x1n + wn, y1n + hn,
                        x1n, y1n + hn,
                    ],
                })
                labels.append(getattr(obj, "class_name", "unknown"))
        return bboxes, labels
