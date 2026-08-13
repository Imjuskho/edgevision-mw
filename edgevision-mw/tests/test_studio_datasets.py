"""Tests for POST /studio/datasets create endpoint."""

from uuid import uuid4

import pytest

from app.core.security import create_access_token
from app.models.buyer import User
from app.models.dataset import Dataset


async def _create_user(db, role="OPERATOR"):
    user_id = uuid4()
    user = User(
        id=user_id,
        email=f"{user_id.hex[:8]}@test.com",
        hashed_password="fakehash",
        full_name="Create Test User",
        role=role,
        is_active=True,
        dpa_signed=True,
    )
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_create_dataset_minimal(test_client, db_session):
    user = await _create_user(db_session, role="OPERATOR")
    token = create_access_token({"sub": str(user.id), "role": user.role})

    resp = await test_client.post(
        "/api/v1/studio/datasets",
        json={"name": "Lilongwe Road Batch 4", "source_type": "studio"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Lilongwe Road Batch 4"
    assert data["status"] == "BUILDING"
    assert data["sample_count"] == 0
    assert data["dataset_id"] == "lilongwe-road-batch-4"
    assert data["source_type"] == "studio"


@pytest.mark.asyncio
async def test_create_dataset_with_custom_id(test_client, db_session):
    user = await _create_user(db_session, role="ADMIN")
    token = create_access_token({"sub": str(user.id), "role": user.role})
    custom_id = f"ds-{uuid4().hex[:8]}"

    resp = await test_client.post(
        "/api/v1/studio/datasets",
        json={
            "name": "Custom ID Dataset",
            "dataset_id": custom_id,
            "source_type": "photo",
            "description": "Field capture batch",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["dataset_id"] == custom_id
    assert data["source_type"] == "photo"
    assert data["description"] == "Field capture batch"


@pytest.mark.asyncio
async def test_create_dataset_conflict(test_client, db_session):
    user = await _create_user(db_session, role="OPERATOR")
    token = create_access_token({"sub": str(user.id), "role": user.role})

    ds = Dataset(
        id=uuid4(),
        dataset_id="existing-dataset",
        name="Existing",
        version="1.0",
        status="BUILDING",
        sample_count=0,
        classes={},
        annotations_per_image=0.0,
        image_width=0,
        image_height=0,
        geographic_coverage={"districts": []},
        demographic_report={"age_groups": {}},
        consent_coverage_pct=0.0,
        pii_scrub_verified=False,
        iaa_score=0.0,
        formats=[],
        price_usd=0,
        license_type="ANNUAL",
    )
    db_session.add(ds)
    await db_session.commit()

    resp = await test_client.post(
        "/api/v1/studio/datasets",
        json={"name": "Duplicate", "dataset_id": "existing-dataset"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_dataset_forbidden_for_annotator(test_client, db_session):
    user = await _create_user(db_session, role="ANNOTATOR")
    token = create_access_token({"sub": str(user.id), "role": user.role})

    resp = await test_client.post(
        "/api/v1/studio/datasets",
        json={"name": "Should Fail"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
