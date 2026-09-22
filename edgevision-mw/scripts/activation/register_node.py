#!/usr/bin/env python3
"""P1.1 — Register a real node in the database.

Usage:
    cd edgevision-mw
    POSTGRES_HOST=localhost .venv/bin/python scripts/activation/register_node.py

Creates LIL-TRUST-001 at a configurable location and submits an initial
heartbeat so the node appears ONLINE in the fleet dashboard.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.models.enums import NodeCategory, NodeStatus, PIIMode
from app.models.heartbeat import Heartbeat
from app.models.node import Node

# ── Configuration ──────────────────────────────────────────────────
NODE_ID = "LIL-TRUST-001"
DISTRICT = "Lilongwe"
LATITUDE = -13.9620
LONGITUDE = 33.7740
AREA = "Old Town / Malangalanga Rd"
CATEGORY = NodeCategory.ROAD
PII_MODE = PIIMode.STRICT

HARDWARE_PROFILE = {
    "camera": {"resolution": [1920, 1080], "fps": 5, "codec": "h264"},
    "soc": "Raspberry Pi 5",
    "storage_gb": 64,
    "solar_panel_watts": 100,
    "battery_ah": 20,
}

NETWORK_CONFIG = {
    "apn": "tm",
    "signal_type": "4G",
    "proxy": None,
}

CAPTURE_SCHEDULE = "*/5 6-18 * * *"  # Every 5 min, 06:00–18:00
INTEREST_CLASSES = ["car", "truck", "bus", "motorcycle", "bicycle", "pedestrian"]
FIRMWARE_VERSION = "1.0.0"
# Ed25519 public key placeholder — replace with real key in production
PUBLIC_KEY = b"placeholder-public-key-for-testing"


async def register_node(db: AsyncSession) -> Node:
    """Insert or fetch the node record."""
    result = await db.execute(select(Node).where(Node.node_id == NODE_ID))
    existing = result.scalar_one_or_none()
    if existing:
        print(f"  Node {NODE_ID} already exists (id={existing.id}), skipping insert.")
        return existing

    node = Node(
        id=uuid4(),
        node_id=NODE_ID,
        district=DISTRICT,
        latitude=LATITUDE,
        longitude=LONGITUDE,
        category=CATEGORY,
        hardware_profile=HARDWARE_PROFILE,
        network_config=NETWORK_CONFIG,
        capture_schedule=CAPTURE_SCHEDULE,
        interest_classes=INTEREST_CLASSES,
        pii_mode=PII_MODE,
        firmware_version=FIRMWARE_VERSION,
        public_key=PUBLIC_KEY,
        status=NodeStatus.ONLINE,
        is_enabled=True,
    )
    db.add(node)
    await db.flush()
    print(f"  Registered node {NODE_ID} (id={node.id})")
    return node


async def submit_heartbeat(db: AsyncSession, node: Node) -> Heartbeat:
    """Write the first heartbeat so the fleet dashboard shows the node online."""
    hb = Heartbeat(
        id=uuid4(),
        node_id=node.id,
        battery_voltage=12.4,
        solar_input_watts=45.0,
        cpu_temp_celsius=42.0,
        gpu_utilization=0.0,
        storage_used_gb=12.5,
        storage_total_gb=64.0,
        lte_rssi_dbm=-78.0,
        camera_status="ACTIVE",
        clock_drift_ms=1.2,
        events_captured=0,
        events_uploaded=0,
        bandwidth_mbps=2.5,
    )
    db.add(hb)
    node.last_heartbeat_at = datetime.now(UTC)
    node.status = NodeStatus.ONLINE
    print(f"  Heartbeat submitted for {NODE_ID}")
    return hb


async def main() -> None:
    print(f"[P1.1] Registering node {NODE_ID} ...")
    async with async_session() as db:
        async with db.begin():
            node = await register_node(db)
            await submit_heartbeat(db, node)
        await db.commit()

    # Verify
    async with async_session() as db:
        result = await db.execute(select(Node).where(Node.node_id == NODE_ID))
        node = result.scalar_one_or_none()
        if node:
            print(f"\n  ✓ Node {NODE_ID} is in the database")
            print(f"    Status:     {node.status}")
            print(f"    Lat/Lng:    {node.latitude}, {node.longitude}")
            print(f"    Category:   {node.category}")
            print(f"    Last HB:    {node.last_heartbeat_at}")
        else:
            print(f"\n  ✗ Node {NODE_ID} NOT found — registration failed")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
