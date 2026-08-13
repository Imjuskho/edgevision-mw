#!/usr/bin/env python3
"""
Render YOLO-seg polygon overlays for visual QA of corrected road labels.

Writes composite images to ``runs/label_gen/{split}/`` mirroring the dataset
layout produced by ``scripts/export_road_labels.py``.

Usage:
    python scripts/render_road_overlays.py
    python scripts/render_road_overlays.py --dataset datasets/road_seg_corrected --limit 50
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CLASS_NAMES = [
    "good_road", "pothole", "crack", "dust_road",
    "gravel_road", "road_marking", "shoulder",
]
COLORS = [
    (0, 200, 0), (0, 0, 255), (255, 0, 0), (0, 165, 255),
    (128, 128, 128), (255, 255, 0), (255, 0, 255),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render road-seg label overlays")
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(ROOT / "datasets" / "road_seg_corrected"),
        help="YOLO-seg dataset root (images/ + labels/)",
    )
    parser.add_argument(
        "--output-run",
        type=str,
        default=str(ROOT / "runs" / "label_gen"),
        help="Directory for overlay PNG/JPG outputs",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max overlays per split (0 = all)")
    return parser.parse_args()


def _load_instances(lbl_path: Path) -> list[tuple[int, list[tuple[float, float]]]]:
    if not lbl_path.exists() or not lbl_path.read_text().strip():
        return []
    out: list[tuple[int, list[tuple[float, float]]]] = []
    for line in lbl_path.read_text().strip().splitlines():
        parts = line.split()
        if len(parts) < 7:
            continue
        cid = int(parts[0])
        coords = [(float(parts[i]), float(parts[i + 1])) for i in range(1, len(parts), 2)]
        if len(coords) >= 3:
            out.append((cid, coords))
    return out


def _render_overlay(image: np.ndarray, instances: list[tuple[int, list[tuple[float, float]]]]) -> np.ndarray:
    vis = image.copy()
    h, w = vis.shape[:2]
    for cid, polygon in instances:
        pts = np.array([[int(x * w), int(y * h)] for x, y in polygon], dtype=np.int32)
        color = COLORS[cid % len(COLORS)]
        cv2.polylines(vis, [pts], True, color, 2)
        if len(pts) > 0:
            label = CLASS_NAMES[cid] if cid < len(CLASS_NAMES) else str(cid)
            cv2.putText(vis, label, tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    return vis


def main() -> None:
    args = parse_args()
    dataset = Path(args.dataset)
    out_root = Path(args.output_run)
    rendered = 0

    for split in ("train", "val", "test"):
        img_dir = dataset / "images" / split
        if not img_dir.exists():
            continue
        images = sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.png"))
        if args.limit:
            images = images[: args.limit]
        for img_path in images:
            lbl_path = dataset / "labels" / split / f"{img_path.stem}.txt"
            image = cv2.imread(str(img_path))
            if image is None:
                continue
            instances = _load_instances(lbl_path)
            overlay = _render_overlay(image, instances)
            out_path = out_root / split / f"{img_path.stem}_overlay.jpg"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out_path), overlay)
            rendered += 1

    print(f"Rendered {rendered} overlays to {out_root}")


if __name__ == "__main__":
    main()
