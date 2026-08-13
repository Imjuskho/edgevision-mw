from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.buyer import User


async def _create_user(db, role="ANNOTATOR"):
    user_id = uuid4()
    user = User(
        id=user_id,
        email=f"an-{user_id.hex[:8]}@test.com",
        hashed_password="fakehash",
        full_name="Analytics Test User",
        role=role,
        is_active=True,
        dpa_signed=True,
    )
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_ingest_experiment_events(db_session, test_client, jwt_token_factory):
    user = await _create_user(db_session)
    token = jwt_token_factory(role="ANNOTATOR", user_id=str(user.id))
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/analytics/experiments",
        headers=headers,
        json={
            "events": [
                {
                    "experiment_id": "ai_assist_mode",
                    "variant_id": "full_image",
                    "event_type": "exposed",
                    "metadata": {"mode": "full_image"},
                },
                {
                    "experiment_id": "ai_assist_mode",
                    "variant_id": "full_image",
                    "event_type": "converted",
                },
            ]
        },
    )
    assert resp.status_code == 201
    assert resp.json()["received"] == 2


@pytest.mark.asyncio
async def test_ingest_requires_auth(test_client):
    resp = await test_client.post(
        "/api/v1/analytics/experiments",
        json={"events": [{"experiment_id": "x", "variant_id": "y", "event_type": "exposed"}]},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_ingest_rejects_unknown_event_type(db_session, test_client, jwt_token_factory):
    user = await _create_user(db_session)
    token = jwt_token_factory(user_id=str(user.id))
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/analytics/experiments",
        headers=headers,
        json={"events": [{"experiment_id": "x", "variant_id": "y", "event_type": "bogus"}]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_experiment_summary(db_session, test_client, jwt_token_factory):
    user = await _create_user(db_session, role="ADMIN")
    token = jwt_token_factory(role="ADMIN", user_id=str(user.id))
    headers = {"Authorization": f"Bearer {token}"}

    experiment_id = f"ai_assist_mode_{uuid4().hex[:8]}"
    for event_type in ("exposed", "converted", "exposed"):
        await test_client.post(
            "/api/v1/analytics/experiments",
            headers=headers,
            json={
                "events": [
                    {
                        "experiment_id": experiment_id,
                        "variant_id": "full_image",
                        "event_type": event_type,
                    }
                ]
            },
        )

    resp = await test_client.get(
        "/api/v1/analytics/experiments/summary",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    variants = data["experiments"][experiment_id]["variants"]
    assert variants["full_image"]["exposed"] == 2
    assert variants["full_image"]["converted"] == 1


@pytest.mark.asyncio
async def test_list_requires_admin_or_operator(db_session, test_client, jwt_token_factory):
    user = await _create_user(db_session, role="BUYER")
    token = jwt_token_factory(role="BUYER", user_id=str(user.id))
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.get("/api/v1/analytics/experiments", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_returns_events(db_session, test_client, jwt_token_factory):
    user = await _create_user(db_session, role="ADMIN")
    token = jwt_token_factory(role="ADMIN", user_id=str(user.id))
    headers = {"Authorization": f"Bearer {token}"}

    experiment_id = f"turbo_review_layout_{uuid4().hex[:8]}"
    await test_client.post(
        "/api/v1/analytics/experiments",
        headers=headers,
        json={
            "events": [
                {
                    "experiment_id": experiment_id,
                    "variant_id": "grid",
                    "event_type": "exposed",
                }
            ]
        },
    )

    resp = await test_client.get(
        "/api/v1/analytics/experiments",
        params={"experiment_id": experiment_id},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["experiment_id"] == experiment_id
    assert data[0]["event_type"] == "exposed"
