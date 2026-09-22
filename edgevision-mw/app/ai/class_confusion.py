"""Class confusion detection and resolution.

Runs confusion matrices on custom classes vs standard COCO to identify
overlapping/contradicting detections. Provides hard-negative mining
suggestions and per-class confidence threshold adjustments.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Known confusion pairs: (class_a, class_b, iou_threshold, resolution_strategy)
CONFUSION_PAIRS: list[tuple[str, str, float, str]] = [
    ("chair", "couch", 0.5, "merge_or_suppress"),
    ("person", "pedestrian_roadside", 0.3, "prefer_specialized"),
    ("car", "car_private", 0.3, "prefer_specialized"),
    ("truck", "truck_freight", 0.3, "prefer_specialized"),
    ("motorcycle", "motorcycle_kabaza", 0.3, "prefer_specialized"),
    ("bus", "minibus", 0.3, "prefer_specialized"),
]

@dataclass
class ConfusionMatrix:
    """Per-pair confusion matrix between two classes."""
    class_a: str
    class_b: str
    true_a_as_a: int = 0  # correct: detected A, ground truth A
    true_b_as_b: int = 0  # correct: detected B, ground truth B
    false_a_as_b: int = 0  # confusion: detected A, ground truth B
    false_b_as_a: int = 0  # confusion: detected B, ground truth A
    iou_overlap_count: int = 0  # frames where both fire on same object
    
    @property
    def precision_a(self) -> float:
        total = self.true_a_as_a + self.false_b_as_a
        return self.true_a_as_a / total if total > 0 else 0.0
    
    @property
    def precision_b(self) -> float:
        total = self.true_b_as_b + self.false_a_as_b
        return self.true_b_as_b / total if total > 0 else 0.0
    
    @property
    def confusion_rate(self) -> float:
        total = self.true_a_as_a + self.true_b_as_b + self.false_a_as_b + self.false_b_as_a
        return (self.false_a_as_b + self.false_b_as_a) / total if total > 0 else 0.0

@dataclass
class ClassThresholdAdjustment:
    """Recommended confidence threshold adjustment for a class."""
    class_name: str
    current_threshold: float
    recommended_threshold: float
    reason: str
    expected_fp_reduction: float

def compute_iou(box_a: list[float], box_b: list[float]) -> float:
    """Compute IoU between two xyxy boxes."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0

def detect_confusions(frame_detections: list[dict], iou_threshold: float = 0.3) -> list[dict]:
    """Analyze a frame's detections for confusion between known class pairs.
    
    Returns list of confusion events: {class_a, class_b, iou, resolution, confidence_a, confidence_b}
    """
    events = []
    by_class: dict[str, list[dict]] = {}
    for det in frame_detections:
        cls = det.get("class_name", "unknown")
        by_class.setdefault(cls, []).append(det)
    
    for class_a, class_b, pair_iou_thresh, strategy in CONFUSION_PAIRS:
        dets_a = by_class.get(class_a, [])
        dets_b = by_class.get(class_b, [])
        for da in dets_a:
            for db in dets_b:
                iou_val = compute_iou(da.get("bbox", [0,0,0,0]), db.get("bbox", [0,0,0,0]))
                if iou_val >= pair_iou_thresh:
                    events.append({
                        "class_a": class_a,
                        "class_b": class_b,
                        "iou": round(iou_val, 4),
                        "resolution": strategy,
                        "confidence_a": da.get("confidence", 0.0),
                        "confidence_b": db.get("confidence", 0.0),
                        "bbox_a": da.get("bbox"),
                        "bbox_b": db.get("bbox"),
                    })
    return events

