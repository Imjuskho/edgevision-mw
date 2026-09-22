"""Data flywheel: collect edge-case frames back into the labeling queue.

Captures:
- Missed detections (frames where tracker lost an object)
- False positives (alerts that were later suppressed)
- Low-confidence detections
- Anomaly events
- Class confusion events
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import numpy as np
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger_text = __name__

@dataclass
class EdgeCase:
    """An edge-case frame identified for human review."""
    id: str
    case_type: str  # "missed_detection", "false_positive", "low_confidence", "anomaly", "class_confusion"
    severity: str  # "high", "medium", "low"
    frame_timestamp: str
    camera_node_id: str
    image_path: str | None = None
    detection_data: dict | None = None
    tracker_data: dict | None = None
    description: str = ""
    sent_to_labeling: bool = False
    labeling_status: str = "pending"  # "pending", "in_review", "completed"
    created_at: str = ""

@dataclass
class FlywheelStats:
    """Statistics about the data flywheel."""
    total_edge_cases: int
    by_type: dict[str, int]
    by_severity: dict[str, int]
    pending_labeling: int
    in_review: int
    completed: int
    collection_rate_per_hour: float

class DataFlywheel:
    """Collects edge-case frames for the labeling queue."""
    
    def __init__(self, max_buffer: int = 1000):
        self._buffer: list[EdgeCase] = []
        self._max_buffer = max_buffer
        self._hourly_counts: list[tuple[str, int]] = []  # (hour, count)
    
    def collect_missed_detection(
        self,
        camera_node_id: str,
        frame_timestamp: str,
        lost_track_id: int,
        last_known_class: str,
        last_confidence: float,
        image_path: str | None = None,
    ) -> EdgeCase:
        case = EdgeCase(
            id=uuid4().hex,
            case_type="missed_detection",
            severity="high" if last_confidence > 0.6 else "medium",
            frame_timestamp=frame_timestamp,
            camera_node_id=camera_node_id,
            image_path=image_path,
            tracker_data={"lost_track_id": lost_track_id, "last_class": last_known_class, "last_confidence": last_confidence},
            description=f"Track {lost_track_id} ({last_known_class}) lost at confidence {last_confidence:.2f}",
            created_at=datetime.now(UTC).isoformat(),
        )
        self._add(case)
        return case
    
    def collect_false_positive(
        self,
        camera_node_id: str,
        frame_timestamp: str,
        event_id: str,
        rule_id: str,
        suppression_reason: str,
        detection_data: dict | None = None,
        image_path: str | None = None,
    ) -> EdgeCase:
        case = EdgeCase(
            id=uuid4().hex,
            case_type="false_positive",
            severity="medium",
            frame_timestamp=frame_timestamp,
            camera_node_id=camera_node_id,
            image_path=image_path,
            detection_data=detection_data,
            description=f"Alert {event_id} (rule={rule_id}) suppressed: {suppression_reason}",
            created_at=datetime.now(UTC).isoformat(),
        )
        self._add(case)
        return case
    
    def collect_low_confidence(
        self,
        camera_node_id: str,
        frame_timestamp: str,
        detection: dict,
        confidence_threshold: float = 0.3,
        image_path: str | None = None,
    ) -> EdgeCase | None:
        conf = detection.get("confidence", 0)
        if conf >= confidence_threshold:
            return None
        case = EdgeCase(
            id=uuid4().hex,
            case_type="low_confidence",
            severity="low",
            frame_timestamp=frame_timestamp,
            camera_node_id=camera_node_id,
            image_path=image_path,
            detection_data=detection,
            description=f"Low confidence {conf:.2f} for {detection.get('class_name', 'unknown')}",
            created_at=datetime.now(UTC).isoformat(),
        )
        self._add(case)
        return case
    
    def collect_anomaly(
        self,
        camera_node_id: str,
        frame_timestamp: str,
        anomaly_score: float,
        anomaly_type: str,
        description: str,
        image_path: str | None = None,
    ) -> EdgeCase:
        case = EdgeCase(
            id=uuid4().hex,
            case_type="anomaly",
            severity="high" if anomaly_score > 3.0 else "medium",
            frame_timestamp=frame_timestamp,
            camera_node_id=camera_node_id,
            image_path=image_path,
            description=f"[{anomaly_type}] {description} (score={anomaly_score:.2f})",
            created_at=datetime.now(UTC).isoformat(),
        )
        self._add(case)
        return case
    
    def collect_class_confusion(
        self,
        camera_node_id: str,
        frame_timestamp: str,
        class_a: str,
        class_b: str,
        iou: float,
        resolution: str,
        image_path: str | None = None,
    ) -> EdgeCase:
        case = EdgeCase(
            id=uuid4().hex,
            case_type="class_confusion",
            severity="medium",
            frame_timestamp=frame_timestamp,
            camera_node_id=camera_node_id,
            image_path=image_path,
            description=f"Confusion between {class_a} and {class_b} (IoU={iou:.3f}, resolution={resolution})",
            created_at=datetime.now(UTC).isoformat(),
        )
        self._add(case)
        return case
    
    def _add(self, case: EdgeCase) -> None:
        if len(self._buffer) >= self._max_buffer:
            self._buffer.pop(0)
        self._buffer.append(case)
    
    def get_pending_for_labeling(self, limit: int = 50) -> list[EdgeCase]:
        pending = [c for c in self._buffer if not c.sent_to_labeling]
        pending.sort(key=lambda c: {"high": 0, "medium": 1, "low": 2}.get(c.severity, 3))
        return pending[:limit]
    
    def mark_sent_to_labeling(self, case_ids: list[str]) -> int:
        count = 0
        for case in self._buffer:
            if case.id in case_ids:
                case.sent_to_labeling = True
                case.labeling_status = "in_review"
                count += 1
        return count
    
    def get_stats(self) -> FlywheelStats:
        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        pending = 0
        in_review = 0
        completed = 0
        
        for case in self._buffer:
            by_type[case.case_type] = by_type.get(case.case_type, 0) + 1
            by_severity[case.severity] = by_severity.get(case.severity, 0) + 1
            if case.labeling_status == "pending":
                pending += 1
            elif case.labeling_status == "in_review":
                in_review += 1
            else:
                completed += 1
        
        return FlywheelStats(
            total_edge_cases=len(self._buffer),
            by_type=by_type,
            by_severity=by_severity,
            pending_labeling=pending,
            in_review=in_review,
            completed=completed,
            collection_rate_per_hour=0.0,
        )

    def collect_from_detection_frame(
        self,
        frame_data: dict,
        detections: list[dict],
        ground_truth: list[dict] | None = None,
        camera_node_id: str = "unknown",
        image_path: str | None = None,
    ) -> list[EdgeCase]:
        """Analyze a frame's detections against ground truth to find edge cases.

        Args:
            frame_data: Dict with at least 'timestamp' key.
            detections: List of detection dicts with 'class_name', 'confidence', 'bbox'.
            ground_truth: Optional list of ground truth detections for missed-detection comparison.
            camera_node_id: Node identifier.
            image_path: Optional path to the frame image.

        Returns:
            List of collected EdgeCase instances.
        """
        timestamp = frame_data.get("timestamp", datetime.now(UTC).isoformat())
        collected: list[EdgeCase] = []

        # 1. Check for low-confidence detections (< 0.5)
        for det in detections:
            conf = det.get("confidence", 0)
            if conf < 0.5:
                case = self.collect_low_confidence(
                    camera_node_id=camera_node_id,
                    frame_timestamp=str(timestamp),
                    detection=det,
                    confidence_threshold=0.5,
                    image_path=image_path,
                )
                if case is not None:
                    collected.append(case)

        # 2. Compare detections against ground truth to find missed detections
        if ground_truth:
            det_bboxes = [d.get("bbox", []) for d in detections]
            for gt in ground_truth:
                gt_bbox = gt.get("bbox", [])
                gt_class = gt.get("class_name", "unknown")
                gt_conf = gt.get("confidence", 1.0)
                # Check if any detection overlaps significantly with this GT
                matched = False
                for det_bbox in det_bboxes:
                    iou = _compute_iou(gt_bbox, det_bbox)
                    if iou > 0.5:
                        matched = True
                        break
                if not matched:
                    case = self.collect_missed_detection(
                        camera_node_id=camera_node_id,
                        frame_timestamp=str(timestamp),
                        lost_track_id=0,
                        last_known_class=gt_class,
                        last_confidence=gt_conf,
                        image_path=image_path,
                    )
                    collected.append(case)

        # 3. Check for class confusion (overlapping detections with different classes)
        for i in range(len(detections)):
            for j in range(i + 1, len(detections)):
                det_a = detections[i]
                det_b = detections[j]
                cls_a = det_a.get("class_name", "")
                cls_b = det_b.get("class_name", "")
                if cls_a == cls_b or not cls_a or not cls_b:
                    continue
                bbox_a = det_a.get("bbox", [])
                bbox_b = det_b.get("bbox", [])
                iou = _compute_iou(bbox_a, bbox_b)
                if iou > 0.3:
                    case = self.collect_class_confusion(
                        camera_node_id=camera_node_id,
                        frame_timestamp=str(timestamp),
                        class_a=cls_a,
                        class_b=cls_b,
                        iou=iou,
                        resolution="needs_review",
                        image_path=image_path,
                    )
                    collected.append(case)

        return collected

    async def flush_to_db(self, db: AsyncSession) -> int:
        """Persist buffered edge cases to the audit_logs table as event records.

        Returns the number of cases flushed.
        """
        unsent = [c for c in self._buffer if not c.sent_to_labeling]
        if not unsent:
            return 0

        flushed = 0
        for case in unsent:
            try:
                log = AuditLog(
                    event_type="edge_case",
                    severity=case.severity,
                    actor_id=None,
                    actor_type="flywheel",
                    resource_type="edge_case",
                    resource_id=None,
                    details={
                        "id": case.id,
                        "case_type": case.case_type,
                        "severity": case.severity,
                        "frame_timestamp": case.frame_timestamp,
                        "camera_node_id": case.camera_node_id,
                        "image_path": case.image_path,
                        "detection_data": case.detection_data,
                        "tracker_data": case.tracker_data,
                        "description": case.description,
                        "labeling_status": case.labeling_status,
                    },
                    ip_address=None,
                )
                db.add(log)
                case.sent_to_labeling = True
                case.labeling_status = "in_review"
                flushed += 1
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("edge_case_flush_failed", error=str(exc))

        if flushed > 0:
            await db.commit()

        return flushed

    async def get_labeling_candidates(self, db: AsyncSession, limit: int = 50) -> list[dict]:
        """Retrieve edge cases from audit_logs that are ready for human review.

        Returns dicts matching the EdgeCase structure.
        """
        result = await db.execute(
            select(AuditLog)
            .where(AuditLog.event_type == "edge_case")
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        logs = result.scalars().all()

        candidates = []
        for log in logs:
            details = log.details or {}
            candidates.append({
                "id": details.get("id", str(log.id)),
                "case_type": details.get("case_type", "unknown"),
                "severity": details.get("severity", "medium"),
                "frame_timestamp": details.get("frame_timestamp", ""),
                "camera_node_id": details.get("camera_node_id", ""),
                "image_path": details.get("image_path"),
                "detection_data": details.get("detection_data"),
                "tracker_data": details.get("tracker_data"),
                "description": details.get("description", ""),
                "labeling_status": details.get("labeling_status", "in_review"),
                "created_at": log.created_at.isoformat() if log.created_at else "",
            })

        return candidates


def _compute_iou(bbox_a: list[float], bbox_b: list[float]) -> float:
    """Compute Intersection over Union between two bounding boxes.

    Bboxes are [x1, y1, x2, y2] format.
    """
    if not bbox_a or not bbox_b or len(bbox_a) < 4 or len(bbox_b) < 4:
        return 0.0

    x1 = max(bbox_a[0], bbox_b[0])
    y1 = max(bbox_a[1], bbox_b[1])
    x2 = min(bbox_a[2], bbox_b[2])
    y2 = min(bbox_a[3], bbox_b[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, bbox_a[2] - bbox_a[0]) * max(0, bbox_a[3] - bbox_a[1])
    area_b = max(0, bbox_b[2] - bbox_b[0]) * max(0, bbox_b[3] - bbox_b[1])
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


# Module-level singleton for the live pipeline
_default_flywheel = DataFlywheel(max_buffer=5000)


def get_default_flywheel() -> DataFlywheel:
    return _default_flywheel
