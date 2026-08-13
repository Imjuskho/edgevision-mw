import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.buyer import User


@pytest.mark.asyncio
async def test_register_prevents_role_escalation(db_session, test_client):
    unique_email = f"admin-escalation-{uuid.uuid4().hex[:8]}@test.com"
    response = await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "securepass123",
            "full_name": "Sneaky User",
            "role": "ADMIN",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "ANNOTATOR", f"Role escalation prevented: got {data['role']}, expected ANNOTATOR"

    await db_session.commit()
    result = await db_session.execute(
        select(User).where(User.email == unique_email)
    )
    user = result.scalar_one()
    assert user.role == "ANNOTATOR"


@pytest.mark.asyncio
async def test_login_returns_valid_jwt(db_session, test_client):
    await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "jwt-test@test.com",
            "password": "securepass123",
            "full_name": "JWT Tester",
        },
    )
    login_resp = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "jwt-test@test.com", "password": "securepass123"},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["expires_in"] > 0

    from app.core.security import decode_access_token
    payload = decode_access_token(token_data["access_token"])
    assert "sub" in payload
    assert "role" in payload
    assert "exp" in payload
    assert payload["role"] == "BUYER"
    assert payload["email"] == "jwt-test@test.com"


@pytest.mark.asyncio
async def test_buyer_api_key_creation(db_session, test_client, api_key_factory):
    unique_email = f"apikey-test-{uuid.uuid4().hex[:8]}@test.com"
    reg = await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "securepass123",
            "full_name": "API Key Tester",
        },
    )
    user_id = reg.json()["id"]

    login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "securepass123"},
    )
    token = login.json()["access_token"]

    key_resp = await test_client.post(
        "/api/v1/auth/api-keys",
        json={"name": "test-key", "scopes": ["read"], "expires_in_days": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert key_resp.status_code == 201
    key_data = key_resp.json()
    assert "key" in key_data
    raw_key = key_data["key"]
    assert len(raw_key) > 20

    list_resp = await test_client.get(
        "/api/v1/auth/api-keys",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    keys = list_resp.json()
    assert len(keys) >= 1
    assert keys[0]["key"] == "****(redacted)"


@pytest.mark.asyncio
async def test_node_auth_rejected_on_jwt_routes(db_session, test_client, node_keypair_factory):
    private_key, public_key = node_keypair_factory()
    import base64

    pub_b64 = base64.b64encode(public_key).decode()
    node_id_str = str(uuid.uuid4())
    now_str = datetime.now(UTC).isoformat()
    message = f"{node_id_str}:{now_str}".encode()
    sig = private_key.sign(message)
    sig_b64 = base64.b64encode(sig).decode()

    resp = await test_client.post(
        "/api/v1/jobs/assign",
        headers={
            "X-Node-Id": node_id_str,
            "X-Node-Timestamp": now_str,
            "X-Node-Signature": sig_b64,
            "X-Node-Public-Key": pub_b64,
        },
    )
    assert resp.status_code == 401, f"Node auth not accepted on JWT routes: {resp.status_code} {resp.text}"


@pytest.mark.asyncio
async def test_node_headers_required_on_node_routes(db_session, test_client, jwt_token_factory):
    token = jwt_token_factory(role="ANNOTATOR", user_id=str(uuid.uuid4()))

    resp = await test_client.post(
        "/api/v1/nodes/heartbeat",
        json={
            "battery_voltage": 12.0,
            "solar_input_watts": 5.0,
            "cpu_temp_celsius": 45.0,
            "gpu_utilization": 30.0,
            "storage_used_gb": 10.0,
            "storage_total_gb": 64.0,
            "lte_rssi_dbm": -70.0,
            "camera_status": "OK",
            "clock_drift_ms": 5.0,
            "events_captured": 100,
            "events_uploaded": 95,
            "bandwidth_mbps": 2.5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, f"Missing node headers should return 422: {resp.status_code}"


@pytest.mark.asyncio
async def test_expired_jwt_rejected(db_session, test_client):
    token = create_access_token(
        data={"sub": str(uuid.uuid4()), "role": "BUYER", "email": "exp@test.com"},
        expires_delta=timedelta(hours=-1),
    )
    resp = await test_client.get(
        "/api/v1/nodes/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_jwt_returns_user(db_session, test_client):
    unique_email = f"me-test-{uuid.uuid4().hex[:8]}@test.com"
    reg = await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "securepass123",
            "full_name": "Me Tester",
            "organization": "TestOrg",
        },
    )
    assert reg.status_code == 201
    registered = reg.json()

    login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "securepass123"},
    )
    token = login.json()["access_token"]

    me_resp = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me = me_resp.json()
    assert me["id"] == registered["id"]
    assert me["email"] == unique_email
    assert me["full_name"] == "Me Tester"
    assert me["organization"] == "TestOrg"
    assert me["role"] == "ANNOTATOR"
    assert me["is_active"] is True
    assert "hashed_password" not in me
    assert "api_key_hash" not in me


@pytest.mark.asyncio
async def test_me_without_auth_returns_401(db_session, test_client):
    resp = await test_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_buyer_route_with_valid_api_key_200(db_session, test_client):
    unique_email = f"apikey-route-{uuid.uuid4().hex[:8]}@test.com"
    reg = await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email,
            "password": "securepass123",
            "full_name": "API Key Route Tester",
        },
    )
    assert reg.status_code == 201

    login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "securepass123"},
    )
    token = login.json()["access_token"]

    key_resp = await test_client.post(
        "/api/v1/auth/api-keys",
        json={"name": "buyer-key", "scopes": ["read"], "expires_in_days": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    raw_key = key_resp.json()["key"]

    resp = await test_client.get(
        "/api/v1/datasets/",
        headers={"X-API-Key": raw_key},
    )
    assert resp.status_code == 200, f"Valid API key should return 200: {resp.status_code} {resp.text}"


@pytest.mark.asyncio
async def test_buyer_route_with_invalid_api_key_401(db_session, test_client):
    resp = await test_client.get(
        "/api/v1/datasets/",
        headers={"X-API-Key": "invalid_key_12345"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_buyer_route_without_api_key_401(db_session, test_client):
    resp = await test_client.get("/api/v1/datasets/")
    assert resp.status_code == 401
