"""Tests for the Operator Console API (D1)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import NodeCategory, NodeStatus, PIIMode
from app.models.node import Node
from app.models.operator import OperatorAccount, OperatorPayout
from app.models.operator_alert import OperatorAlert


async def _create_operator(db: AsyncSession, *, phone: str = "+265999123456") -> OperatorAccount:
    op = OperatorAccount(
        id=uuid4(),
        phone_number=phone,
        full_name="Test Operator",
    )
    db.add(op)
    await db.flush()
    return op


async def _create_node_in_db(db: AsyncSession) -> Node:
    node = Node(
        id=uuid4(),
        node_id=f"NODE-{uuid4().hex[:8]}",
        district="Lilongwe",
        latitude=-13.9626,
        longitude=33.7741,
        category=NodeCategory.ROAD,
        hardware_profile={},
        network_config={},
        capture_schedule="*/10 * * * *",
        interest_classes=["vehicle"],
        pii_mode=PIIMode.STRICT,
        public_key=b"\x01" * 32,
        firmware_version="1.0.0",
        status=NodeStatus.ONLINE,
        is_enabled=True,
    )
    db.add(node)
    await db.flush()
    return node


def _operator_token(operator_id: str) -> str:
    return create_access_token(data={"sub": operator_id, "role": "OPERATOR", "phone": "+265999123456"})


# ── OTP Request ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_otp_request_returns_hint_in_dev(test_client: AsyncClient):
    resp = await test_client.post("/api/v1/operator/auth/otp-request", json={"phone_number": "+265999111111"})
    assert resp.status_code == 200
    data = resp.json()
    assert "otp_dev_hint" in data
    assert len(data["otp_dev_hint"]) == 6


@pytest.mark.asyncio
async def test_otp_verify_returns_token(test_client: AsyncClient):
    # Register operator first
    await test_client.post(
        "/api/v1/operator/auth/register",
        json={
            "phone_number": "+265999222222",
            "full_name": "OTP Test Operator",
            "village": "Lilongwe",
            "district": "Lilongwe",
            "language_preference": "ny",
        },
    )
    # Request OTP
    await test_client.post("/api/v1/operator/auth/otp-request", json={"phone_number": "+265999222222"})
    # Get the OTP from the store (dev hint)
    resp = await test_client.post("/api/v1/operator/auth/otp-request", json={"phone_number": "+265999222222"})
    otp_code = resp.json()["otp_dev_hint"]

    resp = await test_client.post(
        "/api/v1/operator/auth/otp-verify",
        json={"phone_number": "+265999222222", "otp_code": otp_code},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_otp_verify_unregistered_returns_404(test_client: AsyncClient):
    """OTP verify should return 404 if operator has not registered."""
    await test_client.post("/api/v1/operator/auth/otp-request", json={"phone_number": "+265999999999"})
    resp = await test_client.post("/api/v1/operator/auth/otp-request", json={"phone_number": "+265999999999"})
    otp_code = resp.json()["otp_dev_hint"]

    resp = await test_client.post(
        "/api/v1/operator/auth/otp-verify",
        json={"phone_number": "+265999999999", "otp_code": otp_code},
    )
    assert resp.status_code == 404
    assert "register" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_otp_verify_wrong_code(test_client: AsyncClient):
    await test_client.post("/api/v1/operator/auth/otp-request", json={"phone_number": "+265999333333"})
    resp = await test_client.post(
        "/api/v1/operator/auth/otp-verify",
        json={"phone_number": "+265999333333", "otp_code": "000000"},
    )
    assert resp.status_code == 400
    assert "Invalid OTP" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_otp_verify_not_requested(test_client: AsyncClient):
    resp = await test_client.post(
        "/api/v1/operator/auth/otp-verify",
        json={"phone_number": "+265999000000", "otp_code": "123456"},
    )
    assert resp.status_code == 400
    assert "not requested" in resp.json()["detail"]


# ── Register ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_register_operator(test_client: AsyncClient):
    resp = await test_client.post(
        "/api/v1/operator/auth/register",
        json={
            "phone_number": "+265999444444",
            "full_name": "Chikondi Banda",
            "village": "Nkhata Bay",
            "district": "Nkhata Bay",
            "language_preference": "ny",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["full_name"] == "Chikondi Banda"
    assert data["phone_number"] == "+265999444444"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_register_duplicate_phone(test_client: AsyncClient, db_session: AsyncSession):
    op = await _create_operator(db_session, phone="+265999555555")
    await db_session.commit()
    resp = await test_client.post(
        "/api/v1/operator/auth/register",
        json={"phone_number": "+265999555555", "full_name": "Duplicate"},
    )
    assert resp.status_code == 409


# ── Dashboard ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_dashboard_returns_operator_data(test_client: AsyncClient, db_session: AsyncSession):
    op = await _create_operator(db_session, phone="+265999666666")
    await db_session.commit()
    token = _operator_token(str(op.id))
    resp = await test_client.get(
        "/api/v1/operator/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["account"]["full_name"] == "Test Operator"
    assert "stipend_balance_mwk" in data


@pytest.mark.asyncio
async def test_dashboard_with_node(test_client: AsyncClient, db_session: AsyncSession):
    node = await _create_node_in_db(db_session)
    op = await _create_operator(db_session, phone="+265999777777")
    op.associated_node_id = node.id
    await db_session.commit()

    token = _operator_token(str(op.id))
    resp = await test_client.get(
        "/api/v1/operator/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_status"] is not None
    assert data["node_status"]["node_label"] == node.node_id


@pytest.mark.asyncio
async def test_dashboard_unauthenticated(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/operator/dashboard")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_dashboard_unknown_operator(test_client: AsyncClient):
    token = _operator_token(str(uuid4()))
    resp = await test_client.get(
        "/api/v1/operator/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── Alerts ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_alerts(test_client: AsyncClient, db_session: AsyncSession):
    node = await _create_node_in_db(db_session)
    op = await _create_operator(db_session, phone="+265999888888")
    alert = OperatorAlert(
        id=uuid4(),
        node_id=node.id,
        operator_id=op.id,
        alert_type="low_battery",
        message="Battery low",
        severity="warning",
    )
    db_session.add(alert)
    await db_session.commit()

    token = _operator_token(str(op.id))
    resp = await test_client.get(
        "/api/v1/operator/alerts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["alert_type"] == "low_battery"


@pytest.mark.asyncio
async def test_acknowledge_alert(test_client: AsyncClient, db_session: AsyncSession):
    node = await _create_node_in_db(db_session)
    op = await _create_operator(db_session, phone="+265999888889")
    alert = OperatorAlert(
        id=uuid4(),
        node_id=node.id,
        operator_id=op.id,
        alert_type="storage_full",
        message="Storage full",
        severity="critical",
    )
    db_session.add(alert)
    await db_session.commit()

    token = _operator_token(str(op.id))
    resp = await test_client.post(
        f"/api/v1/operator/alerts/{alert.id}/ack",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Alert acknowledged"


@pytest.mark.asyncio
async def test_acknowledge_alert_not_found(test_client: AsyncClient, db_session: AsyncSession):
    op = await _create_operator(db_session, phone="+265999888890")
    await db_session.commit()
    token = _operator_token(str(op.id))
    resp = await test_client.post(
        f"/api/v1/operator/alerts/{uuid4()}/ack",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── Payouts ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_payouts(test_client: AsyncClient, db_session: AsyncSession):
    op = await _create_operator(db_session, phone="+265999888891")
    payout = OperatorPayout(
        id=uuid4(),
        operator_id=op.id,
        amount_mwk=Decimal("42500.00"),
        period_start=datetime(2026, 7, 1, tzinfo=UTC),
        period_end=datetime(2026, 7, 31, tzinfo=UTC),
        status="paid",
    )
    db_session.add(payout)
    await db_session.commit()

    token = _operator_token(str(op.id))
    resp = await test_client.get(
        "/api/v1/operator/payouts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert float(data[0]["amount_mwk"]) == 42500.00


# ── Node Status ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_node_status(test_client: AsyncClient, db_session: AsyncSession):
    node = await _create_node_in_db(db_session)
    op = await _create_operator(db_session, phone="+265999888892")
    await db_session.commit()

    token = _operator_token(str(op.id))
    resp = await test_client.get(
        f"/api/v1/operator/nodes/{node.id}/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_label"] == node.node_id
    assert data["status"] == "ONLINE"


@pytest.mark.asyncio
async def test_get_node_status_not_found(test_client: AsyncClient, db_session: AsyncSession):
    op = await _create_operator(db_session, phone="+265999888893")
    await db_session.commit()
    token = _operator_token(str(op.id))
    resp = await test_client.get(
        f"/api/v1/operator/nodes/{uuid4()}/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
