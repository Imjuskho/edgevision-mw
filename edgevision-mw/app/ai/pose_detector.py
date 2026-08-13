from __future__ import annotations

import cv2
import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.pose_detection")

COCO_KEYPOINTS = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]

COCO_SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (11, 12), (5, 11), (6, 12), (11, 13), (13, 15),
    (12, 14), (14, 16),
]


def _try_ultralytics_pose(image: np.ndarray, conf_threshold: float = 0.3) -> list[dict] | None:
    try:
        import importlib
        if importlib.util.find_spec("ultralytics") is None:
            return None
        import os

        from ultralytics import YOLO
        model_path = os.path.expanduser("~/.cache/edgevision/yolov8n-pose.pt")
        if not os.path.exists(model_path):
            return None
        model = YOLO(model_path)
        results = model.predict(image, conf=conf_threshold, verbose=False)
    except Exception:
        return None

    poses = []
    for result in results:
        if result.keypoints is None:
            continue
        kps_data = result.keypoints.data
        if kps_data is None or len(kps_data) == 0:
            continue
        for person_kps in kps_data:
            keypoints = []
            for i, kp in enumerate(person_kps):
                x, y, conf = float(kp[0]), float(kp[1]), float(kp[2])
                name = COCO_KEYPOINTS[i] if i < len(COCO_KEYPOINTS) else f"kp_{i}"
                keypoints.append({
                    "keypoint": name,
                    "x": int(x) if x > 0 else 0,
                    "y": int(y) if y > 0 else 0,
                    "confidence": round(float(conf), 4),
                })
            mean_conf = float(np.mean([k["confidence"] for k in keypoints]))
            poses.append({"keypoints": keypoints, "confidence": round(mean_conf, 4)})

    return poses


def _detect_poses_simple(image: np.ndarray) -> list[dict]:
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    skin_lower = np.array([0, 20, 70], dtype=np.uint8)
    skin_upper = np.array([20, 150, 255], dtype=np.uint8)
    skin_mask = cv2.inRange(hsv, skin_lower, skin_upper)
    skin_mask = cv2.erode(skin_mask, None, iterations=1)
    skin_mask = cv2.dilate(skin_mask, None, iterations=2)
    contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h, w = image.shape[:2]
    poses = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        area = bw * bh
        if area < w * h * 0.02 or area > w * h * 0.95:
            continue
        aspect = bw / max(bh, 1)
        if aspect < 0.2 or aspect > 2.0:
            continue

        cx, cy = x + bw // 2, y + bh // 2
        keypoints = [
            {"keypoint": name, "x": cx, "y": cy, "confidence": 0.0}
            for name in COCO_KEYPOINTS
        ]
        poses.append({"keypoints": keypoints, "confidence": 0.3, "fallback": True})

    return poses


def detect_poses(image: np.ndarray, conf_threshold: float = 0.3) -> list[dict]:
    ultralytics_result = _try_ultralytics_pose(image, conf_threshold)
    if ultralytics_result is not None:
        return ultralytics_result
    return _detect_poses_simple(image)
