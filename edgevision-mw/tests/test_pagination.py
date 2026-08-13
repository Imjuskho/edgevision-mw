import pytest


@pytest.mark.asyncio
async def test_fleet_list_nodes_accepts_limit_and_offset(test_client, jwt_token_factory):
    token = jwt_token_factory(role="ADMIN")
    resp = await test_client.get(
        "/api/v1/nodes/",
        params={"limit": 5, "offset": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_fleet_list_nodes_default_pagination(test_client, jwt_token_factory):
    token = jwt_token_factory(role="ADMIN")
    resp = await test_client.get(
        "/api/v1/nodes/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ingestion_list_batches_accepts_limit_and_offset(test_client, jwt_token_factory):
    token = jwt_token_factory(role="ADMIN")
    resp = await test_client.get(
        "/api/v1/ingest/batches",
        params={"limit": 5, "offset": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_billing_list_exports_accepts_limit_and_offset(test_client, jwt_token_factory):
    token = jwt_token_factory(role="ADMIN")
    resp = await test_client.get(
        "/api/v1/exports",
        params={"limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