def resolve_confusion(detections: list[dict], events: list[dict]) -> list[dict]:
    """Apply resolution strategies to confused detections.
    
    Returns filtered detections with confusions resolved.
    """
    remove_indices: set[int] = set()
    for event in events:
        strategy = event.get("resolution", "suppress_lower")
        if strategy == "prefer_specialized":
            # Remove generic, keep specialized
            if event["confidence_a"] >= event["confidence_b"]:
                # A is more confident, remove B
                for i, d in enumerate(detections):
                    if (d.get("class_name") == event["class_b"] and 
                        d.get("bbox") == event.get("bbox_b")):
                        remove_indices.add(i)
            else:
                for i, d in enumerate(detections):
                    if (d.get("class_name") == event["class_a"] and 
                        d.get("bbox") == event.get("bbox_a")):
                        remove_indices.add(i)
        elif strategy == "merge_or_suppress":
            # Remove the lower-confidence one
            if event["confidence_a"] >= event["confidence_b"]:
                for i, d in enumerate(detections):
                    if (d.get("class_name") == event["class_b"] and 
                        d.get("bbox") == event.get("bbox_b")):
                        remove_indices.add(i)
            else:
                for i, d in enumerate(detections):
                    if (d.get("class_name") == event["class_a"] and 
                        d.get("bbox") == event.get("bbox_a")):
                        remove_indices.add(i)
        else:
            # Default: suppress lower confidence
            if event["confidence_a"] < event["confidence_b"]:
                for i, d in enumerate(detections):
                    if (d.get("class_name") == event["class_a"] and 
                        d.get("bbox") == event.get("bbox_a")):
                        remove_indices.add(i)
            else:
                for i, d in enumerate(detections):
                    if (d.get("class_name") == event["class_b"] and 
                        d.get("bbox") == event.get("bbox_b")):
                        remove_indices.add(i)
    
    return [d for i, d in enumerate(detections) if i not in remove_indices]

def analyze_confusion_matrix(
    predictions: list[dict],  # [{class_name, bbox, confidence, image_id}]
    ground_truths: list[dict],  # [{class_name, bbox, image_id}]
    class_pairs: list[tuple[str, str]] | None = None,
) -> dict[str, ConfusionMatrix]:
    """Build confusion matrices for given class pairs across a dataset.
    
    Returns dict of (class_a, class_b) -> ConfusionMatrix.
    """
    pairs = class_pairs or [(a, b) for a, b, _, _ in CONFUSION_PAIRS]
    matrices: dict[str, ConfusionMatrix] = {}
    
    for class_a, class_b in pairs:
        key = f"{class_a}_vs_{class_b}"
        cm = ConfusionMatrix(class_a=class_a, class_b=class_b)
        
        gt_by_image: dict[str, list[dict]] = {}
        for gt in ground_truths:
            gt_by_image.setdefault(str(gt.get("image_id", "")), []).append(gt)
        
        for pred in predictions:
            if pred.get("image_id") not in gt_by_image:
                continue
            gt_list = gt_by_image[pred["image_id"]]
            pred_cls = pred.get("class_name", "")
            best_iou = 0.0
            best_gt = None
            for gt in gt_list:
                if gt.get("class_name") == pred_cls:
                    iou_val = compute_iou(pred.get("bbox", [0,0,0,0]), gt.get("bbox", [0,0,0,0]))
                    if iou_val > best_iou:
                        best_iou = iou_val
                        best_gt = gt
            
            if best_gt and best_iou >= 0.3:
                if pred_cls == class_a:
                    cm.true_a_as_a += 1
                elif pred_cls == class_b:
                    cm.true_b_as_b += 1
            else:
                # Check cross-class confusion
                for gt in gt_list:
                    iou_val = compute_iou(pred.get("bbox", [0,0,0,0]), gt.get("bbox", [0,0,0,0]))
                    if iou_val >= 0.3:
                        if pred_cls == class_a and gt.get("class_name") == class_b:
                            cm.false_a_as_b += 1
                        elif pred_cls == class_b and gt.get("class_name") == class_a:
                            cm.false_b_as_a += 1
        
        matrices[key] = cm
    
    return matrices

