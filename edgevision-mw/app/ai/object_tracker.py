from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from app.core.logging import get_logger
from app.models.enums import ModelType

logger = get_logger("edgevision.object_tracker")


def iou(a: np.ndarray, b: np.ndarray) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class TrackState:
    TENTATIVE = 0
    CONFIRMED = 1
    DELETED = 2


@dataclass
class TrackConfig:
    track_high_thresh: float = 0.5
    track_low_thresh: float = 0.1
    confirm_hits: int = 3
    iou_threshold: float = 0.3
    cross_class_penalty: float = 0.5
    reid_threshold: float = 0.75
    confidence_window: int = 8
    alert_on_threshold: float = 0.65
    alert_off_threshold: float = 0.45
    max_age: dict[str, int] = field(default_factory=lambda: {"default": 15})


TRACK_CONFIGS: dict[str, TrackConfig] = {
    ModelType.object_detection.value: TrackConfig(
        max_age={"person": 12, "pedestrian": 12, "car": 15, "default": 10},
    ),
    ModelType.road_segmentation.value: TrackConfig(
        max_age={"road": 20, "default": 15},
        iou_threshold=0.25,
    ),
    ModelType.agri_crop_classification.value: TrackConfig(
        max_age={"plant": 25, "default": 20},
        iou_threshold=0.25,
    ),
    ModelType.agri_health_classification.value: TrackConfig(
        max_age={"plant": 25, "default": 20},
        iou_threshold=0.25,
    ),
}


def get_track_config(model_type: str | ModelType | None) -> TrackConfig:
    key = model_type.value if isinstance(model_type, ModelType) else (model_type or "object_detection")
    return TRACK_CONFIGS.get(key, TrackConfig())


class KalmanBBox:
    """Constant-velocity Kalman filter for bbox [cx, cy, w, h]."""

    def __init__(self, bbox: np.ndarray):
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        w = max(1.0, bbox[2] - bbox[0])
        h = max(1.0, bbox[3] - bbox[1])
        self._state = np.array([cx, cy, w, h, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
        self._P = np.eye(8, dtype=np.float64) * 10.0
        self._Q = np.diag([1.0, 1.0, 0.5, 0.5, 2.0, 2.0, 0.5, 0.5])
        self._R = np.diag([4.0, 4.0, 2.0, 2.0])

    def predict(self) -> np.ndarray:
        F = np.eye(8)
        F[0, 4] = 1.0
        F[1, 5] = 1.0
        F[2, 6] = 1.0
        F[3, 7] = 1.0
        self._state = F @ self._state
        self._P = F @ self._P @ F.T + self._Q
        return self.get_bbox()

    def update(self, bbox: np.ndarray) -> None:
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        w = max(1.0, bbox[2] - bbox[0])
        h = max(1.0, bbox[3] - bbox[1])
        z = np.array([cx, cy, w, h], dtype=np.float64)
        H = np.zeros((4, 8))
        H[0, 0] = H[1, 1] = H[2, 2] = H[3, 3] = 1.0
        y = z - H @ self._state
        S = H @ self._P @ H.T + self._R
        K = self._P @ H.T @ np.linalg.inv(S)
        self._state = self._state + K @ y
        self._P = (np.eye(8) - K @ H) @ self._P

    def get_bbox(self) -> np.ndarray:
        cx, cy, w, h = self._state[:4]
        w = max(1.0, w)
        h = max(1.0, h)
        return np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], dtype=np.float64)


