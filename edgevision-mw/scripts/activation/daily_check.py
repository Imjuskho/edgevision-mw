#!/usr/bin/env python3
"""Daily Discipline Check — the 3 numbers that matter every morning.

Usage:
    cd edgevision-mw
    POSTGRES_HOST=localhost .venv/bin/python scripts/activation/daily_check.py

Runs every morning. If any number is 0, it's your #1 priority.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session


async def check_nodes_online(db: AsyncSession) -> int:
    """How many nodes sent a heartbeat in the last 24h?"""
    result = await db.execute(
        text("""
            SELECT COUNT(DISTINCT node_id)
            FROM heartbeats
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)
    )
    return result.scalar() or 0


async def check_frames_captured(db: AsyncSession) -> int:
    """How many frames were captured in the last 24h?"""
    result = await db.execute(
        text("""
            SELECT COUNT(*)
            FROM annotations
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)
    )
    return result.scalar() or 0


async def check_events_detected(db: AsyncSession) -> int:
    """How many events were detected in the last 24h?"""
    result = await db.execute(
        text("""
            SELECT COUNT(*)
            FROM events
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)
    )
    return result.scalar() or 0


async def check_fleet_status(db: AsyncSession) -> dict:
    """Additional fleet health info."""
    result = await db.execute(
        text("""
            SELECT
                COUNT(*) as total_nodes,
                COUNT(CASE WHEN status = 'ONLINE' THEN 1 END) as online,
                COUNT(CASE WHEN status = 'OFFLINE' THEN 1 END) as offline,
                COUNT(CASE WHEN last_heartbeat_at > NOW() - INTERVAL '1 hour' THEN 1 END) as recent_1h,
                COUNT(CASE WHEN last_heartbeat_at > NOW() - INTERVAL '24 hours' THEN 1 END) as recent_24h
            FROM nodes
            WHERE is_enabled = true
        """)
    )
    row = result.fetchone()
    return {
        "total": row[0],
        "online": row[1],
        "offline": row[2],
        "recent_1h": row[3],
        "recent_24h": row[4],
    }


async def check_annotations_summary(db: AsyncSession) -> dict:
    """Annotation pipeline health."""
    result = await db.execute(
        text("""
            SELECT
                status,
                COUNT(*) as count
            FROM annotations
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY status
        """)
    )
    return {row[0]: row[1] for row in result.fetchall()}


async def main() -> None:
    print(f"\n{'=' * 55}")
    print(f"  EDGEVISION-MW DAILY DISCIPLINE CHECK")
    print(f"  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 55}\n")

    async with async_session() as db:
        nodes_online = await check_nodes_online(db)
        frames_captured = await check_frames_captured(db)
        events_detected = await check_events_detected(db)
        fleet = await check_fleet_status(db)
        annotations = await check_annotations_summary(db)

    # ── THE 3 NUMBERS ──
    print(f"  THE 3 NUMBERS:")
    print(f"  ─────────────────────────────────────────────")

    status_1 = "✓" if nodes_online > 0 else "✗ CRITICAL"
    status_2 = "✓" if frames_captured > 0 else "✗ CRITICAL"
    status_3 = "✓" if events_detected > 0 else "✗ CRITICAL"

    print(f"  1. Nodes online (24h):   {nodes_online:>6}  {status_1}")
    print(f"  2. Frames captured (24h): {frames_captured:>6}  {status_2}")
    print(f"  3. Events detected (24h): {events_detected:>6}  {status_3}")

    # ── FLEET HEALTH ──
    print(f"\n  FLEET HEALTH:")
    print(f"  ─────────────────────────────────────────────")
    print(f"  Total nodes:      {fleet['total']}")
    print(f"  ONLINE:           {fleet['online']}")
    print(f"  OFFLINE:          {fleet['offline']}")
    print(f"  Heartbeat (1h):   {fleet['recent_1h']}")
    print(f"  Heartbeat (24h):  {fleet['recent_24h']}")

    # ── ANNOTATION PIPELINE ──
    if annotations:
        print(f"\n  ANNOTATION PIPELINE (7 days):")
        print(f"  ─────────────────────────────────────────────")
        for status, count in sorted(annotations.items()):
            print(f"  {status}: {count}")

    # ── ALERTS ──
    alerts = []
    if nodes_online == 0:
        alerts.append("NO NODES ONLINE — Check hardware/connectivity")
    if fleet["offline"] > 0:
        alerts.append(f"{fleet['offline']} node(s) OFFLINE — Check power/network")
    if frames_captured == 0:
        alerts.append("NO FRAMES CAPTURED — Check camera/schedule")
    if events_detected == 0:
        alerts.append("NO EVENTS DETECTED — Check detection pipeline")

    if alerts:
        print(f"\n  ⚠ ALERTS:")
        for a in alerts:
            print(f"    → {a}")
    else:
        print(f"\n  ✓ All systems operational")

    print(f"\n{'=' * 55}\n")

    # Exit code: 1 if any critical alert
    sys.exit(1 if any("CRITICAL" in a for a in alerts) else 0)


if __name__ == "__main__":
    asyncio.run(main())