def recommend_threshold_adjustments(
    matrices: dict[str, ConfusionMatrix],
    current_thresholds: dict[str, float],
    target_precision: float = 0.8,
) -> list[ClassThresholdAdjustment]:
    """Based on confusion matrices, recommend per-class threshold adjustments."""
    adjustments = []
    class_stats: dict[str, dict] = {}
    
    for key, cm in matrices.items():
        for cls in [cm.class_a, cm.class_b]:
            if cls not in class_stats:
                class_stats[cls] = {"false_positives": 0, "true_positives": 0, "confusion_count": 0}
            
        class_stats[cm.class_a]["false_positives"] += cm.false_b_as_a
        class_stats[cm.class_a]["true_positives"] += cm.true_a_as_a
        class_stats[cm.class_a]["confusion_count"] += cm.false_a_as_b + cm.false_b_as_a
        
        class_stats[cm.class_b]["false_positives"] += cm.false_a_as_b
        class_stats[cm.class_b]["true_positives"] += cm.true_b_as_b
        class_stats[cm.class_b]["confusion_count"] += cm.false_a_as_b + cm.false_b_as_a
    
    for cls, stats in class_stats.items():
        current = current_thresholds.get(cls, 0.45)
        total = stats["true_positives"] + stats["false_positives"]
        if total == 0:
            continue
        current_precision = stats["true_positives"] / total
        
        if current_precision < target_precision:
            # Raise threshold to reduce false positives
            boost = (target_precision - current_precision) * 0.5
            recommended = min(current + boost, 0.85)
            fp_reduction = stats["confusion_count"] * boost
            adjustments.append(ClassThresholdAdjustment(
                class_name=cls,
                current_threshold=current,
                recommended_threshold=round(recommended, 3),
                reason=f"Precision {current_precision:.2f} below target {target_precision:.2f}; {stats['confusion_count']} confusion events",
                expected_fp_reduction=round(fp_reduction, 1),
            ))
        elif current_precision > target_precision + 0.1:
            # Could lower threshold to catch more
            recommended = max(current - 0.05, 0.2)
            adjustments.append(ClassThresholdAdjustment(
                class_name=cls,
                current_threshold=current,
                recommended_threshold=round(recommended, 3),
                reason=f"Precision {current_precision:.2f} well above target; can lower threshold for recall",
                expected_fp_reduction=0.0,
            ))
    
    return adjustments


@dataclass
class ConfusionReport:
    """Full confusion analysis report across multiple frames/images."""
    total_frames: int = 0
    total_detections: int = 0
    confusion_events: list[dict[str, Any]] = field(default_factory=list)
    matrices: dict[str, ConfusionMatrix] = field(default_factory=dict)
    recommendations: list[ClassThresholdAdjustment] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_frames": self.total_frames,
            "total_detections": self.total_detections,
            "confusion_event_count": len(self.confusion_events),
            "matrices": {
                k: {
                    "class_a": m.class_a,
                    "class_b": m.class_b,
                    "precision_a": m.precision_a,
                    "precision_b": m.precision_b,
                    "confusion_rate": m.confusion_rate,
                    "total_pairs": m.true_a_as_a + m.true_b_as_b + m.false_a_as_b + m.false_b_as_a,
                }
                for k, m in self.matrices.items()
            },
            "recommendations": [
                {
                    "class_name": r.class_name,
                    "current": r.current_threshold,
                    "recommended": r.recommended_threshold,
                    "reason": r.reason,
                }
                for r in self.recommendations
            ],
        }


