"""Annotation Quality Assurance pipeline.

Implements:
- Inter-Annotator Agreement (IAA) calculation with multiple metrics
- Label consistency checks
- Annotation coverage analysis
- Quality scoring per annotation
- QA review workflow
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import numpy as np

@dataclass
class QAReport:
    """Quality report for a set of annotations."""
    total_annotations: int
    annotations_reviewed: int
    annotations_approved: int
    annotations_rejected: int
    annotations_pending: int
    avg_iaa_score: float
    class_coverage: dict[str, int]
    issues_found: list[dict]
    quality_distribution: dict[str, int]  # "excellent": 5, "good": 10, "poor": 2

@dataclass
class AnnotationIssue:
    """A detected quality issue in an annotation."""
    issue_type: str  # "missing_label", "duplicate_bbox", "low_iaa", "inconsistent_class", "bbox_too_small", "bbox_outside_image"
    severity: str  # "critical", "warning", "info"
    annotation_id: str
    description: str
    suggestion: str

def compute_bbox_iou(box_a: list[float], box_b: list[float]) -> float:
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0

def compute_cohens_kappa(ratings_a: list[int], ratings_b: list[int]) -> float:
    """Cohen's Kappa for inter-annotator agreement on categorical labels."""
    assert len(ratings_a) == len(ratings_b)
    n = len(ratings_a)
    if n == 0:
        return 0.0

    categories = set(ratings_a) | set(ratings_b)
    agreement = sum(1 for a, b in zip(ratings_a, ratings_b) if a == b)
    po = agreement / n

    pe = 0.0
    for cat in categories:
        count_a = sum(1 for x in ratings_a if x == cat)
        count_b = sum(1 for x in ratings_b if x == cat)
        pe += (count_a / n) * (count_b / n)

    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)

def compute_detection_iaa(
    annotations_a: list[dict],
    annotations_b: list[dict],
    iou_threshold: float = 0.5,
) -> float:
    """Compute IoU-based IAA between two annotators' bounding box sets.

    Each annotation: {"class_name": str, "bbox": [x1,y1,x2,y2]}
    Returns mean IoU across best-matched pairs.
    """
    if not annotations_a or not annotations_b:
        return 0.0

    matched_ious = []
    used_b: set[int] = set()

    for ann_a in annotations_a:
        best_iou = 0.0
        best_j = -1
        for j, ann_b in enumerate(annotations_b):
            if j in used_b:
                continue
            if ann_a.get("class_name") != ann_b.get("class_name"):
                continue
            iou_val = compute_bbox_iou(ann_a.get("bbox", [0,0,0,0]), ann_b.get("bbox", [0,0,0,0]))
            if iou_val > best_iou:
                best_iou = iou_val
                best_j = j
        if best_j >= 0:
            used_b.add(best_j)
        matched_ious.append(best_iou)

    # Penalize unmatched
    unmatched = len(annotations_b) - len(used_b)
    penalty = unmatched * 0.2
    mean_iou = np.mean(matched_ious) if matched_ious else 0.0
    return max(0.0, float(mean_iou) - penalty)

