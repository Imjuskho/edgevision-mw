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


@pytest.mark.asyncio
async def test_save_live_annotation(_patch_minio, test_client, db_session):
    from tests.test_phase7 import _create_user, _make_png_buffer

    admin = await _create_user(db_session, role="ADMIN")
    token = _create_token(admin)

    buf = _make_png_buffer(seed=42)
    ann_json = json.dumps([
        {"class_name": "car", "confidence": 0.95, "bbox": [100, 50, 200, 150]},
        {"class_name": "person", "confidence": 0.87, "bbox": [300, 100, 80, 180]},
    ])

    resp = await test_client.post(
        "/api/v1/annotations/live",
        files={"file": ("frame.jpg", buf, "image/jpeg")},
        data={
            "annotations": ann_json,
            "source": "live_camera",
            "confidence_threshold": "0.35",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201, f"Body: {resp.text}"
    data = resp.json()
    assert data["annotations_count"] == 2
    assert data["source"] == "live_camera"
    assert data["width"] > 0
    assert data["height"] > 0

    result = await db_session.execute(
        select(Annotation).where(Annotation.id == data["id"])
    )
    record = result.scalar_one_or_none()
    assert record is not None
    assert record.status == AnnotationStatus.PENDING
    assert len(record.detected_objects.get("objects", record.detected_objects)) == 2


@pytest.mark.asyncio
async def test_save_live_annotation_with_orientation(_patch_minio, test_client, db_session):
    from tests.test_phase7 import _create_user, _make_png_buffer

    admin = await _create_user(db_session, role="ADMIN")
    token = _create_token(admin)

    buf = _make_png_buffer(seed=44)
    ann_json = json.dumps([
        {"class_name": "car", "confidence": 0.95, "bbox": [100, 50, 200, 150]},
    ])

    resp = await test_client.post(
        "/api/v1/annotations/live",
        files={"file": ("frame.jpg", buf, "image/jpeg")},
        data={
            "annotations": ann_json,
            "source": "live_camera",
            "orientation": "mirrored",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["orientation"] == "mirrored"


@pytest.mark.asyncio
async def test_save_live_annotation_with_mask_rle(_patch_minio, test_client, db_session, monkeypatch):
    from tests.test_phase7 import _create_user, _make_png_buffer

    admin = await _create_user(db_session, role="ADMIN")
    token = _create_token(admin)

    buf = _make_png_buffer(seed=45)
    mask_polygon = [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]]
    ann_json = json.dumps([
        {"class_name": "car", "confidence": 0.95, "bbox": [10, 10, 50, 50]},
    ])
    masks_json = json.dumps([mask_polygon])

    monkeypatch.setattr("app.ai.mask_utils.pycocotools_available", lambda: True)
    monkeypatch.setattr(
        "app.api.annotations_live.mask_to_rle",
        lambda mask: "mock_rle" if mask.any() else (_ for _ in ()).throw(ValueError("empty")),
    )

    resp = await test_client.post(
        "/api/v1/annotations/live",
        files={"file": ("frame.jpg", buf, "image/jpeg")},
        data={
            "annotations": ann_json,
            "masks": masks_json,
            "source": "live_camera",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()

    result = await db_session.execute(
        select(Annotation).where(Annotation.id == data["id"])
    )
    record = result.scalar_one()
    objects = record.detected_objects.get("objects", [])
    assert len(objects) == 1
    assert objects[0].get("mask_format") == "rle"
    assert objects[0].get("mask_rle") == "mock_rle"
    assert isinstance(objects[0].get("mask"), list)


@pytest.mark.asyncio
async def test_save_live_annotation_invalid_json(_patch_minio, test_client, db_session):
    from tests.test_phase7 import _create_user, _make_png_buffer

    admin = await _create_user(db_session, role="ADMIN")
    token = _create_token(admin)

    buf = _make_png_buffer(seed=43)
    resp = await test_client.post(
        "/api/v1/annotations/live",
        files={"file": ("frame.jpg", buf, "image/jpeg")},
        data={"annotations": "not-valid-json", "source": "live_camera"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_save_live_annotation_requires_auth(test_client):
    resp = await test_client.post(
        "/api/v1/annotations/live",
        files={"file": ("frame.jpg", b"fake-data", "image/jpeg")},
        data={"annotations": "[]", "source": "live_camera"},
    )
    assert resp.status_code == 401


def _create_token(user):
    from app.core.security import create_access_token

    return create_access_token(data={"sub": str(user.id), "role": user.role})
