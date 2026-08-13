from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.security import create_access_token
from app.models.annotation import Annotation
from app.models.buyer import User
from app.models.dataset import Dataset
from app.models.enums import (
    AnnotationStatus,
    BatchStatus,
    DatasetStatus,
    LicenseType,
    NodeCategory,
    NodeStatus,
    PIIMode,
)
from app.models.image import ImageRecord
from app.models.ingestion import IngestionBatch
from app.models.node import Node


async def _create_user(db, role="ANNOTATOR"):
    user_id = uuid4()
    user = User(
        id=user_id,
        email=f"{user_id.hex[:8]}@test.com",
        hashed_password="fakehash",
        full_name="Test User",
        role=role,
        is_active=True,
        dpa_signed=True,
    )
    db.add(user)
    await db.commit()
    return user


async def _create_node(db):
    node = Node(
        id=uuid4(), node_id=f"STU-{uuid4().hex[:8]}",
        district="Blantyre", latitude=-15.7861, longitude=35.0058,
        category=NodeCategory.ROAD, hardware_profile={"gpu": "jetson"},
        network_config={"apn": "airtel"}, capture_schedule="*/10 * * * *",
        interest_classes=["vehicle"], pii_mode=PIIMode.STRICT,
        firmware_version="1.0.0", public_key=b"\x01" * 32,
        status=NodeStatus.ONLINE, is_enabled=True,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


async def _create_batch(db, node):
    batch = IngestionBatch(
        batch_id=f"SBATCH-{uuid4().hex[:8]}",
        node_id=node.id,
        hub_id="hub-1",
        event_count=5,
        file_size_bytes=1024,
        checksum_sha256="abc123",
        node_signature=b"\x02" * 64,
        compression_codec="h265",
        status=BatchStatus.INGESTED,
        quality_scores={"brightness": 0.8},
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return batch


async def _create_dataset(db):
    ds = Dataset(
        id=uuid4(), dataset_id=f"DS-STUDIO-{uuid4().hex[:6]}",
        name="Studio Test Dataset", version="1.0",
        status=DatasetStatus.FOR_SALE, sample_count=10,
        classes={"vehicle": 1, "pedestrian": 2},
        annotations_per_image=2.0, image_width=1920, image_height=1080,
        geographic_coverage={"districts": ["Lilongwe"]},
        demographic_report={"age_groups": {}},
        consent_coverage_pct=1.0, pii_scrub_verified=True,
        iaa_score=0.90, formats=["COCO"],
        price_usd=Decimal("100.00"), license_type=LicenseType.ANNUAL,
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


async def _create_annotation(db, dataset_id, batch_id, index=0):
    ann = Annotation(
        batch_id=batch_id,
        image_index=index,
        image_path=f"images/batch/{index:04d}.jpg",
        thumbnail_path=f"thumbs/batch/{index:04d}.jpg",
        detected_objects={"objects": []},
        auto_labels={"labels": []},
        status=AnnotationStatus.PENDING,
        quality_score=0.0,
        dataset_id=dataset_id,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return ann


async def _create_image_record(db, dataset_id, uploaded_by=None):
    record = ImageRecord(
        id=uuid4(),
        storage_key=f"tenants/anonymous/datasets/{dataset_id}/images/{uuid4().hex}.jpg",
        thumbnail_key=f"tenants/anonymous/datasets/{dataset_id}/thumbnails/{uuid4().hex}.jpg",
        filename="image.jpg",
        content_type="image/jpeg",
        size_bytes=1234,
        width=1024,
        height=768,
        source="file",
        metadata_={"uploaded_from": "test"},
        exif=None,
        dataset_id=dataset_id,
        uploaded_by=uploaded_by,
        checksum_sha256="deadbeef",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


def _make_token(user):
    return create_access_token(data={"sub": str(user.id), "role": user.role, "email": user.email})


@pytest.mark.asyncio
async def test_create_session(db_session, test_client):
    user = await _create_user(db_session)
    ds = await _create_dataset(db_session)
    token = _make_token(user)
    resp = await test_client.post(
        "/api/v1/studio/sessions",
        json={"dataset_id": str(ds.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["dataset_id"] == str(ds.id)
    assert body["is_active"] is True
    assert body["image_count"] == 0
    assert body["annotations_created"] == 0


@pytest.mark.asyncio
async def test_create_session_dataset_not_found(db_session, test_client):
    user = await _create_user(db_session)
    token = _make_token(user)
    resp = await test_client.post(
        "/api/v1/studio/sessions",
        json={"dataset_id": str(uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session(db_session, test_client):
    user = await _create_user(db_session)
    ds = await _create_dataset(db_session)
    token = _make_token(user)

    create_resp = await test_client.post(
        "/api/v1/studio/sessions",
        json={"dataset_id": str(ds.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create_resp.json()["id"]

    resp = await test_client.get(
        f"/api/v1/studio/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == session_id


@pytest.mark.asyncio
async def test_get_session_wrong_user(db_session, test_client):
    user1 = await _create_user(db_session)
    user2 = await _create_user(db_session)
    ds = await _create_dataset(db_session)
    token1 = _make_token(user1)
    token2 = _make_token(user2)

    create_resp = await test_client.post(
        "/api/v1/studio/sessions",
        json={"dataset_id": str(ds.id)},
        headers={"Authorization": f"Bearer {token1}"},
    )
    session_id = create_resp.json()["id"]

    resp = await test_client.get(
        f"/api/v1/studio/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_images(db_session, test_client):
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    for i in range(3):
        await _create_annotation(db_session, ds.id, batch.id, index=i)

    token = _make_token(user)
    resp = await test_client.get(
        f"/api/v1/studio/datasets/{ds.id}/images",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["images"]) == 3
    assert body["images"][0]["index"] == 0
    assert body["images"][0]["has_human_labels"] is False


@pytest.mark.asyncio
async def test_create_session_populates_annotations_from_image_records(db_session, test_client):
    user = await _create_user(db_session)
    ds = await _create_dataset(db_session)
    await _create_image_record(db_session, ds.id)
    await _create_image_record(db_session, ds.id)
    token = _make_token(user)

    session_resp = await test_client.post(
        "/api/v1/studio/sessions",
        json={"dataset_id": str(ds.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert session_resp.status_code == 201

    list_resp = await test_client.get(
        f"/api/v1/studio/datasets/{ds.id}/images",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] == 2
    assert len(body["images"]) == 2
    assert body["images"][0]["index"] == 0
    assert body["images"][1]["index"] == 1


@pytest.mark.asyncio
async def test_list_images_dataset_not_found(db_session, test_client):
    user = await _create_user(db_session)
    token = _make_token(user)
    resp = await test_client.get(
        f"/api/v1/studio/datasets/{uuid4()}/images",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_save_annotation(db_session, test_client):
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    await _create_annotation(db_session, ds.id, batch.id, index=0)
    token = _make_token(user)

    sess_resp = await test_client.post(
        "/api/v1/studio/sessions",
        json={"dataset_id": str(ds.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = sess_resp.json()["id"]

    resp = await test_client.post(
        "/api/v1/studio/annotations/save",
        json={
            "session_id": session_id,
            "image_index": 0,
            "annotations": [
                {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4, "label": "vehicle", "confidence": 0.95},
            ],
            "tool_used": "bbox",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["saved"] is True
    assert body["annotation_count"] == 1
    assert body["image_index"] == 0


@pytest.mark.asyncio
async def test_save_annotation_wrong_session_user(db_session, test_client):
    user1 = await _create_user(db_session)
    user2 = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    await _create_annotation(db_session, ds.id, batch.id, index=0)

    token1 = _make_token(user1)
    token2 = _make_token(user2)

    sess_resp = await test_client.post(
        "/api/v1/studio/sessions",
        json={"dataset_id": str(ds.id)},
        headers={"Authorization": f"Bearer {token1}"},
    )
    session_id = sess_resp.json()["id"]

    resp = await test_client.post(
        "/api/v1/studio/annotations/save",
        json={
            "session_id": session_id,
            "image_index": 0,
            "annotations": [
                {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4, "label": "vehicle"},
            ],
        },
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_health_score(db_session, test_client):
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    await _create_annotation(db_session, ds.id, batch.id, index=0)
    token = _make_token(user)

    resp = await test_client.get(
        f"/api/v1/studio/datasets/{ds.id}/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dataset_id"] == str(ds.id)
    assert body["overall_score"] == 0.0
    assert body["completeness_pct"] == 0.0
    assert len(body["recommendations"]) > 0


@pytest.mark.asyncio
async def test_create_export_job(db_session, test_client):
    user = await _create_user(db_session)
    ds = await _create_dataset(db_session)
    token = _make_token(user)

    resp = await test_client.post(
        "/api/v1/studio/exports",
        json={"dataset_id": str(ds.id), "format": "coco"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] in ("PENDING", "PROCESSING", "COMPLETED", "FAILED")
    assert body["format"] == "coco"


@pytest.mark.asyncio
async def test_get_export_job(db_session, test_client):
    user = await _create_user(db_session)
    ds = await _create_dataset(db_session)
    token = _make_token(user)

    create_resp = await test_client.post(
        "/api/v1/studio/exports",
        json={"dataset_id": str(ds.id), "format": "yolo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    export_id = create_resp.json()["id"]

    resp = await test_client.get(
        f"/api/v1/studio/exports/{export_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["format"] == "yolo"


@pytest.mark.asyncio
async def test_get_export_job_wrong_user(db_session, test_client):
    user1 = await _create_user(db_session)
    user2 = await _create_user(db_session)
    ds = await _create_dataset(db_session)
    token1 = _make_token(user1)
    token2 = _make_token(user2)

    create_resp = await test_client.post(
        "/api/v1/studio/exports",
        json={"dataset_id": str(ds.id), "format": "coco"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    export_id = create_resp.json()["id"]

    resp = await test_client.get(
        f"/api/v1/studio/exports/{export_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_health_score_empty_dataset(db_session, test_client):
    user = await _create_user(db_session)
    ds = await _create_dataset(db_session)
    token = _make_token(user)

    resp = await test_client.get(
        f"/api/v1/studio/datasets/{ds.id}/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert any("no annotations" in r.lower() for r in body["recommendations"])
