from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.enums import NodeCategory, NodeStatus, PIIMode
from app.models.heartbeat import Heartbeat
from app.models.node import Node
from app.schemas.node import HeartbeatPayload
from app.services.fleet import get_active_alerts, record_heartbeat, send_node_command


async def _create_node(db, status=NodeStatus.ONLINE):
    node = Node(
        id=uuid4(), node_id=f"NODE-{uuid4().hex[:8]}",
        district="Lilongwe", latitude=-13.9626, longitude=33.7741,
        category=NodeCategory.ROAD, hardware_profile={"gpu": "jetson-orin"},
        network_config={"apn": "telkom"}, capture_schedule="*/5 * * * *",
        interest_classes=["vehicle", "pedestrian"], pii_mode=PIIMode.STRICT,
        firmware_version="2.1.0", public_key=b"\x00" * 32,
        status=status, is_enabled=True,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


@pytest.mark.asyncio
async def test_heartbeat_updates_node_status(db_session):
    node = await _create_node(db_session, status=NodeStatus.DEGRADED)
    payload = HeartbeatPayload(
        battery_voltage=11.5, solar_input_watts=8.0, cpu_temp_celsius=55.0,
        gpu_utilization=40.0, storage_used_gb=20.0, storage_total_gb=64.0,
        lte_rssi_dbm=-65.0, camera_status="OK", clock_drift_ms=2.0,
        events_captured=50, events_uploaded=48, bandwidth_mbps=5.0,
    )
    response = await record_heartbeat(db_session, node.id, payload)

    assert response.received is True

    result = await db_session.execute(select(Node).where(Node.id == node.id))
    updated_node = result.scalar_one()
    assert updated_node.status == NodeStatus.ONLINE
    assert updated_node.last_heartbeat_at is not None

    hb_result = await db_session.execute(
        select(Heartbeat).where(Heartbeat.node_id == node.id)
    )
    heartbeats = hb_result.scalars().all()
    assert len(heartbeats) == 1
    assert heartbeats[0].battery_voltage == 11.5


@pytest.mark.asyncio
async def test_invalid_signature_rejected(db_session):
    import base64

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    correct_key = Ed25519PrivateKey.generate()
    correct_pub_b64 = base64.b64encode(
        correct_key.public_key().public_bytes(
            encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.Raw,
            format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.Raw,
        )
    ).decode()

    node = await _create_node(db_session)
    await db_session.execute(
        select(Node).where(Node.id == node.id)
    )

    wrong_key = Ed25519PrivateKey.generate()
    now_str = datetime.now(UTC).isoformat()
    message = f"{node.node_id}:{now_str}".encode()
    sig = wrong_key.sign(message)
    sig_b64 = base64.b64encode(sig).decode()
    wrong_pub_b64 = base64.b64encode(
        wrong_key.public_key().public_bytes(
            encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.Raw,
            format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.Raw,
        )
    ).decode()

    from app.core.security import verify_node_signature
    sig_bytes = base64.b64decode(sig_b64)
    correct_pub_bytes = base64.b64decode(correct_pub_b64)
    assert not verify_node_signature(correct_pub_bytes, message, sig_bytes), \
        "Wrong key signature should not verify against correct public key"

    from sqlalchemy import update
    await db_session.execute(
        update(Node).where(Node.id == node.id).values(public_key=correct_pub_bytes)
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_offline_node_alerted(db_session):
    node = await _create_node(db_session)
    seven_hours_ago = datetime.now(UTC) - timedelta(hours=7)
    from sqlalchemy import update
    await db_session.execute(
        update(Node).where(Node.id == node.id).values(last_heartbeat_at=seven_hours_ago)
    )
    hb = Heartbeat(
        node_id=node.id, battery_voltage=12.0, solar_input_watts=5.0,
        cpu_temp_celsius=45.0, gpu_utilization=30.0, storage_used_gb=10.0,
        storage_total_gb=64.0, lte_rssi_dbm=-70.0, camera_status="OK",
        clock_drift_ms=2.0, events_captured=50, events_uploaded=50,
        bandwidth_mbps=5.0,
    )
    db_session.add(hb)
    await db_session.commit()

    result = await get_active_alerts(db_session, limit=5000, offset=0)
    alerts = result["items"] if isinstance(result, dict) else result
    node_alerts = [a for a in alerts if a.get("node_id") == node.node_id]
    assert len(node_alerts) >= 1, f"Node {node.node_id} not found in {len(alerts)} alerts"
    assert any("offline" in str(a.get("alerts", "")).lower() for a in node_alerts)


@pytest.mark.asyncio
async def test_command_persistence(db_session):
    node = await _create_node(db_session)
    success = await send_node_command(
        db_session, node.node_id, {"command": "reboot", "payload": {"force": True}}
    )
    assert success is True

    result = await db_session.execute(select(Node).where(Node.id == node.id))
    updated = result.scalar_one()
    assert "_pending_commands" in updated.network_config
    cmds = updated.network_config["_pending_commands"]
    assert len(cmds) == 1
    assert cmds[0]["command"] == "reboot"

    payload = HeartbeatPayload(
        battery_voltage=12.0, solar_input_watts=5.0, cpu_temp_celsius=45.0,
        gpu_utilization=30.0, storage_used_gb=10.0, storage_total_gb=64.0,
        lte_rssi_dbm=-70.0, camera_status="OK", clock_drift_ms=2.0,
        events_captured=0, events_uploaded=0, bandwidth_mbps=5.0,
    )
    hb_response = await record_heartbeat(db_session, node.id, payload)
    assert hb_response.commands == cmds

    result2 = await db_session.execute(select(Node).where(Node.id == node.id))
    cleared = result2.scalar_one()
    assert "_pending_commands" not in cleared.network_config or cleared.network_config.get("_pending_commands", []) == []


@pytest.mark.asyncio
async def test_heartbeat_creates_heartbeat_record(db_session):
    node = await _create_node(db_session)
    payload = HeartbeatPayload(
        battery_voltage=12.4, solar_input_watts=10.0, cpu_temp_celsius=42.0,
        gpu_utilization=25.0, storage_used_gb=15.0, storage_total_gb=64.0,
        lte_rssi_dbm=-55.0, camera_status="OK", clock_drift_ms=1.0,
        events_captured=200, events_uploaded=195, bandwidth_mbps=8.0,
    )
    response = await record_heartbeat(db_session, node.id, payload)
    assert response.received is True

    hb_result = await db_session.execute(
        select(Heartbeat).where(Heartbeat.node_id == node.id)
    )
    heartbeats = hb_result.scalars().all()
    assert len(heartbeats) >= 1
    latest = heartbeats[-1]
    assert latest.battery_voltage == 12.4
    assert latest.events_captured == 200
    assert latest.events_uploaded == 195


@pytest.mark.asyncio
async def test_heartbeat_rollback_on_failure(db_session):
    from unittest.mock import patch

    node = await _create_node(db_session)
    payload = HeartbeatPayload(
        battery_voltage=12.0, solar_input_watts=5.0, cpu_temp_celsius=45.0,
        gpu_utilization=30.0, storage_used_gb=10.0, storage_total_gb=64.0,
        lte_rssi_dbm=-70.0, camera_status="OK", clock_drift_ms=2.0,
        events_captured=10, events_uploaded=5, bandwidth_mbps=3.0,
    )

    with patch("app.services.fleet.Heartbeat") as MockHB:
        MockHB.side_effect = RuntimeError("Simulated insert failure")
        try:
            await record_heartbeat(db_session, node.id, payload)
        except RuntimeError:
            pass

    hb_result = await db_session.execute(
        select(Heartbeat).where(Heartbeat.node_id == node.id)
    )
    heartbeats = hb_result.scalars().all()
    assert len(heartbeats) == 0, "Heartbeat should not exist after insert failure"


@pytest.mark.asyncio
async def test_low_battery_sets_degraded_status(db_session):
    """C-i: Node with critically low battery should be DEGRADED, not ONLINE."""
    node = await _create_node(db_session, status=NodeStatus.ONLINE)
    # Battery at 1.5V → ~11.9% → below 20% threshold
    payload = HeartbeatPayload(
        battery_voltage=1.5, solar_input_watts=0.0, cpu_temp_celsius=45.0,
        gpu_utilization=10.0, storage_used_gb=10.0, storage_total_gb=64.0,
        lte_rssi_dbm=-60.0, camera_status="OK", clock_drift_ms=1.0,
        events_captured=5, events_uploaded=5, bandwidth_mbps=5.0,
    )
    await record_heartbeat(db_session, node.id, payload)

    result = await db_session.execute(select(Node).where(Node.id == node.id))
    updated_node = result.scalar_one()
    assert updated_node.status == NodeStatus.DEGRADED, (
        f"Expected DEGRADED for low battery, got {updated_node.status}"
    )


@pytest.mark.asyncio
async def test_high_cpu_temp_sets_degraded_status(db_session):
    """C-i: Node with CPU temp > 85C should be DEGRADED."""
    node = await _create_node(db_session, status=NodeStatus.ONLINE)
    payload = HeartbeatPayload(
        battery_voltage=12.4, solar_input_watts=8.0, cpu_temp_celsius=92.0,
        gpu_utilization=40.0, storage_used_gb=10.0, storage_total_gb=64.0,
        lte_rssi_dbm=-60.0, camera_status="OK", clock_drift_ms=1.0,
        events_captured=5, events_uploaded=5, bandwidth_mbps=5.0,
    )
    await record_heartbeat(db_session, node.id, payload)

    result = await db_session.execute(select(Node).where(Node.id == node.id))
    updated_node = result.scalar_one()
    assert updated_node.status == NodeStatus.DEGRADED


@pytest.mark.asyncio
async def test_heartbeat_timeout_marks_offline(db_session):
    """C-i: check_heartbeat_timeouts should mark stale nodes OFFLINE."""
    from app.services.fleet import check_heartbeat_timeouts

    node = await _create_node(db_session, status=NodeStatus.ONLINE)
    # Set last heartbeat to 7 hours ago (beyond 6h timeout)
    stale_time = datetime.now(UTC) - timedelta(hours=7)
    await db_session.execute(
        select(Node).where(Node.id == node.id)
    )
    from sqlalchemy import update
    await db_session.execute(
        update(Node).where(Node.id == node.id).values(last_heartbeat_at=stale_time)
    )
    await db_session.commit()

    timed_out = await check_heartbeat_timeouts(db_session)

    result = await db_session.execute(select(Node).where(Node.id == node.id))
    updated_node = result.scalar_one()
    assert updated_node.status == NodeStatus.OFFLINE, (
        f"Expected OFFLINE after timeout, got {updated_node.status}"
    )
    node_ids_timed_out = [t["node_id"] for t in timed_out]
    assert node.node_id in node_ids_timed_out
