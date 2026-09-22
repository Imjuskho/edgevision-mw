#!/usr/bin/env python3
"""Field Data Collector — Phone + Car workflow for Lilongwe data collection.

Workflow:
  1. Drive a route in Lilongwe with phone recording video or taking photos
  2. Copy files to a folder on your laptop
  3. Run this script — it handles everything else

Supports:
  - iPhone/Android photos (.jpg/.heic) with EXIF GPS
  - iPhone videos (.mov) and Android videos (.mp4)
  - Mixed folders (photos + videos together)
  - Automatic GPS extraction from EXIF
  - Frame extraction from video at configurable interval
  - Deduplication by perceptual hash
  - Batch creation + Celery dispatch

Usage:
    cd edgevision-mw
    POSTGRES_HOST=localhost .venv/bin/python scripts/activation/collect_field_data.py \
        --input /path/to/phone_files/ \
        --node LIL-TRUST-001 \
        --route "City Centre → Area 18 → Kanengo"

    # Or just extract frames from video without DB:
    POSTGRES_HOST=localhost .venv/bin/python scripts/activation/collect_field_data.py \
        --input /path/to/videos/ \
        --extract-only \
        --output /tmp/field_frames/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS


# ── GPS Extraction ─────────────────────────────────────────────────

def _convert_to_degrees(value) -> float:
    """Convert EXIF GPS coordinate to decimal degrees."""
    try:
        d = float(value[0])
        m = float(value[1])
        s = float(value[2])
        return d + (m / 60.0) + (s / 3600.0)
    except (TypeError, IndexError, ValueError):
        return 0.0


def extract_gps_from_image(filepath: Path) -> dict | None:
    """Extract GPS coordinates from image EXIF data."""
    try:
        img = Image.open(filepath)
        exif_data = img._getexif()
        if not exif_data:
            return None

        gps_info = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                for gps_tag_id, gps_value in value.items():
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_info[gps_tag] = gps_value

        if not gps_info:
            return None

        lat = gps_info.get("GPSLatitude")
        lat_ref = gps_info.get("GPSLatitudeRef", "N")
        lon = gps_info.get("GPSLongitude")
        lon_ref = gps_info.get("GPSLongitudeRef", "E")

        if lat and lon:
            lat_deg = _convert_to_degrees(lat)
            if lat_ref == "S":
                lat_deg = -lat_deg
            lon_deg = _convert_to_degrees(lon)
            if lon_ref == "W":
                lon_deg = -lon_deg

            result = {"latitude": round(lat_deg, 6), "longitude": round(lon_deg, 6)}

            # Extract timestamp
            ts = gps_info.get("GPSTimeStamp")
            ds = gps_info.get("GPSDateStamp")
            if ds and ts:
                result["gps_timestamp"] = f"{ds} {ts}"

            # Extract altitude
            alt = gps_info.get("GPSAltitude")
            alt_ref = gps_info.get("GPSAltitudeRef", 0)
            if alt:
                result["altitude_m"] = float(alt) * (-1 if alt_ref else 1)

            return result
    except Exception:
        pass
    return None


def extract_timestamp_from_image(filepath: Path) -> str | None:
    """Extract DateTimeOriginal from EXIF."""
    try:
        img = Image.open(filepath)
        exif_data = img._getexif()
        if exif_data:
            for tag_id, value in exif_data.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == "DateTimeOriginal":
                    return str(value)
    except Exception:
        pass
    return None


# ── Video Frame Extraction ─────────────────────────────────────────

def extract_frames_from_video(
    video_path: Path,
    output_dir: Path,
    interval_sec: float = 2.0,
    max_frames: int = 200,
    route_name: str = "",
    node_id: str = "",
) -> list[dict]:
    """Extract frames from a video file using the existing pipeline."""
    from app.services.video_processing import extract_video_frames

    content = video_path.read_bytes()
    probe, frames = extract_video_frames(
        content,
        video_path.name,
        interval_sec=interval_sec,
        max_frames=max_frames,
    )

    results = []
    for frame in frames:
        stem = f"{video_path.stem}_f{frame.index:04d}"
        filename = f"{stem}.jpg"
        out_path = output_dir / filename

        out_path.write_bytes(frame.jpeg_bytes)
        results.append({
            "filename": filename,
            "source": video_path.name,
            "type": "video_frame",
            "frame_index": frame.index,
            "timestamp_sec": round(frame.timestamp_sec, 3),
            "width": frame.width,
            "height": frame.height,
            "video_fps": round(probe.fps, 1),
            "route": route_name,
            "node_id": node_id,
        })

    return results


# ── Image Processing ───────────────────────────────────────────────

def process_image(
    filepath: Path,
    output_dir: Path,
    route_name: str = "",
    node_id: str = "",
) -> dict:
    """Process a single image: copy, extract GPS, extract timestamp."""
    # Read and convert to JPEG if needed
    try:
        img = Image.open(filepath)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        filename = f"{filepath.stem}.jpg"
        out_path = output_dir / filename

        if filepath.suffix.lower() in (".jpg", ".jpeg"):
            import shutil
            shutil.copy2(filepath, out_path)
        else:
            img.save(out_path, "JPEG", quality=95)
            filename = f"{filepath.stem}.jpg"
    except Exception as e:
        return {"filename": filepath.name, "error": str(e)}

    # Extract metadata
    gps = extract_gps_from_image(filepath)
    timestamp = extract_timestamp_from_image(filepath)

    return {
        "filename": filename,
        "source": filepath.name,
        "type": "photo",
        "width": img.size[0],
        "height": img.size[1],
        "gps": gps,
        "exif_timestamp": timestamp,
        "route": route_name,
        "node_id": node_id,
    }


# ── Deduplication ──────────────────────────────────────────────────

def perceptual_hash(filepath: Path) -> str | None:
    """Simple perceptual hash for dedup (average hash)."""
    try:
        img = Image.open(filepath).convert("L").resize((8, 8), Image.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p > avg else "0" for p in pixels)
        return hex(int(bits, 2))[2:].zfill(16)
    except Exception:
        return None


# ── Main ───────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".mov", ".mp4", ".m4v", ".mkv"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect field data from phone + car")
    parser.add_argument("--input", required=True, help="Directory with phone photos/videos")
    parser.add_argument("--node", default="LIL-TRUST-001", help="Node ID")
    parser.add_argument("--route", default="", help="Route description (e.g. 'City Centre → Kanengo')")
    parser.add_argument("--output", default="/tmp/field_frames", help="Output directory for processed frames")
    parser.add_argument("--interval", type=float, default=2.0, help="Video frame extraction interval (seconds)")
    parser.add_argument("--max-frames", type=int, default=200, help="Max frames per video")
    parser.add_argument("--extract-only", action="store_true", help="Only extract frames, skip DB batch creation")
    parser.add_argument("--dedup", action="store_true", help="Enable perceptual deduplication")
    parser.add_argument("--skip-celery", action="store_true", help="Skip Celery dispatch")
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"ERROR: {input_dir} is not a directory")
        sys.exit(1)

    # Collect all supported files
    files = sorted(
        f for f in input_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not files:
        print(f"ERROR: No supported files in {input_dir}")
        print(f"  Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        sys.exit(1)

    photos = [f for f in files if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic", ".heif"}]
    videos = [f for f in files if f.suffix.lower() in {".mov", ".mp4", ".m4v", ".mkv"}]

    print(f"\n{'=' * 60}")
    print(f"  EDGEVISION-MW FIELD DATA COLLECTOR")
    print(f"{'=' * 60}")
    print(f"  Input:     {input_dir}")
    print(f"  Node:      {args.node}")
    print(f"  Route:     {args.route or '(not specified)'}")
    print(f"  Photos:    {len(photos)}")
    print(f"  Videos:    {len(videos)}")
    print(f"  Output:    {args.output}")
    print(f"{'=' * 60}\n")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    gps_count = 0
    seen_hashes: set[str] = set()
    dedup_count = 0

    # Process photos
    for idx, photo in enumerate(photos, 1):
        print(f"  [{idx}/{len(photos)}] {photo.name} ...", end=" ", flush=True)

        # Dedup check
        if args.dedup:
            h = perceptual_hash(photo)
            if h and h in seen_hashes:
                print("DUP (skipped)")
                dedup_count += 1
                continue
            if h:
                seen_hashes.add(h)

        result = process_image(photo, output_dir, args.route, args.node)
        all_results.append(result)

        if result.get("gps"):
            gps_count += 1
            gps = result["gps"]
            print(f"✓ GPS: {gps['latitude']:.4f}, {gps['longitude']:.4f}")
        elif result.get("error"):
            print(f"✗ {result['error']}")
        else:
            print("✓ (no GPS)")

    # Process videos
    for idx, video in enumerate(videos, 1):
        print(f"\n  [Video {idx}/{len(videos)}] {video.name} ...")
        try:
            frames = extract_frames_from_video(
                video, output_dir,
                interval_sec=args.interval,
                max_frames=args.max_frames,
                route_name=args.route,
                node_id=args.node,
            )
            all_results.extend(frames)
            print(f"    Extracted {len(frames)} frames")
        except Exception as e:
            print(f"    ERROR: {e}")

    # Summary
    total = len(all_results)
    with_gps = sum(1 for r in all_results if r.get("gps"))

    print(f"\n{'=' * 60}")
    print(f"  EXTRACTION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Total frames:     {total}")
    print(f"  With GPS:         {with_gps}")
    print(f"  Duplicates found: {dedup_count}")
    print(f"  Output:           {output_dir}")

    # Save manifest
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "node_id": args.node,
        "route": args.route,
        "input_dir": str(input_dir),
        "total_frames": total,
        "with_gps": with_gps,
        "duplicates_skipped": dedup_count,
        "photos_input": len(photos),
        "videos_input": len(videos),
        "frames": all_results,
    }
    manifest_path = output_dir / "field_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"  Manifest:         {manifest_path}")

    # GPS summary
    if with_gps:
        lats = [r["gps"]["latitude"] for r in all_results if r.get("gps")]
        lons = [r["gps"]["longitude"] for r in all_results if r.get("gps")]
        print(f"\n  GPS Bounding Box:")
        print(f"    Lat: {min(lats):.4f} → {max(lats):.4f}")
        print(f"    Lon: {min(lons):.4f} → {max(lons):.4f}")

    # Create batch + dispatch to Celery
    if not args.extract_only and total > 0:
        print(f"\n  Creating ingestion batch ...")
        _create_batch_and_dispatch(
            output_dir, all_results, args.node, args.route, args.skip_celery
        )

    print(f"\n{'=' * 60}")
    print(f"  NEXT STEPS:")
    print(f"  1. Review frames in {output_dir}")
    print(f"  2. Run YOLO validation: python scripts/activation/validate_yolo.py --frames {output_dir}")
    print(f"  3. Check daily: python scripts/activation/daily_check.py")
    print(f"{'=' * 60}\n")


def _create_batch_and_dispatch(
    output_dir: Path,
    frames: list[dict],
    node_id: str,
    route: str,
    skip_celery: bool,
) -> None:
    """Create IngestionBatch and optionally dispatch Celery task."""
    import asyncio
    from uuid import uuid4

    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.enums import BatchStatus
    from app.models.ingestion import IngestionBatch
    from app.models.node import Node

    async def _run():
        async with async_session() as db:
            async with db.begin():
                result = await db.execute(select(Node).where(Node.node_id == node_id))
                node = result.scalar_one_or_none()
                if node is None:
                    print(f"    ERROR: Node {node_id} not found. Run register_node.py first.")
                    return

                # Compute total size
                total_bytes = sum(
                    (output_dir / f["filename"]).stat().st_size
                    for f in frames
                    if (output_dir / f["filename"]).exists()
                )

                # Compute checksum
                sha = hashlib.sha256()
                for f in sorted(output_dir.glob("*.jpg")):
                    sha.update(f.read_bytes())

                batch_id = f"batch_{node_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
                batch = IngestionBatch(
                    id=uuid4(),
                    batch_id=batch_id,
                    node_id=node.id,
                    hub_id="HUB-FIELD",
                    event_count=len(frames),
                    file_size_bytes=total_bytes,
                    checksum_sha256=sha.hexdigest(),
                    node_signature=b"field-collection-mode",
                    compression_codec="jpg",
                    status=BatchStatus.PENDING,
                    quality_scores={"route": route, "collection_method": "phone_car"},
                    storage_path=f"raw/{node_id}/{batch_id}/",
                )
                db.add(batch)
                print(f"    Batch {batch_id} created ({len(frames)} frames, {total_bytes / 1024:.0f} KB)")

            await db.commit()

            if not skip_celery:
                try:
                    from app.workers.celery_app import celery_app
                    task = celery_app.send_task("workers.auto_label", args=[batch_id])
                    print(f"    Celery task dispatched: {task.id}")
                    print(f"    Waiting for worker ...")

                    import time
                    for _ in range(30):
                        time.sleep(2)
                        if task.state in ("SUCCESS", "FAILURE"):
                            break
                    print(f"    Task state: {task.state}")
                    if task.state == "SUCCESS":
                        print(f"    ✓ Auto-labeling complete")
                except Exception as e:
                    print(f"    Celery dispatch failed: {e}")
                    print(f"    Start worker, then: auto_label_task.delay('{batch_id}')")

    asyncio.run(_run())


if __name__ == "__main__":
    main()
