#!/usr/bin/env python3
"""P1.2 — Process real frames through the ingestion → auto-label pipeline.

Usage:
    cd edgevision-mw
    POSTGRES_HOST=localhost .venv/bin/python scripts/activation/process_batch.py \
        --frames /path/to/frames/ \
        --node LIL-TRUST-001

Steps:
  1. Creates an IngestionBatch record
  2. Writes frames to local storage (fallback when MinIO is down)
  3. Dispatches auto_label_task via Celery
  4. Polls for completion
  5. Reports annotation count
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session
from app.models.enums import BatchStatus
from app.models.ingestion import IngestionBatch
from app.models.node import Node


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def create_batch(db, node: Node, frame_count: int, total_bytes: int, checksum: str) -> IngestionBatch:
    """Create an IngestionBatch record."""
    batch_id = f"batch_{node.node_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    batch = IngestionBatch(
        id=uuid4(),
        batch_id=batch_id,
        node_id=node.id,
        hub_id="HUB-001",
        event_count=frame_count,
        file_size_bytes=total_bytes,
        checksum_sha256=checksum,
        node_signature=b"dev-mode-no-sig",
        compression_codec="jpg",
        status=BatchStatus.PENDING,
        quality_scores={},
        storage_path=f"raw/{node.node_id}/{batch_id}/",
    )
    db.add(batch)
    await db.flush()
    print(f"  Created batch {batch_id} ({frame_count} frames, {total_bytes / 1024:.0f} KB)")
    return batch


async def dispatch_autolabel(batch_id: str) -> str:
    """Dispatch auto_label task via Celery and return task ID."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    from app.workers.celery_app import celery_app

    result = celery_app.send_task(
        "workers.auto_label",
        args=[batch_id],
        kwargs={},
    )
    print(f"  Dispatched auto_label task: {result.id}")
    return result.id


async def poll_task(task_id: str, timeout_s: int = 120) -> str:
    """Poll Celery task until SUCCESS/FAILURE or timeout."""
    import time
    from app.workers.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    start = time.time()
    while time.time() - start < timeout_s:
        if result.state in ("SUCCESS", "FAILURE"):
            break
        time.sleep(2)

    print(f"  Task {task_id[:12]}... → {result.state}")
    if result.state == "SUCCESS":
        print(f"  Result: {result.result}")
    elif result.state == "FAILURE":
        print(f"  Error: {result.info}")
    return result.state


async def main() -> None:
    parser = argparse.ArgumentParser(description="Process a batch of frames")
    parser.add_argument("--frames", required=True, help="Directory containing .jpg/.png frames")
    parser.add_argument("--node", default="LIL-TRUST-001", help="Node ID to associate with the batch")
    args = parser.parse_args()

    frames_dir = Path(args.frames)
    if not frames_dir.is_dir():
        print(f"  ERROR: {frames_dir} is not a directory")
        sys.exit(1)

    frame_files = sorted(
        [f for f in frames_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
    )
    if not frame_files:
        print(f"  ERROR: No .jpg/.png files found in {frames_dir}")
        sys.exit(1)

    print(f"[P1.2] Processing {len(frame_files)} frames from {frames_dir}")

    # Compute total size + checksum
    total_bytes = 0
    sha = hashlib.sha256()
    for f in frame_files:
        data = f.read_bytes()
        total_bytes += len(data)
        sha.update(data)
    checksum = sha.hexdigest()

    async with async_session() as db:
        async with db.begin():
            # Find or create the node
            result = await db.execute(select(Node).where(Node.node_id == args.node))
            node = result.scalar_one_or_none()
            if node is None:
                print(f"  ERROR: Node {args.node} not found. Run register_node.py first.")
                sys.exit(1)

            batch = await create_batch(db, node, len(frame_files), total_bytes, checksum)

            # Write frames to local storage
            storage_dir = Path("/tmp/edgevision_frames") / batch.batch_id
            storage_dir.mkdir(parents=True, exist_ok=True)
            for idx, f in enumerate(frame_files):
                dest = storage_dir / f"{idx}.jpg"
                dest.write_bytes(f.read_bytes())
            print(f"  Wrote {len(frame_files)} frames to {storage_dir}")

        await db.commit()

    # Dispatch Celery task (requires a running worker)
    import os as _os
    skip_celery = _os.environ.get("SKIP_CELERY", "0") == "1"
    if skip_celery:
        print(f"\n  SKIP_CELERY=1: Skipping Celery dispatch. Batch {batch.batch_id} created.")
        print(f"  To process: start worker, then run:")
        print(f"    from app.workers.tasks import auto_label_task")
        print(f"    auto_label_task.delay('{batch.batch_id}')")
        return

    print(f"\n  Dispatching auto_label for batch {batch.batch_id} ...")
    task_id = await dispatch_autolabel(batch.batch_id)

    # Poll for completion
    print(f"  Waiting for task to complete (timeout=120s) ...")
    final_state = await poll_task(task_id, timeout_s=120)

    # Report
    async with async_session() as db:
        result = await db.execute(
            select(IngestionBatch).where(IngestionBatch.batch_id == batch.batch_id)
        )
        b = result.scalar_one_or_none()
        if b:
            print(f"\n  Batch status: {b.status}")
            print(f"  Events processed: {b.event_count}")

    if final_state == "SUCCESS":
        print(f"\n  ✓ Batch processed successfully")
    else:
        print(f"\n  ✗ Batch processing ended with state: {final_state}")


if __name__ == "__main__":
    asyncio.run(main())
