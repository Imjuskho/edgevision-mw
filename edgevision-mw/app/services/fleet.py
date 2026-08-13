from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.enums import NodeStatus
from app.models.heartbeat import Heartbeat
from app.models.node import Node
from app.schemas.node import HeartbeatPayload, HeartbeatResponse

logger = logging.getLogger(__name__)


BATTERY_LOW_THRESHOLD = 20.0
TEMP_HIGH_THRESHOLD = 85.0
STORAGE_HIGH_THRESHOLD = 0.90


async def record_heartbeat(
    db: AsyncSession, node_id: UUID, payload: HeartbeatPayload
) -> HeartbeatResponse:
    now = datetime.now(UTC)

    heartbeat = Heartbeat(
        id=None,
        node_id=node_id,
        battery_voltage=payload.battery_voltage,
        solar_input_watts=payload.solar_input_watts,
        cpu_temp_celsius=payload.cpu_temp_celsius,
        gpu_utilization=payload.gpu_utilization,
        storage_used_gb=payload.storage_used_gb,
        storage_total_gb=payload.storage_total_gb,
        lte_rssi_dbm=payload.lte_rssi_dbm,
        camera_status=payload.camera_status,
        clock_drift_ms=payload.clock_drift_ms,
        events_captured=payload.events_captured,
        events_uploaded=payload.events_uploaded,
        bandwidth_mbps=payload.bandwidth_mbps,
        raw_diagnostics=payload.raw_diagnostics,
    )
    db.add(heartbeat)

    # Derive node status from telemetry instead of unconditionally setting ONLINE (C7)
    node_status = _derive_node_status(payload)

    await db.execute(
        update(Node)
        .where(Node.id == node_id)
        .values(
            last_heartbeat_at=now,
            status=node_status,
        )
    )
    await db.flush()

    # Retrieve and clear pending commands in same transaction
    node_result = await db.execute(select(Node).where(Node.id == node_id))
    node = node_result.scalar_one_or_none()
    pending_commands = []
    if node and node.network_config:
        network = dict(node.network_config) if node.network_config else {}
        pending_commands = network.pop("_pending_commands", [])
        if pending_commands:
            await db.execute(
                update(Node)
                .where(Node.id == node_id)
                .values(network_config=network)
            )

    await db.commit()

    # Post-commit: generate alerts and write audit_log entries
    alerts = check_node_health_from_payload(payload)

    if node and node.last_heartbeat_at:
        hours_since = (now - node.last_heartbeat_at).total_seconds() / 3600
        if hours_since > 6:
            alerts.append(f"OFFLINE for {hours_since:.1f} hours")

    for alert_msg in alerts:
        severity = "warning" if "WARNING" in alert_msg else "critical"
        audit = AuditLog(
            event_type="node_health_alert",
            severity=severity,
            actor_id=node_id,
            actor_type="NODE",
            resource_type="NODE",
            resource_id=node_id,
            details={"alert": alert_msg, "node_id": str(node_id)},
        )
        db.add(audit)
    if alerts:
        await db.commit()

    return HeartbeatResponse(
        received=True,
        alerts=alerts,
        commands=pending_commands,
    )


def check_node_health_from_payload(payload: HeartbeatPayload) -> list[str]:
    alerts: list[str] = []
    battery_pct = (payload.battery_voltage / 12.6) * 100
    if battery_pct < BATTERY_LOW_THRESHOLD:
        alerts.append(f"CRITICAL: Battery low ({battery_pct:.1f}%)")
    if payload.cpu_temp_celsius > TEMP_HIGH_THRESHOLD:
        alerts.append(f"WARNING: CPU temperature high ({payload.cpu_temp_celsius}C)")
    storage_pct = payload.storage_used_gb / max(payload.storage_total_gb, 0.001)
    if storage_pct > STORAGE_HIGH_THRESHOLD:
        alerts.append(f"WARNING: Storage usage high ({storage_pct:.0%})")
    if payload.camera_status != "OK":
        alerts.append(f"WARNING: Camera status is {payload.camera_status}")
    return alerts


def _derive_node_status(payload: HeartbeatPayload) -> NodeStatus:
    """Derive node status from telemetry thresholds instead of always ONLINE.

    Priority: MAINTENANCE > OFFLINE-equivalent > DEGRADED > ONLINE
    """
    battery_pct = (payload.battery_voltage / 12.6) * 100
    storage_pct = payload.storage_used_gb / max(payload.storage_total_gb, 0.001)

    # Critical battery: node cannot operate → DEGRADED
    if battery_pct < BATTERY_LOW_THRESHOLD:
        return NodeStatus.DEGRADED

    # CPU overheating: risk of thermal shutdown → DEGRADED
    if payload.cpu_temp_celsius > TEMP_HIGH_THRESHOLD:
        return NodeStatus.DEGRADED

    # Storage full: cannot capture/store data → DEGRADED
    if storage_pct > STORAGE_HIGH_THRESHOLD:
        return NodeStatus.DEGRADED

    # No cellular signal: cannot upload → DEGRADED
    if payload.lte_rssi_dbm is not None and payload.lte_rssi_dbm < -110:
        return NodeStatus.DEGRADED

    return NodeStatus.ONLINE


