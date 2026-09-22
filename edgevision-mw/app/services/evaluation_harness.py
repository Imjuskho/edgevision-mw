"""Standing evaluation harness for model regression detection.

Every model update is measured against a benchmark set before deployment.
Prevents silent regressions as models are fine-tuned.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable
import time
import numpy as np

@dataclass
class EvalResult:
    """Evaluation results for a model on a benchmark set."""
    model_version: str
    benchmark_name: str
    total_samples: int
    mAP50: float
    mAP50_95: float
    precision: float
    recall: float
    f1_score: float
    per_class_ap: dict[str, float]
    confusion_matrix: dict[str, dict[str, int]]
    inference_time_ms_avg: float
    regression_detected: bool
    regression_details: list[str]
    passed: bool
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

@dataclass
class BenchmarkConfig:
    """Configuration for a benchmark evaluation run."""
    name: str
    model_version: str
    dataset_path: str
    confidence_threshold: float = 0.25
    iou_threshold: float = 0.5
    max_detections: int = 300
    image_size: tuple[int, int] = (640, 640)

def compute_ap(predictions: list[dict], ground_truths: list[dict], iou_threshold: float = 0.5) -> float:
    """Compute Average Precision for a single class."""
    if not predictions or not ground_truths:
        return 0.0

    # Sort predictions by confidence
    sorted_preds = sorted(predictions, key=lambda p: p.get("confidence", 0), reverse=True)

    tp = np.zeros(len(sorted_preds))
    fp = np.zeros(len(sorted_preds))
    matched_gt: set[int] = set()

    for i, pred in enumerate(sorted_preds):
        best_iou = 0.0
        best_gt_idx = -1
        for j, gt in enumerate(ground_truths):
            if j in matched_gt:
                continue
            pred_box = pred.get("bbox", [0, 0, 0, 0])
            gt_box = gt.get("bbox", [0, 0, 0, 0])
            iou_val = _iou(pred_box, gt_box)
            if iou_val > best_iou:
                best_iou = iou_val
                best_gt_idx = j

        if best_iou >= iou_threshold and best_gt_idx >= 0:
            tp[i] = 1
            matched_gt.add(best_gt_idx)
        else:
            fp[i] = 1

    tp_cumsum = np.cumsum(tp)
    fp_cumsum = np.cumsum(fp)
    precision_curve = tp_cumsum / (tp_cumsum + fp_cumsum)
    recall_curve = tp_cumsum / len(ground_truths) if ground_truths else np.zeros_like(tp_cumsum)

    # AP = area under precision-recall curve (11-point interpolation)
    ap = 0.0
    for t in np.arange(0, 1.1, 0.1):
        prec_at_recall = precision_curve[recall_curve >= t]
        if len(prec_at_recall) > 0:
            ap += np.max(prec_at_recall) / 11.0

    return float(ap)

def _iou(box_a: list[float], box_b: list[float]) -> float:
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0

def run_evaluation(
    predictions: list[dict],  # [{class_name, bbox, confidence, image_id}]
    ground_truths: list[dict],  # [{class_name, bbox, image_id}]
    model_version: str = "unknown",
    benchmark_name: str = "default",
    iou_threshold: float = 0.5,
    baseline_result: EvalResult | None = None,
    regression_threshold: float = 0.02,
) -> EvalResult:
    """Run full evaluation and detect regressions against baseline."""
    # Group by class
    classes = set(p.get("class_name", "") for p in predictions) | set(g.get("class_name", "") for g in ground_truths)

    per_class_ap = {}
    confusion = {}

    for cls in classes:
        cls_preds = [p for p in predictions if p.get("class_name") == cls]
        cls_gts = [g for g in ground_truths if g.get("class_name") == cls]
        ap = compute_ap(cls_preds, cls_gts, iou_threshold)
        per_class_ap[cls] = round(ap, 4)

        confusion[cls] = {
            "true_positives": len([p for p in cls_preds if any(
                _iou(p.get("bbox", [0,0,0,0]), g.get("bbox", [0,0,0,0])) >= iou_threshold
                for g in cls_gts
            )]),
            "false_positives": len(cls_preds) - len([p for p in cls_preds if any(
                _iou(p.get("bbox", [0,0,0,0]), g.get("bbox", [0,0,0,0])) >= iou_threshold
                for g in cls_gts
            )]),
            "false_negatives": len(cls_gts) - len([g for g in cls_gts if any(
                _iou(p.get("bbox", [0,0,0,0]), g.get("bbox", [0,0,0,0])) >= iou_threshold
                for p in cls_preds
            )]),
        }

    all_ap = list(per_class_ap.values())
    mAP50 = float(np.mean(all_ap)) if all_ap else 0.0

    # Real mAP50-95: compute AP at IoU thresholds from 0.5 to 0.95 in 0.05 steps
    iou_thresholds = np.arange(0.5, 1.0, 0.05)
    ap_per_threshold = []
    for iou_thresh in iou_thresholds:
        threshold_aps = []
        for cls in classes:
            cls_preds = [p for p in predictions if p.get("class_name") == cls]
            cls_gts = [g for g in ground_truths if g.get("class_name") == cls]
            ap = compute_ap(cls_preds, cls_gts, iou_threshold=float(iou_thresh))
            threshold_aps.append(ap)
        ap_per_threshold.append(float(np.mean(threshold_aps)) if threshold_aps else 0.0)
    mAP50_95 = float(np.mean(ap_per_threshold))

    total_tp = sum(c["true_positives"] for c in confusion.values())
    total_fp = sum(c["false_positives"] for c in confusion.values())
    total_fn = sum(c["false_negatives"] for c in confusion.values())

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # Regression detection
    regressions = []
    if baseline_result:
        for cls in per_class_ap:
            if cls in baseline_result.per_class_ap:
                delta = per_class_ap[cls] - baseline_result.per_class_ap[cls]
                if delta < -regression_threshold:
                    regressions.append(
                        f"{cls}: AP dropped from {baseline_result.per_class_ap[cls]:.4f} to {per_class_ap[cls]:.4f} (delta={delta:.4f})"
                    )
        map_delta = mAP50 - baseline_result.mAP50
        if map_delta < -regression_threshold:
            regressions.append(f"Overall mAP dropped from {baseline_result.mAP50:.4f} to {mAP50:.4f}")

    return EvalResult(
        model_version=model_version,
        benchmark_name=benchmark_name,
        total_samples=len(ground_truths),
        mAP50=round(mAP50, 4),
        mAP50_95=round(mAP50_95, 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1_score=round(f1, 4),
        per_class_ap=per_class_ap,
        confusion_matrix=confusion,
        inference_time_ms_avg=0.0,
        regression_detected=len(regressions) > 0,
        regression_details=regressions,
        passed=len(regressions) == 0 and mAP50 >= 0.3,
    )


def compute_per_class_f1(
    predictions: list[dict],
    ground_truths: list[dict],
    iou_threshold: float = 0.5,
) -> dict[str, dict[str, float]]:
    """Compute per-class precision, recall, and F1 score.

    Args:
        predictions: List of prediction dicts with class_name, bbox, confidence.
        ground_truths: List of ground-truth dicts with class_name, bbox.
        iou_threshold: Minimum IoU for a true-positive match.

    Returns:
        Dict mapping class_name -> {precision, recall, f1, support}.
    """
    classes = set(p.get("class_name", "") for p in predictions) | set(g.get("class_name", "") for g in ground_truths)
    results: dict[str, dict[str, float]] = {}

    for cls in classes:
        cls_preds = [p for p in predictions if p.get("class_name") == cls]
        cls_gts = [g for g in ground_truths if g.get("class_name") == cls]

        matched_gt: set[int] = set()
        tp = 0
        for pred in cls_preds:
            best_iou = 0.0
            best_idx = -1
            for j, gt in enumerate(cls_gts):
                if j in matched_gt:
                    continue
                iou_val = _iou(pred.get("bbox", [0, 0, 0, 0]), gt.get("bbox", [0, 0, 0, 0]))
                if iou_val > best_iou:
                    best_iou = iou_val
                    best_idx = j
            if best_iou >= iou_threshold and best_idx >= 0:
                tp += 1
                matched_gt.add(best_idx)

        fp = len(cls_preds) - tp
        fn = len(cls_gts) - tp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        results[cls] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": float(len(cls_gts)),
        }

    return results


def run_benchmark(
    samples: list[tuple[list[dict], list[dict]]],
    model_version: str = "unknown",
    benchmark_name: str = "default",
    iou_threshold: float = 0.5,
    baseline_result: EvalResult | None = None,
    regression_threshold: float = 0.02,
) -> EvalResult:
    """Run evaluation on a list of (predictions, ground_truths) tuples and aggregate.

    Args:
        samples: List of (predictions, ground_truths) tuples.
        model_version: Model version identifier.
        benchmark_name: Name of the benchmark.
        iou_threshold: IoU threshold for matching.
        baseline_result: Optional baseline for regression detection.
        regression_threshold: Maximum acceptable AP drop.

    Returns:
        Aggregated EvalResult across all samples.
    """
    all_predictions: list[dict] = []
    all_ground_truths: list[dict] = []
    for preds, gts in samples:
        all_predictions.extend(preds)
        all_ground_truths.extend(gts)

    result = run_evaluation(
        predictions=all_predictions,
        ground_truths=all_ground_truths,
        model_version=model_version,
        benchmark_name=benchmark_name,
        iou_threshold=iou_threshold,
        baseline_result=baseline_result,
        regression_threshold=regression_threshold,
    )
    result.total_samples = len(all_ground_truths)
    return result


def measure_inference_time(
    inference_fn: Callable[[Any], Any],
    images: list[Any],
    warmup: int = 2,
) -> dict[str, float]:
    """Measure inference time statistics for a callable over a list of images.

    Args:
        inference_fn: Callable that accepts a single image and returns a result.
        images: List of input images (any format the inference function accepts).
        warmup: Number of initial images to exclude from timing (GPU warmup).

    Returns:
        Dict with mean_ms, std_ms, min_ms, max_ms, total_ms, num_images.
    """
    if not images:
        return {"mean_ms": 0.0, "std_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "total_ms": 0.0, "num_images": 0}

    times_ms: list[float] = []

    # Warmup passes (timed but excluded from stats)
    for img in images[:warmup]:
        start = time.perf_counter()
        inference_fn(img)
        _ = time.perf_counter() - start  # noqa: F841

    # Timed passes
    for img in images:
        start = time.perf_counter()
        inference_fn(img)
        elapsed = (time.perf_counter() - start) * 1000.0
        times_ms.append(elapsed)

    arr = np.array(times_ms)
    return {
        "mean_ms": round(float(np.mean(arr)), 2),
        "std_ms": round(float(np.std(arr)), 2),
        "min_ms": round(float(np.min(arr)), 2),
        "max_ms": round(float(np.max(arr)), 2),
        "total_ms": round(float(np.sum(arr)), 2),
        "num_images": len(images),
    }
