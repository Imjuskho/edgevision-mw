"""Ensure uploads immediately create studio annotations and update sample_count."""

from __future__ import annotations

import io
import random
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.image import ImageRecord


def _make_png() -> io.BytesIO:
    img = Image.new(
        "RGB",
        (64, 64),
        color=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)),
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@pytest.mark.asyncio
async def test_upload_creates_annotation_and_updates_sample_count(db_session, test_client, jwt_token_factory):
    reg = await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"pipeline-{uuid.uuid4().hex[:8]}@test.com",
            "password": "securepass123",
            "full_name": "Pipeline Tester",
        },
    )
    assert reg.status_code == 201
    user_id = reg.json()["id"]
    token = jwt_token_factory(role="ANNOTATOR", user_id=user_id)
    headers = {"Authorization": f"Bearer {token}"}

    dataset_id = f"pipeline-ds-{uuid.uuid4().hex[:8]}"
    with patch("app.services.images.put_object", new=AsyncMock()):
        resp = await test_client.post(
            "/api/v1/upload/images",
            files={"files": ("frame.png", _make_png(), "image/png")},
            data={"dataset_id": dataset_id, "source": "file"},
            headers=headers,
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["uploaded"] >= 0

    ds = (await db_session.execute(select(Dataset).where(Dataset.dataset_id == dataset_id))).scalar_one()
    image_count = (
        await db_session.execute(select(func.count()).select_from(ImageRecord).where(ImageRecord.dataset_id == ds.id))
    ).scalar()
    ann_count = (await db_session.execute(select(func.count()).where(Annotation.dataset_id == ds.id))).scalar()

    assert image_count == 1
    assert ann_count == 1
    assert ds.sample_count == 1

    list_resp = await test_client.get(
        f"/api/v1/studio/datasets/{dataset_id}/images?page=1&page_size=10",
        headers=headers,
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert listed["total"] == 1
    assert len(listed["images"]) == 1
