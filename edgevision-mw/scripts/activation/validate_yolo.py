#!/usr/bin/env python3
"""P2.1 — Validate YOLO detection on real Lilongwe frames.

Usage:
    cd edgevision-mw
    POSTGRES_HOST=localhost .venv/bin/python scripts/activation/validate_yolo.py \
        --frames /path/to/real_frames/

Produces:
  - Per-frame detection counts, classes, inference time
  - Precision / Recall / F1 if --ground-truth is provided
  - JSON report saved to /tmp/edgevision_exports/yolo_validation.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cv2
import numpy as np


def run_yolo_on_frame(detector, frame_path: Path) -> dict:
    """Run YOLO on a single frame and return detection summary."""
    img = cv2.imread(str(frame_path))
    if img is None:
        return {"frame": str(frame_path), "error": "unreadable", "detections": 0}

    t0 = time.perf_counter()
    results = detector(img)
    inference_ms = (time.perf_counter() - t0) * 1000

    boxes = []
    if hasattr(results, "boxes") and results.boxes is not None:
        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_name = results.names.get(cls_id, str(cls_id)) if hasattr(results, "names") else str(cls_id)
            boxes.append({
                "class": cls_name,
                "confidence": round(conf, 4),
                "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            })

    classes = [b["class"] for b in boxes]
    return {
        "frame": frame_path.name,
        "detections": len(boxes),
        "classes": classes,
        "class_counts": {c: classes.count(c) for c in set(classes)},
        "inference_ms": round(inference_ms, 1),
        "boxes": boxes,
    }


def load_ground_truth(gt_path: Path) -> dict[str, list[dict]]:
    """Load ground-truth annotations from a JSON file.

    Expected format:
    {
        "frame_name.jpg": [
            {"class": "car", "bbox": [x1, y1, x2, y2]},
            ...
        ],
        ...
    }
    """
    if not gt_path.exists():
        return {}
    with open(gt_path) as f:
        return json.load(f)


def compute_iou(box_a: list[float], box_b: list[float]) -> float:
    """Compute IoU between two [x1, y1, x2, y2] boxes."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def evaluate_frame(pred_boxes: list[dict], gt_boxes: list[dict], iou_threshold: float = 0.5) -> dict:
    """Match predictions to ground truth and count TP/FP/FN."""
    matched_gt = set()
    tp = 0
    fp = 0

    for pred in pred_boxes:
        best_iou = 0.0
        best_idx = -1
        for idx, gt in enumerate(gt_boxes):
            if idx in matched_gt:
                continue
            if pred["class"] != gt["class"]:
                continue
            iou = compute_iou(pred["bbox"], gt["bbox"])
            if iou > best_iou:
                best_iou = iou
                best_idx = idx
        if best_iou >= iou_threshold and best_idx >= 0:
            tp += 1
            matched_gt.add(best_idx)
        else:
            fp += 1

    fn = len(gt_boxes) - len(matched_gt)
    return {"tp": tp, "fp": fp, "fn": fn}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate YOLO on real frames")
    parser.add_argument("--frames", required=True, help="Directory of .jpg/.png frames")
    parser.add_argument("--model", default="yolov8x.pt", help="YOLO model path")
    parser.add_argument("--ground-truth", default=None, help="Optional: path to ground-truth JSON")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--output", default="/tmp/edgevision_exports/yolo_validation.json")
    args = parser.parse_args()

    frames_dir = Path(args.frames)
    frame_files = sorted(
        [f for f in frames_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
    )
    if not frame_files:
        print(f"ERROR: No images in {frames_dir}")
        sys.exit(1)

    print(f"[P2.1] Validating YOLO on {len(frame_files)} frames")

    # Load model
    from ultralytics import YOLO
    model = YOLO(args.model)
    print(f"  Model: {args.model} ({len(model.names)} classes)")
    print(f"  Classes: {list(model.names.values())[:10]}...")

    # Run inference
    results = []
    all_inference_ms = []
    for f in frame_files:
        r = run_yolo_on_frame(model, f)
        results.append(r)
        all_inference_ms.append(r.get("inference_ms", 0))
        det_str = f"{r['detections']} det" if r["detections"] > 0 else "no det"
        print(f"  {r['frame']}: {det_str}, {r.get('inference_ms', 0):.0f}ms")

    # Summary
    total_dets = sum(r["detections"] for r in results)
    avg_ms = sum(all_inference_ms) / len(all_inference_ms) if all_inference_ms else 0

    print(f"\n  Total detections: {total_dets}")
    print(f"  Avg inference:    {avg_ms:.1f}ms/frame")
    print(f"  Frames analyzed:  {len(results)}")

    # Class distribution
    all_classes = []
    for r in results:
        all_classes.extend(r.get("classes", []))
    if all_classes:
        class_dist = {c: all_classes.count(c) for c in sorted(set(all_classes))}
        print(f"  Class distribution:")
        for cls, count in class_dist.items():
            print(f"    {cls}: {count}")

    # Ground-truth evaluation
    report = {
        "model": args.model,
        "frames": len(results),
        "total_detections": total_dets,
        "avg_inference_ms": round(avg_ms, 1),
        "class_distribution": {c: all_classes.count(c) for c in set(all_classes)} if all_classes else {},
        "per_frame": results,
    }

    if args.ground_truth:
        gt = load_ground_truth(Path(args.ground_truth))
        total_tp = 0
        total_fp = 0
        total_fn = 0
        for r in results:
            fname = r["frame"]
            pred_boxes = r.get("boxes", [])
            gt_boxes = gt.get(fname, [])
            ev = evaluate_frame(pred_boxes, gt_boxes)
            total_tp += ev["tp"]
            total_fp += ev["fp"]
            total_fn += ev["fn"]

        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        report["ground_truth"] = {
            "tp": total_tp, "fp": total_fp, "fn": total_fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
        print(f"\n  Ground-truth evaluation:")
        print(f"    TP={total_tp} FP={total_fp} FN={total_fn}")
        print(f"    Precision: {precision:.4f}")
        print(f"    Recall:    {recall:.4f}")
        print(f"    F1:        {f1:.4f}")
    else:
        print(f"\n  (No --ground-truth provided; skipping precision/recall/F1)")

    # Save report
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved to {output_path}")


if __name__ == "__main__":
    main()
