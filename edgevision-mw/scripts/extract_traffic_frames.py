#!/usr/bin/env python3
"""
Extract JPEG frames from iPhone MOV files in Traffic Data/ for road-seg annotation.

Output layout (YOLO-seg ready — add labels/ manually or via Studio):
    datasets/road_seg_traffic/
        images/train/          # extracted frames
        images/val/
        labels/train/          # empty until annotated (YOLO-seg polygon .txt files)
        labels/val/
        manifest.json          # source video, timestamp, dimensions per frame

Usage:
    cd edgevision-mw
    python scripts/extract_traffic_frames.py
    python scripts/extract_traffic_frames.py --interval 2.0 --max-frames 60
    python scripts/extract_traffic_frames.py --input "Traffic Data" --output datasets/road_seg_traffic

After extraction, annotate polygon masks (7 road classes) then train:

    python scripts/train_road_seg.py --data road_dataset.yaml
    python scripts/export_road_seg_onnx.py --weights runs/segment/train/weights/best.pt --output models/road_seg/
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.video_processing import extract_video_frames  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract frames from Traffic Data MOV files")
    parser.add_argument(
        "--input",
        type=str,
        default=str(ROOT / "Traffic Data"),
        help="Directory containing .MOV/.MP4 files (default: Traffic Data/)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT / "datasets" / "road_seg_traffic"),
        help="Output dataset root (images/train + manifest.json)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between extracted frames (default: 1.0)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=120,
        help="Max frames per video (default: 120, matches upload API limit)",
    )
    parser.add_argument(
        "--split-val",
        type=float,
        default=0.15,
        help="Fraction of frames reserved for val/ (default: 0.15)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input)
    output_root = Path(args.output)
    images_train = output_root / "images" / "train"
    images_val = output_root / "images" / "val"
    labels_train = output_root / "labels" / "train"
    labels_val = output_root / "labels" / "val"

    for d in (images_train, images_val, labels_train, labels_val):
        d.mkdir(parents=True, exist_ok=True)

    if not input_dir.is_dir():
        print(f"ERROR: input directory not found: {input_dir}")
        print("Place iPhone MOV files in edgevision-mw/Traffic Data/ (gitignored, local only).")
        sys.exit(1)

    videos = sorted(
        p for p in input_dir.iterdir()
        if p.suffix.lower() in {".mov", ".mp4", ".m4v", ".mkv", ".webm"}
    )
    if not videos:
        print(f"ERROR: no video files in {input_dir}")
        sys.exit(1)

    manifest_entries: list[dict] = []
    pending: list[tuple[str, bytes, dict]] = []

    print(f"Input:  {input_dir} ({len(videos)} videos)")
    print(f"Output: {output_root}")
    print(f"Interval: {args.interval}s, max {args.max_frames} frames/video\n")

    for video_path in videos:
        print(f"  {video_path.name} ...", end=" ", flush=True)
        content = video_path.read_bytes()
        try:
            probe, frames = extract_video_frames(
                content,
                video_path.name,
                interval_sec=args.interval,
                max_frames=args.max_frames,
            )
        except Exception as exc:
            print(f"SKIP ({exc})")
            continue

        for frame in frames:
            stem = f"{video_path.stem}_f{frame.index:04d}_t{frame.timestamp_sec:.1f}s"
            meta = {
                "filename": f"{stem}.jpg",
                "source_video": video_path.name,
                "frame_index": frame.index,
                "timestamp_sec": round(frame.timestamp_sec, 3),
                "width": frame.width,
                "height": frame.height,
                "video_duration_sec": round(probe.duration_sec, 2),
                "video_fps": round(probe.fps, 2),
            }
            pending.append((f"{stem}.jpg", frame.jpeg_bytes, meta))

        print(f"{len(frames)} frames ({probe.width}x{probe.height}, {probe.duration_sec:.1f}s)")

    if not pending:
        print("\nERROR: no frames extracted")
        sys.exit(1)

    val_count = max(1, int(len(pending) * args.split_val)) if len(pending) > 5 else 0
    val_indices = set(range(0, len(pending), max(1, len(pending) // val_count))[:val_count])

    for idx, (filename, jpeg_bytes, meta) in enumerate(pending):
        split = "val" if idx in val_indices else "train"
        meta["split"] = split
        dest_dir = images_val if split == "val" else images_train
        (dest_dir / filename).write_bytes(jpeg_bytes)
        manifest_entries.append(meta)

    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "source_dir": str(input_dir),
        "interval_sec": args.interval,
        "max_frames_per_video": args.max_frames,
        "total_frames": len(manifest_entries),
        "train_frames": sum(1 for m in manifest_entries if m["split"] == "train"),
        "val_frames": sum(1 for m in manifest_entries if m["split"] == "val"),
        "road_classes": [
            "good_road", "pothole", "crack", "dust_road",
            "gravel_road", "road_marking", "shoulder",
        ],
        "annotation_format": "YOLO-seg polygon: class_id x1 y1 x2 y2 ... (normalized 0-1)",
        "frames": manifest_entries,
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"\nDone: {len(manifest_entries)} frames → {output_root}")
    print(f"  train: {manifest['train_frames']}  val: {manifest['val_frames']}")
    print(f"  manifest: {manifest_path}")
    print("\nNext steps:")
    print("  1. Annotate polygon masks (7 road classes) in Studio Live Annotate")
    print("  2. Export YOLO-seg .txt labels to labels/train/ and labels/val/")
    print("  3. Point road_dataset.yaml path at datasets/road_seg_traffic")
    print("  4. python scripts/train_road_seg.py --data road_dataset.yaml")
    print("  5. python scripts/export_road_seg_onnx.py --weights runs/segment/train/weights/best.pt --output models/road_seg/")


if __name__ == "__main__":
    main()
