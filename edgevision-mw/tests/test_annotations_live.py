from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.annotation import Annotation


@pytest.fixture
def _patch_minio(monkeypatch):
    monkeypatch.setattr("app.core.minio_helper.put_object", AsyncMock(return_value=None))


def _create_token(user):
    from app.core.security import create_access_token

    return create_access_token(data={"sub": str(user.id), "role": user.role})


@pytest.mark.asyncio
async def test_attach_mask_rle_sets_format_and_metadata(
    _patch_minio, test_client, db_session, monkeypatch,
):
    pytest.importorskip("pycocotools")
    from tests.test_phase7 import _create_user, _make_png_buffer

    admin = await _create_user(db_session, role="ADMIN")
    token = _create_token(admin)

    buf = _make_png_buffer(seed=55)
    mask_polygon = [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]]
    ann_json = json.dumps([
        {"class_name": "car", "confidence": 0.95, "bbox": [10, 10, 50, 50]},
    ])
    masks_json = json.dumps([mask_polygon])

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
    assert data.get("has_mask_rle") is True

    result = await db_session.execute(
        select(Annotation).where(Annotation.id == data["id"])
    )
    record = result.scalar_one()
    objects = record.detected_objects.get("objects", [])
    assert objects[0].get("mask_rle")
    assert objects[0].get("mask_format") == "rle"
    assert isinstance(objects[0].get("mask"), list)


@pytest.mark.asyncio
async def test_save_live_annotation_with_bbox_3d(_patch_minio, test_client, db_session):
    from tests.test_phase7 import _create_user, _make_png_buffer

    admin = await _create_user(db_session, role="ADMIN")
    token = _create_token(admin)

    buf = _make_png_buffer(seed=56)
    box3d = {
        "corners": [[0.1, 0.2, 0.5], [0.3, 0.2, 0.5]],
        "yaw": 0.0,
        "limitation": "heuristic_prior_yaw0",
    }
    ann_json = json.dumps([
        {"class_name": "car", "confidence": 0.9, "bbox": [10, 10, 50, 50]},
    ])
    bbox_3d_json = json.dumps([box3d])

    resp = await test_client.post(
        "/api/v1/annotations/live",
        files={"file": ("frame.jpg", buf, "image/jpeg")},
        data={
            "annotations": ann_json,
            "bbox_3d": bbox_3d_json,
            "source": "live_camera",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201
    data = resp.json()

    result = await db_session.execute(
        select(Annotation).where(Annotation.id == data["id"])
    )
    record = result.scalar_one()
    objects = record.detected_objects.get("objects", [])
    assert objects[0].get("bbox_3d") == box3d