def detect_annotation_issues(annotation: dict, image_width: int = 640, image_height: int = 480) -> list[AnnotationIssue]:
    """Detect quality issues in a single annotation."""
    issues = []
    labels = annotation.get("labels") or annotation.get("boxes", [])

    if not labels:
        issues.append(AnnotationIssue(
            issue_type="missing_label",
            severity="warning",
            annotation_id=str(annotation.get("id", "")),
            description="Annotation has no labels",
            suggestion="Add detection labels or mark as empty",
        ))
        return issues

    bboxes = []
    for label in labels:
        bbox = label.get("bbox", label.get("x", None))
        if bbox is None:
            continue
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            bboxes.append(bbox)

    # Check for duplicate/near-duplicate boxes
    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            iou_val = compute_bbox_iou(bboxes[i], bboxes[j])
            if iou_val > 0.8:
                issues.append(AnnotationIssue(
                    issue_type="duplicate_bbox",
                    severity="critical",
                    annotation_id=str(annotation.get("id", "")),
                    description=f"Near-duplicate bounding boxes detected (IoU={iou_val:.3f})",
                    suggestion="Remove the duplicate box or merge overlapping detections",
                ))

    # Check for boxes outside image
    for i, bbox in enumerate(bboxes):
        if len(bbox) >= 4:
            x1, y1, x2, y2 = bbox[:4]
            if x1 < 0 or y1 < 0 or x2 > image_width or y2 > image_height:
                issues.append(AnnotationIssue(
                    issue_type="bbox_outside_image",
                    severity="warning",
                    annotation_id=str(annotation.get("id", "")),
                    description=f"Box {i} extends outside image bounds",
                    suggestion="Clip box to image boundaries",
                ))

    # Check for very small boxes
    for i, bbox in enumerate(bboxes):
        if len(bbox) >= 4:
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            if w * h < 100:  # less than 100 pixels
                issues.append(AnnotationIssue(
                    issue_type="bbox_too_small",
                    severity="info",
                    annotation_id=str(annotation.get("id", "")),
                    description=f"Box {i} is very small ({w:.0f}x{h:.0f}px)",
                    suggestion="Verify this is a valid detection, not noise",
                ))

    return issues

def compute_annotation_quality_score(annotation: dict) -> float:
    """Compute a quality score (0-1) for an annotation based on multiple factors."""
    score = 1.0
    labels = annotation.get("labels") or annotation.get("boxes", [])

    # Penalize empty annotations
    if not labels:
        return 0.3

    # Reward consistent confidence
    confidences = [l.get("confidence", 0.5) for l in labels if isinstance(l, dict)]
    if confidences:
        mean_conf = np.mean(confidences)
        std_conf = np.std(confidences)
        score *= (0.7 + 0.3 * mean_conf)
        score *= (1.0 - 0.1 * min(std_conf, 1.0))

    # Penalize if many low-confidence detections
    low_conf_count = sum(1 for c in confidences if c < 0.3)
    if low_conf_count > len(confidences) * 0.5:
        score *= 0.7

    return round(max(0.0, min(1.0, score)), 3)

def generate_qa_report(annotations: list[dict], iaa_threshold: float = 0.96) -> QAReport:
    """Generate a comprehensive QA report for a batch of annotations."""
    total = len(annotations)
    approved = 0
    rejected = 0
    pending = 0
    all_issues = []
    class_counts: dict[str, int] = {}
    quality_scores = []

    for ann in annotations:
        issues = detect_annotation_issues(ann)
        all_issues.extend(issues)

        score = compute_annotation_quality_score(ann)
        quality_scores.append(score)

        status = ann.get("status", "PENDING")
        if status == "CERTIFIED":
            approved += 1
        elif status == "REJECTED":
            rejected += 1
        else:
            pending += 1

        labels = ann.get("labels") or ann.get("boxes", [])
        for label in labels:
            if isinstance(label, dict):
                cls = label.get("class_name", label.get("label", "unknown"))
                class_counts[cls] = class_counts.get(cls, 0) + 1

    quality_dist = {"excellent": 0, "good": 0, "poor": 0}
    for s in quality_scores:
        if s >= 0.9:
            quality_dist["excellent"] += 1
        elif s >= 0.7:
            quality_dist["good"] += 1
        else:
            quality_dist["poor"] += 1

    avg_score = float(np.mean(quality_scores)) if quality_scores else 0.0

    return QAReport(
        total_annotations=total,
        annotations_reviewed=total,
        annotations_approved=approved,
        annotations_rejected=rejected,
        annotations_pending=pending,
        avg_iaa_score=round(avg_score, 4),
        class_coverage=class_counts,
        issues_found=[{"type": i.issue_type, "severity": i.severity, "desc": i.description} for i in all_issues],
        quality_distribution=quality_dist,
    )
