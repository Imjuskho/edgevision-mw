import pytest


@pytest.mark.asyncio
async def test_cors_headers_present(test_client):
    resp = await test_client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 200
    header_names = [k.lower() for k in resp.headers]
    assert "access-control-allow-origin" in header_names


@pytest.mark.asyncio
async def test_metrics_endpoint_no_auth_required(test_client):
    resp = await test_client.get("/metrics")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_endpoint_returns_version(test_client):
    resp = await test_client.get("/health")
    assert resp.status_code == 200
    assert "version" in resp.json()


@pytest.mark.asyncio
async def test_sql_injection_in_query_param(test_client, jwt_token_factory):
    token = jwt_token_factory(role="ADMIN")
    resp = await test_client.get(
        "/api/v1/nodes/",
        params={"district": "'; DROP TABLE nodes;--"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_xss_in_search_param(test_client, jwt_token_factory):
    token = jwt_token_factory(role="ADMIN")
    resp = await test_client.get(
        "/api/v1/datasets/",
        params={"search": "<script>alert(1)</script>"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
