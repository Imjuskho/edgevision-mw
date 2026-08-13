from __future__ import annotations

import uuid

import pytest

from app.core.security import hash_api_key_bcrypt, verify_api_key_bcrypt


async def _register_admin(test_client, email: str | None = None) -> tuple[str, str]:
    """Register a real admin user and return (token, user_id)."""
    mail = email or f"key-admin-{uuid.uuid4().hex[:8]}@test.com"
    resp = await test_client.post(
        "/api/v1/auth/register",
        json={"email": mail, "password": "securepass123", "full_name": "Key Admin"},
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["id"]
    login = await test_client.post(
        "/api/v1/auth/login",
        json={"email": mail, "password": "securepass123"},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"], user_id


@pytest.mark.asyncio
async def test_create_api_key_returns_plaintext_once(db_session, test_client):
    """POST /auth/api-keys returns plaintext key only on creation."""
    token, _ = await _register_admin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/auth/api-keys",
        json={"name": "Test Key", "scopes": ["read"]},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "key" in data
    assert data["key"].startswith("ak_")
    assert "." in data["key"]
    assert data["key_id"] == data["key"].split(".")[0]

    key_id = data["key_id"]

    list_resp = await test_client.get("/api/v1/auth/api-keys", headers=headers)
    assert list_resp.status_code == 200
    keys = list_resp.json()
    matched = [k for k in keys if k["key_id"] == key_id]
    assert len(matched) == 1
    assert matched[0]["key"] == "****(redacted)"
    assert matched[0]["key_id"] == key_id


@pytest.mark.asyncio
async def test_verify_api_key_bcrypt():
    """Verify bcrypt hash/verify round-trip works."""
    from app.core.security import generate_api_key_pair

    _key_id, _secret, plaintext = generate_api_key_pair()
    hashed = hash_api_key_bcrypt(plaintext)
    assert verify_api_key_bcrypt(plaintext, hashed)
    assert not verify_api_key_bcrypt("wrong_key", hashed)


@pytest.mark.asyncio
async def test_api_key_service_verify(db_session, test_client):
    """Verify API key authentication via service layer."""
    from uuid import UUID

    from app.auth.service import create_api_key, verify_api_key

    token, user_id = await _register_admin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    user_resp = await test_client.get("/api/v1/auth/me", headers=headers)
    assert user_resp.status_code == 200
    assert user_resp.json()["id"] == user_id

    plaintext, api_key = await create_api_key(
        db_session, UUID(user_id), {"name": "Service Test Key", "scopes": ["read"]}
    )
    assert plaintext.startswith("ak_")
    assert api_key.key_id == plaintext.split(".")[0]

    user = await verify_api_key(db_session, plaintext)
    assert user is not None
    assert str(user.id) == str(user_id)

    bad_user = await verify_api_key(db_session, "ak_fake.secret")
    assert bad_user is None

    wrong_key = plaintext[::-1]
    bad_user2 = await verify_api_key(db_session, wrong_key)
    assert bad_user2 is None


@pytest.mark.asyncio
async def test_delete_api_key(db_session, test_client):
    """DELETE /auth/api-keys/{key_id} invalidates the key."""

    from app.auth.service import verify_api_key

    token, _user_id = await _register_admin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await test_client.post(
        "/api/v1/auth/api-keys",
        json={"name": "Delete Key", "scopes": ["read"]},
        headers=headers,
    )
    assert create_resp.status_code == 201
    key_id = create_resp.json()["key_id"]
    plaintext = create_resp.json()["key"]

    del_resp = await test_client.delete(
        f"/api/v1/auth/api-keys/{key_id}",
        headers=headers,
    )
    assert del_resp.status_code == 204

    user = await verify_api_key(db_session, plaintext)
    assert user is None


@pytest.mark.asyncio
async def test_list_api_keys_no_secret_leak(db_session, test_client):
    """GET /auth/api-keys does not leak secret keys."""
    token, _ = await _register_admin(test_client)
    headers = {"Authorization": f"Bearer {token}"}

    await test_client.post(
        "/api/v1/auth/api-keys",
        json={"name": "List Test Key 1", "scopes": ["read"]},
        headers=headers,
    )
    await test_client.post(
        "/api/v1/auth/api-keys",
        json={"name": "List Test Key 2", "scopes": ["write"]},
        headers=headers,
    )

    list_resp = await test_client.get("/api/v1/auth/api-keys", headers=headers)
    assert list_resp.status_code == 200
    keys = list_resp.json()
    assert len(keys) >= 2
    for k in keys:
        assert k["key"] == "****(redacted)"
        assert "last_used_at" in k
