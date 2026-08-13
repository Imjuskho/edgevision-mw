from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.annotation import Annotation
from app.models.enums import AnnotationStatus


@pytest.fixture
def _patch_minio(monkeypatch):
    monkeypatch.setattr("app.core.minio_helper.put_object", AsyncMock(return_value=None))


def _create_token(user):
    from app.core.security import create_access_token

    return create_access_token(data={"sub": str(user.id), "role": user.role})


@pytest.mark.asyncio
async def test_live_review_queue_lists_pending_captures(
    _patch_minio, test_client, db_session,
):
    from tests.test_phase7 import _create_user, _make_png_buffer

    admin = await _create_user(db_session, role="QA")
    token = _create_token(admin)
    buf = _make_png_buffer(seed=99)
    ann_json = json.dumps([{"class_name": "car", "confidence": 0.9, "bbox": [10, 10, 50, 50]}])

    save = await test_client.post(
        "/api/v1/annotations/live",
        files={"file": ("frame.jpg", buf, "image/jpeg")},
        data={"annotations": ann_json, "source": "live_camera", "depth_available": "true"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert save.status_code == 201, save.text
    ann_id = save.json()["id"]

    resp = await test_client.get(
        "/api/v1/review/live/queue",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    ids = [item["annotation_id"] for item in data["items"]]
    assert ann_id in ids


@pytest.mark.asyncio
async def test_live_bulk_approve_certifies(_patch_minio, test_client, db_session):
    from tests.test_phase7 import _create_user, _make_png_buffer

    admin = await _create_user(db_session, role="QA")
    token = _create_token(admin)
    buf = _make_png_buffer(seed=100)
    ann_json = json.dumps([{"class_name": "person", "confidence": 0.8, "bbox": [5, 5, 30, 60]}])

    save = await test_client.post(
        "/api/v1/annotations/live",
        files={"file": ("frame.jpg", buf, "image/jpeg")},
        data={"annotations": ann_json, "source": "live_camera"},
        headers={"Authorization": f"Bearer {token}"},
    )
    ann_id = save.json()["id"]

    approve = await test_client.post(
        "/api/v1/review/live/approve",
        json={"annotation_ids": [ann_id]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert approve.status_code == 200
    assert approve.json()["approved_count"] == 1

    result = await db_session.execute(select(Annotation).where(Annotation.id == ann_id))
    record = result.scalar_one()
    assert record.status == AnnotationStatus.CERTIFIED
    assert record.is_certified is True


@pytest.mark.asyncio
async def test_live_bulk_reject(_patch_minio, test_client, db_session):
    from tests.test_phase7 import _create_user, _make_png_buffer

    admin = await _create_user(db_session, role="QA")
    token = _create_token(admin)
    buf = _make_png_buffer(seed=101)
    ann_json = json.dumps([{"class_name": "car", "confidence": 0.7, "bbox": [1, 1, 20, 20]}])

    save = await test_client.post(
        "/api/v1/annotations/live",
        files={"file": ("frame.jpg", buf, "image/jpeg")},
        data={"annotations": ann_json, "source": "live_camera"},
        headers={"Authorization": f"Bearer {token}"},
    )
    ann_id = save.json()["id"]

    reject = await test_client.post(
        "/api/v1/review/live/reject",
        json={"annotation_ids": [ann_id], "reason": "blur"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reject.status_code == 200
    assert reject.json()["rejected_count"] == 1

    result = await db_session.execute(select(Annotation).where(Annotation.id == ann_id))
    record = result.scalar_one()
    assert record.status == AnnotationStatus.REJECTED
