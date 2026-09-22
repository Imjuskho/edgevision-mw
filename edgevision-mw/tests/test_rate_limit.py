"""Tests for rate limiting (F7)."""

import uuid

import pytest


@pytest.mark.asyncio
async def test_login_rate_limit_429(rate_limit_client):
    """POST /auth/login should return 429 after 5 requests in 60s."""
    for i in range(6):
        resp = await rate_limit_client.post(
            "/api/v1/auth/login",
            json={"email": f"ratelimit-{i}@test.com", "password": "wrongpass"},
        )
        if i < 5:
            assert resp.status_code != 429, f"Request {i + 1} should not be rate limited"
        else:
            assert resp.status_code == 429, f"Request {i + 1} should be rate limited, got {resp.status_code}"
            assert "Retry-After" in resp.headers


@pytest.mark.asyncio
async def test_register_rate_limit_429(rate_limit_client):
    """POST /auth/register should return 429 after 3 requests in 60s."""
    for i in range(4):
        resp = await rate_limit_client.post(
            "/api/v1/auth/register",
            json={
                "email": f"rl-register-{uuid.uuid4().hex[:8]}@test.com",
                "password": "securepass123",
                "full_name": f"RL User {i}",
            },
        )
        if i < 3:
            assert resp.status_code != 429, f"Request {i + 1} should not be rate limited"
        else:
            assert resp.status_code == 429, f"Request {i + 1} should be rate limited, got {resp.status_code}"


@pytest.mark.asyncio
async def test_health_not_rate_limited(rate_limit_client):
    """GET /health should never be rate limited."""
    for _ in range(20):
        resp = await rate_limit_client.get("/health")
        assert resp.status_code == 200