class Track:
    def __init__(
        self,
        track_id: int,
        bbox: np.ndarray,
        class_name: str,
        confidence: float,
        *,
        mask: list | None = None,
        mask_format: str | None = None,
        config: TrackConfig | None = None,
    ):
        self.track_id = track_id
        self.class_name = class_name
        self._config = config or TrackConfig()
        self.state = TrackState.TENTATIVE
        self.hits = 1
        self.no_loss_coast = 0
        self.age = 0
        self.kf = KalmanBBox(bbox)
        self.bbox = bbox.copy()
        self.mask = mask
        self.mask_format = mask_format
        self._embedding: list[float] | None = None
        window = max(1, self._config.confidence_window)
        self._confidence_history: deque[float] = deque(maxlen=window)
        self.confidence = confidence
        self.smoothed_confidence = confidence
        self.alert_active = False
        self._apply_confidence_smoothing(confidence)

    def predict(self) -> None:
        self.age += 1
        self.bbox = self.kf.predict()

    def update(
        self,
        bbox: np.ndarray,
        confidence: float,
        embedding: list[float] | None = None,
        *,
        mask: list | None = None,
        mask_format: str | None = None,
    ) -> None:
        self.kf.update(bbox)
        self.bbox = bbox.copy()
        self._apply_confidence_smoothing(confidence)
        self.hits += 1
        self.no_loss_coast = 0
        if embedding is not None:
            self._embedding = embedding
        if mask is not None:
            self.mask = mask
            self.mask_format = mask_format
        if self.state == TrackState.TENTATIVE and self.hits >= 3:
            self.state = TrackState.CONFIRMED

    def mark_missed(self, max_age: int) -> None:
        self.no_loss_coast += 1
        if self.no_loss_coast > max_age:
            self.state = TrackState.DELETED

    @property
    def embedding(self) -> list[float] | None:
        return self._embedding

    def _apply_confidence_smoothing(self, confidence: float) -> None:
        self.confidence = confidence
        self._confidence_history.append(confidence)
        self.smoothed_confidence = sum(self._confidence_history) / len(self._confidence_history)
        if self.alert_active:
            if self.smoothed_confidence < self._config.alert_off_threshold:
                self.alert_active = False
        elif self.smoothed_confidence >= self._config.alert_on_threshold:
            self.alert_active = True


def _hungarian(cost: np.ndarray) -> list[tuple[int, int]]:
    """Optimal assignment; scipy if available, else pure-Python Munkres."""
    if cost.size == 0:
        return []
    try:
        from scipy.optimize import linear_sum_assignment

        row, col = linear_sum_assignment(cost)
        return list(zip(row.tolist(), col.tolist(), strict=False))
    except ImportError:
        return _hungarian_greedy(cost)


def _hungarian_greedy(cost: np.ndarray) -> list[tuple[int, int]]:
    """Fallback: iteratively pick minimum cost pairs."""
    n_rows, n_cols = cost.shape
    used_rows: set[int] = set()
    used_cols: set[int] = set()
    pairs: list[tuple[int, int]] = []
    flat = [(cost[r, c], r, c) for r in range(n_rows) for c in range(n_cols)]
    flat.sort(key=lambda x: x[0])
    for _, r, c in flat:
        if r in used_rows or c in used_cols:
            continue
        pairs.append((r, c))
        used_rows.add(r)
        used_cols.add(c)
        if len(used_rows) == n_rows or len(used_cols) == n_cols:
            break
    return pairs


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


