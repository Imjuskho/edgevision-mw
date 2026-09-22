"""Structured event logging and observability for the perception pipeline.

Provides:
- Structured event logs with detection confidence, tracker IDs, segmentation results
- False-alert debugging support
- Performance metrics per pipeline stage
- Event correlation across frames
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from collections import deque
import time
import numpy as np

@dataclass
class PerceptionLogEntry:
    """A structured log entry for a perception pipeline frame."""
    timestamp: str
    frame_index: int
    camera_node_id: str
    detections_count: int
    tracks_active: int
    detections: list[dict]  # [{class_name, confidence, track_id, distance_m, bbox}]
    events_fired: list[dict]  # [{event_type, rule_id, track_id, confidence}]
    segmentation: dict | None = None  # {road_ratio, classes_found}
    depth_stats: dict | None = None  # {min_m, max_m, avg_m}
    pipeline_ms: float = 0.0
    inference_ms: float = 0.0
    tracking_ms: float = 0.0
    events_ms: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "frame_index": self.frame_index,
            "camera_node_id": self.camera_node_id,
            "detections_count": self.detections_count,
            "tracks_active": self.tracks_active,
            "detections": self.detections[:20],  # cap for storage
            "events_fired": self.events_fired,
            "segmentation": self.segmentation,
            "depth_stats": self.depth_stats,
            "pipeline_ms": round(self.pipeline_ms, 2),
            "inference_ms": round(self.inference_ms, 2),
            "tracking_ms": round(self.tracking_ms, 2),
            "events_ms": round(self.events_ms, 2),
        }

class PerceptionLogger:
    """Structured logger for the perception pipeline."""
    
    def __init__(self, camera_node_id: str = "default", max_history: int = 500):
        self.camera_node_id = camera_node_id
        self._history: deque[PerceptionLogEntry] = deque(maxlen=max_history)
        self._frame_index = 0
        self._alert_history: deque[dict] = deque(maxlen=100)
        self._false_alert_suspects: deque[dict] = deque(maxlen=50)
    
    def log_frame(
        self,
        detections: list[dict],
        events: list[dict],
        segmentation: dict | None = None,
        depth_stats: dict | None = None,
        pipeline_ms: float = 0.0,
        inference_ms: float = 0.0,
        tracking_ms: float = 0.0,
        events_ms: float = 0.0,
    ) -> PerceptionLogEntry:
        entry = PerceptionLogEntry(
            timestamp=datetime.now(UTC).isoformat(),
            frame_index=self._frame_index,
            camera_node_id=self.camera_node_id,
            detections_count=len(detections),
            tracks_active=len([d for d in detections if d.get("track_id")]),
            detections=[{
                "class_name": d.get("class_name", "unknown"),
                "confidence": round(d.get("confidence", 0), 4),
                "track_id": d.get("track_id"),
                "distance_m": d.get("distance_m"),
                "bbox": [round(v, 2) for v in (d.get("bbox") or [0,0,0,0])[:4]],
            } for d in detections[:50]],
            events_fired=[{
                "event_type": e.get("event_type", ""),
                "rule_id": e.get("rule_id", ""),
                "track_id": e.get("track_id"),
                "confidence": round(e.get("confidence", 0), 4),
            } for e in events],
            segmentation=segmentation,
            depth_stats=depth_stats,
            pipeline_ms=pipeline_ms,
            inference_ms=inference_ms,
            tracking_ms=tracking_ms,
            events_ms=events_ms,
        )
        self._history.append(entry)
        self._frame_index += 1
        
        # Track alerts for false-alert debugging
        for evt in events:
            if evt.get("alert"):
                self._alert_history.append({
                    "timestamp": entry.timestamp,
                    "frame_index": self._frame_index,
                    **evt,
                })
        
        return entry
    
    def log_false_alert_suspect(self, event_id: str, reason: str, details: dict | None = None) -> None:
        self._false_alert_suspects.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "event_id": event_id,
            "reason": reason,
            "details": details or {},
        })
    
    def get_recent_entries(self, count: int = 50) -> list[dict]:
        return [e.to_dict() for e in list(self._history)[-count:]]
    
    def get_alert_history(self, count: int = 50) -> list[dict]:
        return list(self._alert_history)[-count:]
    
    def get_false_alert_suspects(self) -> list[dict]:
        return list(self._false_alert_suspects)
    
    def get_performance_stats(self) -> dict:
        if not self._history:
            return {"avg_pipeline_ms": 0, "avg_inference_ms": 0, "avg_tracking_ms": 0, "avg_events_ms": 0, "total_frames": 0}
        entries = list(self._history)
        return {
            "avg_pipeline_ms": round(np.mean([e.pipeline_ms for e in entries]), 2),
            "avg_inference_ms": round(np.mean([e.inference_ms for e in entries]), 2),
            "avg_tracking_ms": round(np.mean([e.tracking_ms for e in entries]), 2),
            "avg_events_ms": round(np.mean([e.events_ms for e in entries]), 2),
            "total_frames": len(entries),
            "avg_detections_per_frame": round(np.mean([e.detections_count for e in entries]), 2),
            "avg_tracks_per_frame": round(np.mean([e.tracks_active for e in entries]), 2),
        }
    
    def get_detection_distribution(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self._history:
            for det in entry.detections:
                cls = det.get("class_name", "unknown")
                counts[cls] = counts.get(cls, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
