#!/usr/bin/env python3
"""Evaluate class confusion for custom safety-critical labels.

Modes:
  1. Detection-only overlap scan (no ground truth):
       python scripts/eval_class_confusion.py --images datasets/foo/images/train

  2. COCO ground-truth confusion matrix:
       python scripts/eval_class_confusion.py --images path/to/images --coco annotations.json

Output: JSON report + human-readable summary to stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai.class_confusion import build_confusion_report, summarize_report  # noqa: E402
from app.ai.yolo_seg import SEG_TO_TAXONOMY, get_yolo_seg_segmenter  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate class confusion for live detection")
    parser.add_argument("--images", type=str, required=True, help="Directory of images to evaluate")
    parser.add_argument("--coco", type=str, default=None, help="Optional COCO-format annotations JSON")
    parser.add_argument("--conf", type=float, default=0.22, help="Detection confidence threshold")
    parser.add_argument("--iou", type=float, default=0.5, help="IoU threshold for GT matching")
    parser.add_argument(
        "--conflict-iou",
        type=float,
        default=0.3,
        help="IoU threshold for overlapping contradictory classes",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max images to process (0 = all)")
    parser.add_argument("--output", type=str, default=None, help="Write JSON report to this path")
    return parser.parse_args()


def _load_coco_ground_truth(coco_path: Path) -> dict[str, list[dict]]:
    data = json.loads(coco_path.read_text(encoding="utf-8"))
    categories = {cat["id"]: cat["name"] for cat in data.get("categories", [])}
    images = {img["id"]: img["file_name"] for img in data.get("images", [])}

    by_image: dict[str, list[dict]] = {}
    for ann in data.get("annotations", []):
        file_name = images.get(ann["image_id"])
        if not file_name:
            continue
        class_name = categories.get(ann["category_id"], "object")
        bbox = ann.get("bbox", [])
        if len(bbox) < 4:
            continue
        entry = {
            "class_name": class_name,
            "taxonomy_label": SEG_TO_TAXONOMY.get(class_name, class_name),
            "confidence": 1.0,
            "bbox": bbox,
        }
        by_image.setdefault(file_name, []).append(entry)
    return by_image


def _iter_images(images_dir: Path) -> list[Path]:
    files = [p for p in sorted(images_dir.rglob("*")) if p.suffix.lower() in IMAGE_SUFFIXES]
    return files


def _detections_from_yolo(image_path: Path, conf_threshold: float) -> list[dict]:
    segmenter = get_yolo_seg_segmenter()
    if not segmenter.is_loaded():
        raise RuntimeError("YOLOv8-seg model not loaded — set YOLOV8_SEG_MODEL_PATH or bundle the ONNX model")

    image_bytes = image_path.read_bytes()
    instances = segmenter.detect(image_bytes, conf_threshold=conf_threshold)
    detections: list[dict] = []
    for inst in instances:
        x, y, w, h = inst["bbox"]
        detections.append(
            {
                "class_name": inst["class_name"],
                "taxonomy_label": inst.get("taxonomy") or SEG_TO_TAXONOMY.get(inst["class_name"], inst["class_name"]),
                "confidence": inst["confidence"],
                "bbox": [x, y, w, h],
            }
        )
    return detections


def main() -> None:
    args = parse_args()
    images_dir = Path(args.images)
    if not images_dir.is_dir():
        raise SystemExit(f"Images directory not found: {images_dir}")

    gt_by_image: dict[str, list[dict]] = {}
    if args.coco:
        coco_path = Path(args.coco)
        if not coco_path.is_file():
            raise SystemExit(f"COCO annotations not found: {coco_path}")
        gt_by_image = _load_coco_ground_truth(coco_path)

    image_paths = _iter_images(images_dir)
    if args.limit > 0:
        image_paths = image_paths[: args.limit]
    if not image_paths:
        raise SystemExit(f"No images found under {images_dir}")

    image_results: list[tuple[str | None, list[dict], list[dict] | None]] = []
    for image_path in image_paths:
        rel_name = image_path.name
        predictions = _detections_from_yolo(image_path, conf_threshold=args.conf)
        ground_truth = gt_by_image.get(rel_name)
        if ground_truth is None and gt_by_image:
            ground_truth = gt_by_image.get(str(image_path.relative_to(images_dir)))
        image_results.append((rel_name, predictions, ground_truth))

    report = build_confusion_report(
        image_results,
        iou_threshold=args.iou,
        conflict_iou_threshold=args.conflict_iou,
    )
    summary = summarize_report(report)
    print(summary)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"\nWrote JSON report to {out_path}")


if __name__ == "__main__":
    main()
