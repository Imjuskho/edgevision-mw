"""API tests for the semantic road-scene endpoint (/road/scene)."""

from __future__ import annotations

import io
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from PIL import Image

from app.ai.road_segmenter import InstanceMaskResult
from app.core.security import create_access_token
from app.models.annotation import Annotation
from app.models.enums import AnnotationStatus, BatchStatus, NodeCategory, NodeStatus, PIIMode
from app.models.ingestion import IngestionBatch
from app.models.node import Node

_ROAD_PATH = "app.api.road"


def _make_png_bytes() -> bytes:
    img = Image.new("RGB", (160, 120), color=(90, 90, 90))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _seed_annotation(db):
    node = Node(
        node_id=f"node-{uuid4().hex[:8]}",
        district="Lilongwe",
        latitude=-13.9626,
        longitude=33.7741,
        category=NodeCategory.ROAD,
        hardware_profile={"soc": "rpi4"},
        network_config={"lte": "enabled"},
        capture_schedule="07:00-18:00",
        interest_classes=["road"],
        pii_mode=PIIMode.NONE,
        firmware_version="1.0.0",
        public_key=b"\x01" * 32,
        status=NodeStatus.ONLINE,
        is_enabled=True,
    )
    db.add(node)
    await db.flush()
    batch = IngestionBatch(
        batch_id=f"batch-{uuid4().hex[:8]}",
        node_id=node.id,
        hub_id="hub-1",
        event_count=1,
        file_size_bytes=1024,
        checksum_sha256="abc",
        node_signature=b"\x02" * 64,
        compression_codec="h265",
        status=BatchStatus.INGESTED,
        quality_scores={"brightness": 0.8},
    )
    db.add(batch)
    await db.flush()
    ann = Annotation(
        batch_id=batch.id,
        image_index=0,
        image_path="images/scene.jpg",
        thumbnail_path="thumbs/scene.jpg",
        detected_objects={"objects": []},
        auto_labels={"labels": []},
        status=AnnotationStatus.PENDING,
        quality_score=0.0,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return ann


def _fake_segmenter(instances):
    class _Fake:
        def __init__(self, instances):
            self._instances = instances

        def is_loaded(self):
            return True

        def segment(self, image, conf_threshold, iou_threshold):
            return list(self._instances)

    return _Fake(instances)


def _road_instance(cid, cname, bbox, confidence=0.9):
    return InstanceMaskResult(
        class_id=cid,
        class_name=cname,
        confidence=confidence,
        bbox=bbox,
        mask_rle="",
        polygon=None,
    )


@pytest.mark.asyncio
async def test_scene_requires_auth(db_session, test_client):
    resp = await test_client.post(
        "/api/v1/road/scene",
        json={"image_id": str(uuid4())},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_scene_returns_semantic_analysis(db_session, test_client, monkeypatch):
    ann = await _seed_annotation(db_session)

    user_id = uuid4()
    token = create_access_token(data={"sub": str(user_id), "role": "ADMIN", "email": "admin@scene.test"})

    mock_mc = MagicMock()
    mock_mc.get_object.return_value.read.return_value = _make_png_bytes()
    async def _get_mc():
        return mock_mc
    monkeypatch.setattr(f"{_ROAD_PATH}.get_minio_client", _get_mc)

    road_inst = _road_instance(0, "good_road", [0.25, 0.625, 0.5, 0.354])
    fake = _fake_segmenter([road_inst])
    async def _fake_rs(*a, **k):
        return fake
    monkeypatch.setattr("app.ai.road_segmenter.get_road_segmenter", _fake_rs)

    resp = await test_client.post(
        "/api/v1/road/scene",
        json={"image_id": str(ann.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["scene"]["has_road"] is True
    assert data["scene"]["drivable_class_ids"] == [0]
    assert data["scene"]["road_edge_distance_m"] is not None
    assert data["scene"]["road_edge_quality"] == "metric_ground_plane"
    assert data["depth_quality"] == "metric_ground_plane"
    assert data["surface_type"] in ("paved", "unpaved", "mixed")


@pytest.mark.asyncio
async def test_scene_isolates_hazards(db_session, test_client, monkeypatch):
    ann = await _seed_annotation(db_session)
    user_id = uuid4()
    token = create_access_token(data={"sub": str(user_id), "role": "ADMIN", "email": "admin2@scene.test"})

    mock_mc = MagicMock()
    mock_mc.get_object.return_value.read.return_value = _make_png_bytes()
    async def _get_mc():
        return mock_mc
    monkeypatch.setattr(f"{_ROAD_PATH}.get_minio_client", _get_mc)

    instances = [
        _road_instance(0, "good_road", [0.25, 0.625, 0.5, 0.354]),
        _road_instance(1, "pothole", [0.45, 0.8, 0.1, 0.08]),
    ]
    async def _fake_rs(*a, **k):
        return _fake_segmenter(instances)
    monkeypatch.setattr("app.ai.road_segmenter.get_road_segmenter", _fake_rs)

    resp = await test_client.post(
        "/api/v1/road/scene",
        json={"image_id": str(ann.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["scene"]["hazards"]) == 1
    assert data["scene"]["hazards"][0]["class_name"] == "pothole"


@pytest.mark.asyncio
async def test_scene_unknown_image_404(db_session, test_client):
    user_id = uuid4()
    token = create_access_token(data={"sub": str(user_id), "role": "ADMIN", "email": "admin3@scene.test"})
    resp = await test_client.post(
        "/api/v1/road/scene",
        json={"image_id": str(uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