HEARTBEAT_TIMEOUT_HOURS = 6.0


async def check_heartbeat_timeouts(db: AsyncSession) -> list[dict]:
    """Mark nodes as OFFLINE if no heartbeat received within timeout window.

    Called by a periodic Celery beat task.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=HEARTBEAT_TIMEOUT_HOURS)

    result = await db.execute(
        select(Node).where(
            Node.is_enabled.is_(True),
            Node.status != NodeStatus.OFFLINE,
        ).with_for_update(skip_locked=True)
    )
    nodes = result.scalars().all()

    timed_out = []
    for node in nodes:
        if node.last_heartbeat_at is None or node.last_heartbeat_at < cutoff:
            node.status = NodeStatus.OFFLINE
            timed_out.append({
                "node_id": node.node_id,
                "district": node.district,
                "last_heartbeat": node.last_heartbeat_at.isoformat() if node.last_heartbeat_at else None,
            })

    if timed_out:
        await db.commit()
        logger.warning("Marked %d nodes as OFFLINE (heartbeat timeout)", len(timed_out))

        # Write audit log
        from app.models.audit import AuditLog
        audit = AuditLog(
            event_type="NODES_TIMED_OUT",
            severity="WARNING",
            resource_type="fleet",
            details={
                "count": len(timed_out),
                "nodes": timed_out,
                "timeout_hours": HEARTBEAT_TIMEOUT_HOURS,
            },
            actor_type="SYSTEM",
        )
        db.add(audit)
        await db.commit()

    return timed_out


async def get_fleet_status(db: AsyncSession, filters: dict | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    query = select(Node)
    if filters:
        conditions = []
        if filters.get("district"):
            conditions.append(Node.district == filters["district"])
        if filters.get("category"):
            conditions.append(Node.category == filters["category"])
        if filters.get("status"):
            conditions.append(Node.status == filters["status"])
        if conditions:
            query = query.where(and_(*conditions))

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    nodes = result.scalars().all()
    if not nodes:
        return []

    node_ids = [node.id for node in nodes]
    node_map = {node.id: node for node in nodes}

    # Single query: latest heartbeat per node (avoids N+1)
    latest_subq = (
        select(
            Heartbeat.node_id,
            func.max(Heartbeat.created_at).label("max_ts"),
        )
        .where(Heartbeat.node_id.in_(node_ids))
        .group_by(Heartbeat.node_id)
        .subquery()
    )
    hb_result = await db.execute(
        select(Heartbeat).join(
            latest_subq,
            and_(
                Heartbeat.node_id == latest_subq.c.node_id,
                Heartbeat.created_at == latest_subq.c.max_ts,
            ),
        )
    )
    latest_hbs = {hb.node_id: hb for hb in hb_result.scalars().all()}

    fleet = []
    for node_id, node in node_map.items():
        latest_hb = latest_hbs.get(node_id)
        battery_pct = 0.0
        storage_pct = 0.0
        if latest_hb:
            battery_pct = (latest_hb.battery_voltage / 12.6) * 100
            storage_pct = (
                latest_hb.storage_used_gb / max(latest_hb.storage_total_gb, 0.001)
            ) * 100
        fleet.append(
            {
                "node_id": node.node_id,
                "status": node.status.value if hasattr(node.status, "value") else node.status,
                "battery_pct": round(battery_pct, 1),
                "storage_pct": round(storage_pct, 1),
                "last_sync": node.last_heartbeat_at,
                "district": node.district,
                "category": node.category.value if hasattr(node.category, "value") else node.category,
            }
        )
    return fleet


async def get_node_detail(db: AsyncSession, node_id: str) -> dict | None:
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if node is None:
        return None

    hb_result = await db.execute(
        select(Heartbeat)
        .where(Heartbeat.node_id == node.id)
        .order_by(Heartbeat.created_at.desc())
        .limit(10)
    )
    recent_hbs = hb_result.scalars().all()

    return {
        "node": node,
        "recent_heartbeats": recent_hbs,
    }


async def send_node_command(
    db: AsyncSession, node_id: str, command: dict
) -> bool:
    # First resolve the string node_id to the internal UUID primary key
    node_uuid = await db.scalar(select(Node.id).where(Node.node_id == node_id))
    if node_uuid is None:
        return False

    # Store command in network_config._pending_commands
    result = await db.execute(select(Node.network_config).where(Node.id == node_uuid))
    current_network = result.scalar_one_or_none()
    network = dict(current_network) if current_network else {}
    pending = network.get("_pending_commands", [])
    pending.append({
        "command": command.get("command"),
        "payload": command.get("payload", {}),
        "created_at": datetime.now(UTC).isoformat(),
    })
    network["_pending_commands"] = pending[-10:]  # keep last 10

    await db.execute(
        update(Node)
        .where(Node.id == node_uuid)
        .values(network_config=network)
    )
    await db.commit()
    return True


async def get_telemetry(
    db: AsyncSession, node_id: str, hours: int = 24
) -> list[dict]:
    node_result = await db.execute(select(Node.id).where(Node.node_id == node_id))
    node_uuid = node_result.scalar_one_or_none()
    if node_uuid is None:
        return []

    since = datetime.now(UTC) - timedelta(hours=hours)
    result = await db.execute(
        select(Heartbeat)
        .where(
            Heartbeat.node_id == node_uuid,
            Heartbeat.created_at >= since,
        )
        .order_by(Heartbeat.created_at.asc())
    )
    heartbeats = result.scalars().all()

    return [
        {
            "timestamp": hb.created_at.isoformat(),
            "battery_voltage": hb.battery_voltage,
            "cpu_temp_celsius": hb.cpu_temp_celsius,
            "storage_used_gb": hb.storage_used_gb,
            "lte_rssi_dbm": hb.lte_rssi_dbm,
            "events_captured": hb.events_captured,
            "events_uploaded": hb.events_uploaded,
            "bandwidth_mbps": hb.bandwidth_mbps,
        }
        for hb in heartbeats
    ]


async def get_active_alerts(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    count_result = await db.execute(
        select(func.count(Node.id)).where(Node.is_enabled == True)  # noqa: E712
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Node)
        .where(Node.is_enabled == True)  # noqa: E712
        .limit(limit)
        .offset(offset)
    )
    nodes = result.scalars().all()
    if not nodes:
        return {"items": [], "total": total, "limit": limit, "offset": offset}

    node_ids = [node.id for node in nodes]
    node_map = {node.id: node for node in nodes}

    # Single query: latest heartbeat per node (avoids N+1)
    latest_subq = (
        select(
            Heartbeat.node_id,
            func.max(Heartbeat.created_at).label("max_ts"),
        )
        .where(Heartbeat.node_id.in_(node_ids))
        .group_by(Heartbeat.node_id)
        .subquery()
    )
    hb_result = await db.execute(
        select(Heartbeat).join(
            latest_subq,
            and_(
                Heartbeat.node_id == latest_subq.c.node_id,
                Heartbeat.created_at == latest_subq.c.max_ts,
            ),
        )
    )
    latest_hbs = {hb.node_id: hb for hb in hb_result.scalars().all()}

    alerts: list[dict] = []
    for node_id, node in node_map.items():
        latest_hb = latest_hbs.get(node_id)
        if latest_hb is None:
            alerts.append(
                {
                    "node_id": node.node_id,
                    "node_uuid": str(node.id),
                    "district": node.district,
                    "alerts": ["CRITICAL: No heartbeat received"],
                }
            )
            continue

        battery_pct = (latest_hb.battery_voltage / 12.6) * 100
        node_alerts: list[str] = []
        if node.last_heartbeat_at:
            hours_since = (datetime.now(UTC) - node.last_heartbeat_at).total_seconds() / 3600
            if hours_since > 6:
                node_alerts.append(f"OFFLINE for {hours_since:.1f} hours (no heartbeat)")
        if battery_pct < BATTERY_LOW_THRESHOLD:
            node_alerts.append(f"Battery low ({battery_pct:.1f}%)")
        if latest_hb.cpu_temp_celsius > TEMP_HIGH_THRESHOLD:
            node_alerts.append(f"CPU temp high ({latest_hb.cpu_temp_celsius}C)")
        storage_pct = latest_hb.storage_used_gb / max(latest_hb.storage_total_gb, 0.001)
        if storage_pct > STORAGE_HIGH_THRESHOLD:
            node_alerts.append(f"Storage high ({storage_pct:.0%})")
        if latest_hb.camera_status != "OK":
            node_alerts.append(f"Camera: {latest_hb.camera_status}")

        if node_alerts:
            alerts.append(
                {
                    "node_id": node.node_id,
                    "node_uuid": str(node.id),
                    "district": node.district,
                    "alerts": node_alerts,
                }
            )

    return {"items": alerts, "total": total, "limit": limit, "offset": offset}
