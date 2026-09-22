from __future__ import annotations

import json
from datetime import UTC
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select


@pytest.fixture
def _patch_minio(monkeypatch):
    monkeypatch.setattr("app.core.minio_helper.put_object", AsyncMock(return_value=None))


class TestLiveLabelBridge:
    def test_pixel_bbox_to_normalized(self):
        from app.services.live_label_bridge import live_detections_to_studio_boxes

        objects = [
            {
                "class_name": "person",
                "taxonomy_label": "pedestrian_roadside",
                "confidence": 0.91,
                "bbox": [64.0, 48.0, 128.0, 192.0],
            }
        ]
        boxes = live_detections_to_studio_boxes(objects, 512, 384)
        assert len(boxes) == 1
        assert boxes[0]["label"] == "pedestrian_roadside"
        assert boxes[0]["x"] == pytest.approx(0.125, abs=1e-3)
        assert boxes[0]["y"] == pytest.approx(0.125, abs=1e-3)
        assert boxes[0]["width"] == pytest.approx(0.125, abs=1e-3)
        assert boxes[0]["height"] == pytest.approx(0.375, abs=1e-3)

    def test_mask_polygon_bbox(self):
        from app.services.live_label_bridge import live_detections_to_studio_boxes

        objects = [
            {
                "class_name": "car",
                "confidence": 0.88,
                "mask": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]],
            }
        ]
        boxes = live_detections_to_studio_boxes(objects, 640, 480)
        assert boxes[0]["polygon"] is not None
        assert len(boxes[0]["polygon"]) == 4
        assert boxes[0]["width"] == pytest.approx(0.4, abs=1e-3)


@pytest.mark.asyncio
async def test_live_save_with_dataset_seeds_human_labels(
    _patch_minio,
    test_client,
    db_session,
):
    from app.models.annotation import Annotation
    from tests.test_phase7 import _create_dataset, _create_user, _make_png_buffer

    admin = await _create_user(db_session, role="ADMIN")
    ds = await _create_dataset(db_session)

    from app.core.security import create_access_token

    token = create_access_token(data={"sub": str(admin.id), "role": admin.role})
    buf = _make_png_buffer(seed=99)
    ann_json = json.dumps(
        [
            {
                "class_name": "car",
                "taxonomy_label": "car_private",
                "confidence": 0.9,
                "bbox": [50, 40, 150, 120],
                "mask": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4]],
            }
        ]
    )

    resp = await test_client.post(
        "/api/v1/annotations/live",
        files={"file": ("frame.jpg", buf, "image/jpeg")},
        data={"annotations": ann_json, "dataset_id": ds.dataset_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data.get("ai_draft") is True
    assert data.get("image_index") is not None

    result = await db_session.execute(select(Annotation).where(Annotation.id == data["id"]))
    record = result.scalar_one()
    assert record.human_labels is not None
    assert record.human_labels.get("source") == "live_ai_assisted"
    boxes = record.human_labels["boxes"]
    assert len(boxes) == 1
    assert boxes[0]["label"] == "car_private"
    assert boxes[0]["polygon"] is not None


@pytest.mark.asyncio
async def test_studio_save_clears_ai_draft(
    _patch_minio,
    test_client,
    db_session,
):
    from datetime import datetime

    from app.models.annotation import Annotation
    from app.models.studio import AnnotationSession
    from tests.test_phase7 import _create_dataset, _create_user, _make_png_buffer

    user = await _create_user(db_session, role="ANNOTATOR")
    ds = await _create_dataset(db_session)

    from app.core.security import create_access_token

    token = create_access_token(data={"sub": str(user.id), "role": user.role})
    buf = _make_png_buffer(seed=7)

    resp = await test_client.post(
        "/api/v1/annotations/live",
        files={"file": ("frame.jpg", buf, "image/jpeg")},
        data={
            "annotations": '[{"class_name":"car","bbox":[10,10,100,80]}]',
            "dataset_id": ds.dataset_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    payload = resp.json()
    ann_id = payload["id"]
    image_index = payload["image_index"]

    sess = AnnotationSession(
        user_id=user.id,
        dataset_id=ds.id,
        started_at=datetime.now(UTC),
        is_active=True,
        image_count=1,
        annotations_created=0,
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)

    save_resp = await test_client.post(
        "/api/v1/studio/annotations/save",
        json={
            "session_id": str(sess.id),
            "image_index": image_index,
            "annotations": [
                {
                    "x": 0.1,
                    "y": 0.1,
                    "width": 0.2,
                    "height": 0.2,
                    "label": "car_private",
                    "confidence": 1.0,
                }
            ],
            "tool_used": "bbox",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert save_resp.status_code == 201, save_resp.text

    result = await db_session.execute(select(Annotation).where(Annotation.id == ann_id))
    record = result.scalar_one()
    assert record.human_labels.get("ai_draft") is False
    assert record.human_labels.get("source") == "human_corrected"