class ByteTrack:
    def __init__(
        self,
        track_high_thresh: float = 0.5,
        track_low_thresh: float = 0.1,
        config: TrackConfig | None = None,
        model_type: str | ModelType | None = None,
    ):
        self._config = config or get_track_config(model_type)
        self._track_high_thresh = track_high_thresh or self._config.track_high_thresh
        self._track_low_thresh = track_low_thresh or self._config.track_low_thresh
        self._next_id = 1
        self._tracks: list[Track] = []
        self._clip = None

    def _get_max_age(self, class_name: str) -> int:
        return self._config.max_age.get(class_name, self._config.max_age.get("default", 15))

    def _get_clip(self):
        if self._clip is None:
            try:
                from app.ai.clip_embedder import CLIPEmbedder

                self._clip = CLIPEmbedder()
            except Exception:
                self._clip = False
        return self._clip if self._clip is not False else None

    def update(
        self,
        detections: list[dict],
        image: np.ndarray | None = None,
    ) -> list[dict]:
        for t in self._tracks:
            t.predict()

        high_dets = [d for d in detections if d.get("confidence", 0) >= self._track_high_thresh]
        low_dets = [d for d in detections if self._track_low_thresh <= d.get("confidence", 0) < self._track_high_thresh]

        confirmed = [t for t in self._tracks if t.state in (TrackState.CONFIRMED, TrackState.TENTATIVE)]

        matched_tracks, unmatched_dets = self._match(confirmed, high_dets, image)
        unmatched_tracks = [i for i in range(len(confirmed)) if i not in matched_tracks]

        matched_low, _ = self._match(
            [confirmed[i] for i in unmatched_tracks],
            low_dets,
            image,
            track_indices=unmatched_tracks,
        )

        for i, t in enumerate(confirmed):
            if i in matched_tracks:
                det = high_dets[matched_tracks[i]]
                emb = self._det_embedding(det, image)
                t.update(
                    np.array(det["bbox"]),
                    det.get("confidence", 0.5),
                    emb,
                    mask=det.get("mask"),
                    mask_format=det.get("mask_format"),
                )
            elif i in matched_low:
                det = low_dets[matched_low[i]]
                emb = self._det_embedding(det, image)
                t.update(
                    np.array(det["bbox"]),
                    det.get("confidence", 0.3),
                    emb,
                    mask=det.get("mask"),
                    mask_format=det.get("mask_format"),
                )
            else:
                t.mark_missed(self._get_max_age(t.class_name))

        for i in unmatched_dets:
            det = high_dets[i]
            bbox = np.array(det["bbox"])
            track = Track(
                track_id=self._next_id,
                bbox=bbox,
                class_name=det.get("class_name", "object"),
                confidence=det.get("confidence", 0.5),
                mask=det.get("mask"),
                mask_format=det.get("mask_format"),
                config=self._config,
            )
            emb = self._det_embedding(det, image)
            if emb is not None:
                track._embedding = emb
            self._tracks.append(track)
            self._next_id += 1

        self._tracks = [t for t in self._tracks if t.state != TrackState.DELETED]

        outputs = []
        for t in self._tracks:
            if t.state != TrackState.DELETED:
                out = {
                    "track_id": t.track_id,
                    "bbox": t.bbox.tolist(),
                    "class_name": t.class_name,
                    "confidence": t.confidence,
                    "smoothed_confidence": t.smoothed_confidence,
                    "alert_active": t.alert_active,
                    "hits": t.hits,
                    "age": t.age,
                }
                if t.mask is not None:
                    out["mask"] = t.mask
                    out["mask_format"] = t.mask_format
                outputs.append(out)
        return outputs

    def _det_embedding(self, det: dict, image: np.ndarray | None) -> list[float] | None:
        if image is None:
            return None
        clip = self._get_clip()
        if clip is None or not clip.is_loaded():
            return None
        try:
            x1, y1, x2, y2 = (int(v) for v in det["bbox"])
            h, w = image.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return None
            crop = image[y1:y2, x1:x2]
            return clip.embed(crop)
        except Exception:
            return None

    def _match(
        self,
        tracks: list[Track],
        detections: list[dict],
        image: np.ndarray | None = None,
        track_indices: list[int] | None = None,
    ) -> tuple[dict[int, int], list[int]]:
        if not tracks or not detections:
            return {}, list(range(len(detections)))

        n_t = len(tracks)
        n_d = len(detections)
        cost = np.ones((n_t, n_d), dtype=np.float64)

        for i, t in enumerate(tracks):
            for j, det in enumerate(detections):
                iou_val = iou(t.bbox, np.array(det["bbox"]))
                if det.get("class_name") != t.class_name:
                    iou_val *= self._config.cross_class_penalty
                cost[i, j] = 1.0 - iou_val

        pairs = _hungarian(cost)
        matched: dict[int, int] = {}
        matched_det_indices: set[int] = set()

        for row, col in pairs:
            iou_val = 1.0 - cost[row, col]
            if iou_val >= self._config.iou_threshold:
                key = track_indices[row] if track_indices is not None else row
                matched[key] = col
                matched_det_indices.add(col)

        # ReID fallback for unmatched coasting tracks
        if image is not None:
            clip = self._get_clip()
            if clip is not None and clip.is_loaded():
                unmatched_tracks = [
                    (track_indices[i] if track_indices else i, tracks[i])
                    for i in range(n_t)
                    if (track_indices[i] if track_indices else i) not in matched
                    and tracks[i].no_loss_coast > 0
                    and tracks[i].embedding is not None
                ]
                for t_idx, track in unmatched_tracks:
                    best_j = -1
                    best_sim = 0.0
                    for j, det in enumerate(detections):
                        if j in matched_det_indices:
                            continue
                        if det.get("class_name") != track.class_name:
                            continue
                        emb = self._det_embedding(det, image)
                        if emb is None:
                            continue
                        sim = _cosine_similarity(track.embedding or [], emb)
                        if sim > best_sim and sim >= self._config.reid_threshold:
                            best_sim = sim
                            best_j = j
                    if best_j >= 0:
                        matched[t_idx] = best_j
                        matched_det_indices.add(best_j)

        unmatched_dets = [j for j in range(n_d) if j not in matched_det_indices]
        return matched, unmatched_dets

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1
