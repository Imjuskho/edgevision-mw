#!/usr/bin/env python3
"""
Auto-generate YOLO-seg polygon labels for road surface segmentation training.

Uses MobileSAM ONNX (when decoder probe passes) for region proposals, then
assigns road classes via color/texture heuristics. Falls back to pure
heuristics when SAM is unavailable.

Usage:
    python scripts/generate_road_labels.py
    python scripts/generate_road_labels.py --dataset datasets/road_seg_traffic --spot-check 5
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ai.sam_segmenter import SAMSegmenter  # noqa: E402

CLASS_NAMES = [
    "good_road", "pothole", "crack", "dust_road",
    "gravel_road", "road_marking", "shoulder",
]
NUM_CLASSES = len(CLASS_NAMES)

# Conflict resolution priority (higher wins)
CLASS_PRIORITY = {1: 7, 2: 6, 5: 5, 4: 4, 3: 3, 6: 2, 0: 1}


@dataclass
class LabelInstance:
    class_id: int
    polygon: list[tuple[float, float]]  # normalized x,y pairs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate YOLO-seg road labels via SAM + heuristics")
    parser.add_argument("--dataset", type=str, default=str(ROOT / "datasets" / "road_seg_traffic"))
    parser.add_argument("--min-area-frac", type=float, default=0.002, help="Min mask area as fraction of frame")
    parser.add_argument("--grid-cols", type=int, default=12)
    parser.add_argument("--grid-rows", type=int, default=8)
    parser.add_argument("--spot-check", type=int, default=5, help="Number of overlay images to write")
    parser.add_argument("--output-run", type=str, default=str(ROOT / "runs" / "label_gen"))
    return parser.parse_args()


def mask_to_polygon(mask: np.ndarray, max_points: int = 40) -> list[tuple[float, float]] | None:
    """Extract simplified normalized polygon from binary mask."""
    h, w = mask.shape
    contours, _ = cv2.findContours(
        (mask > 0.5).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 10:
        return None
    epsilon = 0.005 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)
    if len(approx) < 3:
        return None
    pts = approx.reshape(-1, 2).astype(np.float32)
    if len(pts) > max_points:
        step = max(1, len(pts) // max_points)
        pts = pts[::step][:max_points]
    return [(float(x) / w, float(y) / h) for x, y in pts]


def classify_mask_region(image: np.ndarray, mask: np.ndarray) -> tuple[int, float]:
    """Assign road class to a mask region using HSV color/texture heuristics."""
    h, w = image.shape[:2]
    area = mask.sum()
    if area < 50:
        return 0, 0.1

    roi = image[mask > 0.5]
    if roi.size == 0:
        return 0, 0.1

    hsv = cv2.cvtColor(roi.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    h_vals, s_vals, v_vals = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    mean_h, mean_s, mean_v = float(h_vals.mean()), float(s_vals.mean()), float(v_vals.mean())
    std_v = float(v_vals.std())

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F, ksize=3).var())

    ys, xs = np.where(mask > 0.5)
    y1, y2, x1, x2 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    bw, bh = max(1, x2 - x1), max(1, y2 - y1)
    aspect = max(bw, bh) / max(1, min(bw, bh))
    area_frac = area / (h * w)
    compactness = area / max(1, bw * bh)

    scores: dict[int, float] = {i: 0.0 for i in range(NUM_CLASSES)}

    # road_marking (5): white/yellow high luminance
    white_frac = float(((v_vals > 200) & (s_vals < 60)).mean())
    yellow_frac = float(((h_vals >= 15) & (h_vals <= 35) & (s_vals > 80) & (v_vals > 150)).mean())
    scores[5] = max(white_frac, yellow_frac) * 2.0

    # pothole (1): dark, compact, local variance
    if mean_v < 80 and compactness > 0.3 and area_frac < 0.05:
        scores[1] = (80 - mean_v) / 80 * compactness * 2.0

    # crack (2): thin elongated dark
    if aspect > 3.0 and mean_v < 100 and area_frac < 0.02:
        scores[2] = min(aspect / 10, 1.0) * (100 - mean_v) / 100

    # dust_road (3): tan/brown
    if 15 <= mean_h <= 40 and 30 <= mean_s <= 70 and 60 <= mean_v <= 90:
        scores[3] = 0.8

    # gravel_road (4): brownish-gray, high texture
    if 10 <= mean_h <= 30 and mean_s < 50 and lap_var > 200:
        scores[4] = min(lap_var / 500, 1.0)

    # shoulder (6): edges of frame, non-road color
    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
    if cx < 0.15 or cx > 0.85 or (cy < 0.55 and mean_s > 40):
        scores[6] = 0.6

    # good_road (0): smooth dark asphalt
    if 40 <= mean_v <= 120 and mean_s < 50 and lap_var < 300:
        scores[0] = 0.7 + (1.0 - min(lap_var / 300, 1.0)) * 0.3

    best_class = max(scores, key=lambda k: scores[k])
    confidence = scores[best_class]
    if confidence < 0.15:
        best_class = 0
        confidence = 0.3
    return best_class, confidence


def road_region_mask(h: int, w: int) -> np.ndarray:
    """Center-weighted lower 2/3 of frame as drivable region."""
    mask = np.zeros((h, w), dtype=np.float32)
    y_start = int(h * 0.25)
    y_end = h
    x_margin = int(w * 0.05)
    mask[y_start:y_end, x_margin:w - x_margin] = 1.0
    return mask


def heuristic_segment(image: np.ndarray) -> list[np.ndarray]:
    """Pure color/texture segmentation fallback when SAM is unavailable."""
    h, w = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    road = road_region_mask(h, w)

    # Segment by color clusters in road region
    masks: list[np.ndarray] = []
    ranges = [
        ((0, 0, 40), (180, 50, 130)),   # dark asphalt → good_road
        ((15, 30, 60), (40, 70, 90)),   # tan → dust_road
        ((0, 0, 180), (180, 60, 255)),  # bright → road_marking
    ]
    for lo, hi in ranges:
        seg = cv2.inRange(hsv, np.array(lo), np.array(hi))
        seg = cv2.bitwise_and(seg, (road * 255).astype(np.uint8))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        seg = cv2.morphologyEx(seg, cv2.MORPH_CLOSE, kernel)
        seg = cv2.morphologyEx(seg, cv2.MORPH_OPEN, kernel)
        n_labels, labels_map, stats, _ = cv2.connectedComponentsWithStats(seg, connectivity=8)
        for i in range(1, n_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < h * w * 0.002:
                continue
            comp_mask = (labels_map == i).astype(np.float32)
            masks.append(comp_mask)

    if not masks:
        # Last resort: single good_road polygon for lower half
        m = np.zeros((h, w), dtype=np.float32)
        m[int(h * 0.4):, int(w * 0.1):int(w * 0.9)] = 1.0
        masks.append(m)
    return masks


def sam_propose_masks(sam: SAMSegmenter, image: np.ndarray, grid_cols: int, grid_rows: int) -> list[np.ndarray]:
    """Generate mask proposals from SAM point grid in lower 2/3 of frame."""
    h, w = image.shape[:2]
    road = road_region_mask(h, w)
    y_start = int(h * 0.25)
    y_end = h
    x_margin = int(w * 0.05)

    raw_masks: list[np.ndarray] = []
    for row in range(grid_rows):
        for col in range(grid_cols):
            x = x_margin + int((w - 2 * x_margin) * (col + 0.5) / grid_cols)
            y = y_start + int((y_end - y_start) * (row + 0.5) / grid_rows)
            m = sam.predict_point(image, x, y)
            if m.sum() < h * w * 0.001:
                continue
            m = m * road
            if m.sum() < h * w * 0.001:
                continue
            raw_masks.append(m)

    return merge_overlapping_masks(raw_masks, iou_threshold=0.7)


def merge_overlapping_masks(masks: list[np.ndarray], iou_threshold: float = 0.7) -> list[np.ndarray]:
    """Merge highly overlapping masks, keeping larger ones."""
    if not masks:
        return []
    areas = [m.sum() for m in masks]
    order = sorted(range(len(masks)), key=lambda i: areas[i], reverse=True)
    kept: list[np.ndarray] = []
    for idx in order:
        m = masks[idx]
        dominated = False
        for k in kept:
            inter = (m * k).sum()
            union = m.sum() + k.sum() - inter
            if union > 0 and inter / union > iou_threshold:
                dominated = True
                break
        if not dominated:
            kept.append(m)
    return kept


def resolve_instances(instances: list[tuple[int, float, np.ndarray]], min_area_frac: float, h: int, w: int) -> list[LabelInstance]:
    """Resolve class conflicts and convert to label instances."""
    frame_area = h * w
    sorted_inst = sorted(instances, key=lambda x: (CLASS_PRIORITY.get(x[0], 0), x[1]), reverse=True)
    used = np.zeros((h, w), dtype=np.float32)
    results: list[LabelInstance] = []

    for class_id, conf, mask in sorted_inst:
        if mask.sum() < frame_area * min_area_frac:
            continue
        overlap = (mask * used).sum() / max(1, mask.sum())
        if overlap > 0.5:
            continue
        poly = mask_to_polygon(mask)
        if poly is None or len(poly) < 3:
            continue
        results.append(LabelInstance(class_id=class_id, polygon=poly))
        used = np.maximum(used, mask * 0.5)

    return results


def write_yolo_label(path: Path, instances: list[LabelInstance]) -> None:
    lines = []
    for inst in instances:
        coords = " ".join(f"{x:.6f} {y:.6f}" for x, y in inst.polygon)
        lines.append(f"{inst.class_id} {coords}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def render_overlay(image: np.ndarray, instances: list[LabelInstance], out_path: Path) -> None:
    vis = image.copy()
    colors = [
        (0, 200, 0), (0, 0, 255), (255, 0, 0), (0, 165, 255),
        (128, 128, 128), (255, 255, 0), (255, 0, 255),
    ]
    h, w = vis.shape[:2]
    for inst in instances:
        pts = np.array([[int(x * w), int(y * h)] for x, y in inst.polygon], dtype=np.int32)
        color = colors[inst.class_id % len(colors)]
        cv2.polylines(vis, [pts], True, color, 2)
        if len(pts) > 0:
            cv2.putText(vis, CLASS_NAMES[inst.class_id], tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), vis)


def process_image(
    image_path: Path,
    sam: SAMSegmenter | None,
    use_sam: bool,
    grid_cols: int,
    grid_rows: int,
    min_area_frac: float,
) -> list[LabelInstance]:
    image = cv2.imread(str(image_path))
    if image is None:
        return []
    h, w = image.shape[:2]

    if use_sam and sam is not None:
        raw_masks = sam_propose_masks(sam, image, grid_cols, grid_rows)
    else:
        raw_masks = heuristic_segment(image)

    instances_raw: list[tuple[int, float, np.ndarray]] = []
    for mask in raw_masks:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_u8 = (mask > 0.5).astype(np.uint8)
        mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, kernel)
        mask = mask_u8.astype(np.float32)
        class_id, conf = classify_mask_region(image, mask)
        instances_raw.append((class_id, conf, mask))

    return resolve_instances(instances_raw, min_area_frac, h, w)


def main() -> None:
    args = parse_args()
    dataset = Path(args.dataset)
    class_hist: Counter[int] = Counter()
    sam_ok = False
    sam_fail_reason = ""

    sam = SAMSegmenter()
    if sam.is_loaded():
        sam_ok = True
        print("SAM probe PASSED — using MobileSAM for region proposals")
    else:
        sam_fail_reason = "SAM decoder probe failed or models missing"
        print(f"WARNING: {sam_fail_reason} — falling back to pure heuristics")

    run_dir = Path(args.output_run)
    run_dir.mkdir(parents=True, exist_ok=True)
    spot_check_paths: list[Path] = []

    stats = {"frames": 0, "labeled": 0, "empty": 0, "sam_used": sam_ok}

    for split in ("train", "val"):
        img_dir = dataset / "images" / split
        lbl_dir = dataset / "labels" / split
        if not img_dir.exists():
            print(f"Skipping missing split: {img_dir}")
            continue
        images = sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.png"))
        for img_path in images:
            stats["frames"] += 1
            instances = process_image(
                img_path, sam, use_sam=sam_ok,
                grid_cols=args.grid_cols, grid_rows=args.grid_rows,
                min_area_frac=args.min_area_frac,
            )
            lbl_path = lbl_dir / f"{img_path.stem}.txt"
            write_yolo_label(lbl_path, instances)
            if instances:
                stats["labeled"] += 1
                for inst in instances:
                    class_hist[inst.class_id] += 1
            else:
                stats["empty"] += 1
            if len(spot_check_paths) < args.spot_check:
                spot_check_paths.append(img_path)

    print("\n=== Label generation complete ===")
    print(f"Frames processed: {stats['frames']}")
    print(f"Frames with labels: {stats['labeled']}")
    print(f"Empty label files: {stats['empty']}")
    print(f"SAM used: {sam_ok}")
    if not sam_ok:
        print(f"SAM fallback reason: {sam_fail_reason}")
    print("\nPer-class histogram:")
    for cid in range(NUM_CLASSES):
        print(f"  {cid} {CLASS_NAMES[cid]}: {class_hist[cid]}")

    for i, img_path in enumerate(spot_check_paths):
        image = cv2.imread(str(img_path))
        lbl_path = dataset / "labels" / ("train" if "train" in str(img_path) else "val") / f"{img_path.stem}.txt"
        instances: list[LabelInstance] = []
        if lbl_path.exists() and lbl_path.read_text().strip():
            for line in lbl_path.read_text().strip().splitlines():
                parts = line.split()
                cid = int(parts[0])
                coords = [(float(parts[j]), float(parts[j + 1])) for j in range(1, len(parts), 2)]
                instances.append(LabelInstance(class_id=cid, polygon=coords))
        out = run_dir / f"overlay_{i:02d}_{img_path.name}"
        if image is not None:
            render_overlay(image, instances, out)
            print(f"Spot-check overlay: {out}")

    summary = {
        "stats": stats,
        "class_histogram": {CLASS_NAMES[k]: v for k, v in sorted(class_hist.items())},
        "sam_ok": sam_ok,
        "sam_fail_reason": sam_fail_reason if not sam_ok else None,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nSummary written to {run_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
