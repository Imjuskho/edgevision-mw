import pytest


@pytest.mark.asyncio
async def test_openapi_schema_returns(test_client):
    resp = await test_client.get("/openapi.json")
    assert resp.status_code == 200
    assert "openapi" in resp.json()


@pytest.mark.asyncio
async def test_openapi_tags_present(test_client):
    resp = await test_client.get("/openapi.json")
    assert resp.status_code == 200
    tags = [t["name"] for t in resp.json().get("tags", [])]
    for tag in ["Fleet", "Ingestion", "Annotation", "Catalog", "Compliance", "Billing"]:
        assert tag in tags, f"Tag '{tag}' missing from OpenAPI tags"


@pytest.mark.asyncio
async def test_docs_endpoint(test_client):
    resp = await test_client.get("/docs")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_redoc_endpoint(test_client):
    resp = await test_client.get("/redoc")
    assert resp.status_code == 200