def build_confusion_report(
    image_results: list[dict[str, Any]],
    *,
    class_pairs: list[tuple[str, str, float, str]] | None = None,
    conf_threshold: float = 0.3,
    iou_threshold: float = 0.3,
) -> ConfusionReport:
    """Build a full confusion report from a list of per-image detection results.

    Each entry in image_results should have:
      - "detections": list of {bbox, class_name, confidence}
      - optionally "ground_truth": list of {bbox, class_name}
    """
    pairs = class_pairs or CONFUSION_PAIRS
    report = ConfusionReport()
    report.total_frames = len(image_results)

    matrix_map: dict[str, ConfusionMatrix] = {}
    for cls_a, cls_b, default_iou, _strategy in pairs:
        key = f"{cls_a}_vs_{cls_b}"
        matrix_map[key] = ConfusionMatrix(class_a=cls_a, class_b=cls_b)

    for frame in image_results:
        dets = frame.get("detections", [])
        report.total_detections += len(dets)
        gt = frame.get("ground_truth", [])

        for cls_a, cls_b, pair_iou, _strategy in pairs:
            key = f"{cls_a}_vs_{cls_b}"
            matrix = matrix_map[key]

            dets_a = [d for d in dets if d.get("class_name") == cls_a and d.get("confidence", 0) >= conf_threshold]
            dets_b = [d for d in dets if d.get("class_name") == cls_b and d.get("confidence", 0) >= conf_threshold]

            if gt:
                gt_a = [g for g in gt if g.get("class_name") == cls_a]
                gt_b = [g for g in gt if g.get("class_name") == cls_b]
                for g in gt_a:
                    matched = any(_iou(g.get("bbox", [0,0,0,0]), d.get("bbox", [0,0,0,0])) >= pair_iou for d in dets_a)
                    if matched:
                        matrix.true_a_as_a += 1
                    for d in dets_b:
                        if _iou(g.get("bbox", [0,0,0,0]), d.get("bbox", [0,0,0,0])) >= pair_iou:
                            matrix.false_b_as_a += 1
                            report.confusion_events.append({
                                "frame": report.total_frames,
                                "confused_class": cls_b,
                                "ground_truth": cls_a,
                                "confidence": d.get("confidence"),
                            })
                for g in gt_b:
                    matched = any(_iou(g.get("bbox", [0,0,0,0]), d.get("bbox", [0,0,0,0])) >= pair_iou for d in dets_b)
                    if matched:
                        matrix.true_b_as_b += 1
                    for d in dets_a:
                        if _iou(g.get("bbox", [0,0,0,0]), d.get("bbox", [0,0,0,0])) >= pair_iou:
                            matrix.false_a_as_b += 1
                            report.confusion_events.append({
                                "frame": report.total_frames,
                                "confused_class": cls_a,
                                "ground_truth": cls_b,
                                "confidence": d.get("confidence"),
                            })
            else:
                combined = [_bbox_dict(d) for d in dets_a] + [_bbox_dict(d) for d in dets_b]
                overlap_events = detect_confusions(combined, pair_iou)
                for ev in overlap_events:
                    matrix.false_a_as_b += 1
                    report.confusion_events.append({
                        "frame": report.total_frames,
                        "confused_class": cls_a,
                        "detected_alongside": cls_b,
                        "iou": ev.get("iou"),
                    })

    report.matrices = matrix_map
    return report


def summarize_report(report: ConfusionReport) -> str:
    """Return a human-readable summary of a ConfusionReport."""
    lines = [
        f"Confusion Report: {report.total_frames} frames, {report.total_detections} detections, "
        f"{len(report.confusion_events)} confusion events",
        "",
    ]
    for key, matrix in report.matrices.items():
        total = matrix.true_a_as_a + matrix.true_b_as_b + matrix.false_a_as_b + matrix.false_b_as_a
        if total == 0:
            continue
        lines.append(
            f"  {matrix.class_a} vs {matrix.class_b}: "
            f"precision_a={matrix.precision_a:.2f}, precision_b={matrix.precision_b:.2f}, "
            f"confusion_rate={matrix.confusion_rate:.2f}, "
            f"pairs={total}"
        )
    if not any(
        m.true_a_as_a + m.true_b_as_b + m.false_a_as_b + m.false_b_as_a > 0
        for m in report.matrices.values()
    ):
        lines.append("  No confusion pairs detected (or no ground truth available).")
    return "\n".join(lines)


def _bbox_dict(d: dict) -> dict:
    """Ensure detection dict has 'bbox' and 'class_name' keys."""
    return {"bbox": d.get("bbox", [0, 0, 0, 0]), "class_name": d.get("class_name", "unknown")}
