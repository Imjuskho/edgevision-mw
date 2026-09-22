from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.core.dependencies import get_redis
from app.main import app


def _override_redis(mock_redis: AsyncMock):
    app.dependency_overrides[get_redis] = lambda: mock_redis


@pytest.mark.asyncio
async def test_health_celery_endpoint_ok(
    db_session,
    test_client: AsyncClient,
):
    """GET /health/celery returns ok when Redis heartbeats are fresh."""

    mock_redis = AsyncMock()
    mock_redis.get.return_value = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
    mock_redis.keys.return_value = [
        "heartbeat:worker:worker1@host",
        "heartbeat:task:workers.check_heartbeat_timeouts",
    ]

    _override_redis(mock_redis)
    resp = await test_client.get("/health/celery")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "beat" in data
    assert "workers" in data
    assert "tasks" in data


@pytest.mark.asyncio
async def test_health_celery_endpoint_stale(
    db_session,
    test_client: AsyncClient,
):
    """GET /health/celery reports stale when heartbeats are old."""

    mock_redis = AsyncMock()
    mock_redis.get.return_value = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    mock_redis.keys.return_value = ["heartbeat:worker:worker1@host"]

    _override_redis(mock_redis)
    resp = await test_client.get("/health/celery")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unhealthy" or data["workers"]["worker1@host"] == "stale"


@pytest.mark.asyncio
async def test_health_celery_endpoint_no_heartbeats(
    db_session,
    test_client: AsyncClient,
):
    """GET /health/celery returns unhealthy when no heartbeats exist."""

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.keys.return_value = []

    _override_redis(mock_redis)
    resp = await test_client.get("/health/celery")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_health_base_endpoint(db_session, test_client: AsyncClient):
    """GET /health returns base health check."""
    resp = await test_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "version" in data
    assert "checks" in data
    assert "postgres" in data["checks"]
