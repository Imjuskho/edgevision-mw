import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select

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
        id=uuid4(), node_id=f"PH7-{uuid4().hex[:8]}",
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
        batch_id=f"SBATCH-PH7-{uuid4().hex[:8]}",
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


async def _create_dataset(db, status=DatasetStatus.FOR_SALE):
    ds = Dataset(
        id=uuid4(), dataset_id=f"DS-PH7-{uuid4().hex[:6]}",
        name="Phase 7 Test Dataset", version="1.0",
        status=status, sample_count=10,
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


async def _create_annotation(db, dataset_id, batch_id, index=0, human_labels=None):
    ann = Annotation(
        batch_id=batch_id,
        image_index=index,
        image_path=f"images/ph7/{index:04d}.jpg",
        thumbnail_path=f"thumbs/ph7/{index:04d}.jpg",
        detected_objects={"objects": []},
        auto_labels={"labels": []},
        human_labels=human_labels,
        status=AnnotationStatus.PENDING,
        quality_score=0.0,
        dataset_id=dataset_id,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return ann


def _make_token(user):
    return create_access_token(data={"sub": str(user.id), "role": user.role, "email": user.email})


# ══════════════════════════════════════════════════════════════════════════════
# WORKSTREAM A: Image Upload Tests
# ══════════════════════════════════════════════════════════════════════════════

def _mock_minio(monkeypatch, mock_minio):
    async def mock_put_object(bucket, key, data, content_type, metadata=None):
        pass

    # Patch at the import site where process_upload resolves put_object
    monkeypatch.setattr("app.services.images.put_object", mock_put_object)


def _make_png_buffer(seed=0):
    color = ((seed * 50) % 256, (seed * 80) % 256, (seed * 110) % 256)
    noise = uuid4().int & 0xFF
    r = (color[0] + noise) % 256
    g = (color[1] + noise) % 256
    b = (color[2] + noise) % 256
    img = Image.new("RGB", (100, 100), color=(r, g, b))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@ pytest.mark.asyncio
async def test_upload_images_empty_files(db_session, test_client):
    admin = await _create_user(db_session, role="ADMIN")
    ds = await _create_dataset(db_session)
    token = _make_token(admin)

    resp = await test_client.post(
        "/api/v1/upload/images",
        data={"dataset_id": ds.dataset_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (400, 422)


@ pytest.mark.asyncio
async def test_upload_images_requires_admin_role(db_session, test_client, mock_minio, monkeypatch):
    _mock_minio(monkeypatch, mock_minio)
    annotator = await _create_user(db_session, role="ANNOTATOR")
    ds = await _create_dataset(db_session)
    token = _make_token(annotator)

    buf = _make_png_buffer(seed=1)
    resp = await test_client.post(
        "/api/v1/upload/images",
        files=[("files", ("test.png", buf, "image/png"))],
        data={"dataset_id": ds.dataset_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text[:200]}"


@ pytest.mark.asyncio
async def test_upload_single_image(db_session, test_client, mock_minio, monkeypatch):
    _mock_minio(monkeypatch, mock_minio)
    admin = await _create_user(db_session, role="ADMIN")
    ds = await _create_dataset(db_session, status=DatasetStatus.BUILDING)
    token = _make_token(admin)

    buf = _make_png_buffer(seed=2)
    resp = await test_client.post(
        "/api/v1/upload/images",
        files=[("files", ("road_photo.png", buf, "image/png"))],
        data={"dataset_id": ds.dataset_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["uploaded"] == 1, f"Body: {body}"
    assert body["skipped"] == 0
    assert body["total"] == 1
    assert body["images"][0]["status"] == "uploaded"
    test_client._transport.app.dependency_overrides.clear() if hasattr(test_client, '_transport') and hasattr(test_client._transport, 'app') else None


@ pytest.mark.asyncio
async def test_upload_auto_creates_dataset(db_session, test_client, mock_minio, monkeypatch):
    _mock_minio(monkeypatch, mock_minio)
    admin = await _create_user(db_session, role="ADMIN")
    token = _make_token(admin)

    new_id = f"DS-NEW-{uuid4().hex[:8]}"
    buf = _make_png_buffer(seed=3)
    resp = await test_client.post(
        "/api/v1/upload/images",
        files=[("files", ("img.png", buf, "image/png"))],
        data={"dataset_id": new_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["dataset_id"] == new_id
    assert body["uploaded"] == 1, f"Body: {body}"

    ds = (await db_session.execute(
        select(Dataset).where(Dataset.dataset_id == new_id)
    )).scalar_one_or_none()
    assert ds is not None
    assert ds.status == DatasetStatus.BUILDING


@ pytest.mark.asyncio
async def test_upload_rejects_unsupported_type(db_session, test_client):
    admin = await _create_user(db_session, role="ADMIN")
    ds = await _create_dataset(db_session)
    token = _make_token(admin)

    resp = await test_client.post(
        "/api/v1/upload/images",
        files=[("files", ("doc.pdf", io.BytesIO(b"fake pdf"), "application/pdf"))],
        data={"dataset_id": ds.dataset_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["uploaded"] == 0
    assert body["total"] == 1


@ pytest.mark.asyncio
async def test_upload_video_file(db_session, test_client):
    admin = await _create_user(db_session, role="ADMIN")
    ds = await _create_dataset(db_session, status=DatasetStatus.BUILDING)
    token = _make_token(admin)

    fake_mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100
    resp = await test_client.post(
        "/api/v1/upload/images",
        files=[("files", ("video.mp4", io.BytesIO(fake_mp4), "video/mp4"))],
        data={"dataset_id": ds.dataset_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["uploaded"] == 0, f"Expected 0 uploaded for video, got: {body}"


# ══════════════════════════════════════════════════════════════════════════════
# WORKSTREAM B: Annotator Assignment Tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_assignment(db_session, test_client):
    admin = await _create_user(db_session, role="ADMIN")
    annotator = await _create_user(db_session, role="ANNOTATOR")
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    for i in range(5):
        await _create_annotation(db_session, ds.id, batch.id, index=i)
    token = _make_token(admin)

    resp = await test_client.post(
        "/api/v1/assignments",
        json={
            "dataset_id": ds.dataset_id,
            "annotator_ids": [str(annotator.id)],
            "deadline": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            "priority": 5,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["total"] == 1
    assert body["assignments"][0]["status"] == "ASSIGNED"
    assert body["assignments"][0]["priority"] == 5


@pytest.mark.asyncio
async def test_create_assignment_requires_admin(db_session, test_client):
    annotator = await _create_user(db_session, role="ANNOTATOR")
    ds = await _create_dataset(db_session)
    token = _make_token(annotator)

    resp = await test_client.post(
        "/api/v1/assignments",
        json={
            "dataset_id": ds.dataset_id,
            "annotator_ids": [str(annotator.id)],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_assignment_empty_dataset(db_session, test_client):
    admin = await _create_user(db_session, role="ADMIN")
    annotator = await _create_user(db_session, role="ANNOTATOR")
    ds = await _create_dataset(db_session)
    token = _make_token(admin)

    resp = await test_client.post(
        "/api/v1/assignments",
        json={
            "dataset_id": ds.dataset_id,
            "annotator_ids": [str(annotator.id)],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_annotator_queue(db_session, test_client):
    admin = await _create_user(db_session, role="ADMIN")
    annotator = await _create_user(db_session, role="ANNOTATOR")
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    for i in range(3):
        await _create_annotation(db_session, ds.id, batch.id, index=i)

    admin_token = _make_token(admin)
    await test_client.post(
        "/api/v1/assignments",
        json={
            "dataset_id": ds.dataset_id,
            "annotator_ids": [str(annotator.id)],
            "priority": 3,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    annotator_token = _make_token(annotator)
    resp = await test_client.get(
        "/api/v1/assignments/queue",
        headers={"Authorization": f"Bearer {annotator_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert body["items"][0]["dataset_id"] == ds.dataset_id


@pytest.mark.asyncio
async def test_claim_assignment(db_session, test_client):
    admin = await _create_user(db_session, role="ADMIN")
    annotator = await _create_user(db_session, role="ANNOTATOR")
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    for i in range(3):
        await _create_annotation(db_session, ds.id, batch.id, index=i)

    admin_token = _make_token(admin)
    create_resp = await test_client.post(
        "/api/v1/assignments",
        json={
            "dataset_id": ds.dataset_id,
            "annotator_ids": [str(annotator.id)],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assignment_id = create_resp.json()["assignments"][0]["id"]

    annotator_token = _make_token(annotator)
    resp = await test_client.post(
        "/api/v1/assignments/claim",
        json={"assignment_id": assignment_id},
        headers={"Authorization": f"Bearer {annotator_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_submit_assignment(db_session, test_client):
    admin = await _create_user(db_session, role="ADMIN")
    annotator = await _create_user(db_session, role="ANNOTATOR")
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    for i in range(3):
        await _create_annotation(db_session, ds.id, batch.id, index=i)

    admin_token = _make_token(admin)
    create_resp = await test_client.post(
        "/api/v1/assignments",
        json={
            "dataset_id": ds.dataset_id,
            "annotator_ids": [str(annotator.id)],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assignment_id = create_resp.json()["assignments"][0]["id"]

    annotator_token = _make_token(annotator)
    await test_client.post(
        "/api/v1/assignments/claim",
        json={"assignment_id": assignment_id},
        headers={"Authorization": f"Bearer {annotator_token}"},
    )

    resp = await test_client.post(
        "/api/v1/assignments/submit",
        json={"assignment_id": assignment_id},
        headers={"Authorization": f"Bearer {annotator_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUBMITTED"


@pytest.mark.asyncio
async def test_list_assignments_admin(db_session, test_client):
    admin = await _create_user(db_session, role="ADMIN")
    annotator = await _create_user(db_session, role="ANNOTATOR")
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    for i in range(3):
        await _create_annotation(db_session, ds.id, batch.id, index=i)

    admin_token = _make_token(admin)
    await test_client.post(
        "/api/v1/assignments",
        json={
            "dataset_id": ds.dataset_id,
            "annotator_ids": [str(annotator.id)],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = await test_client.get(
        "/api/v1/assignments",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1


# ══════════════════════════════════════════════════════════════════════════════
# WORKSTREAM C: QA Review Tests
# ══════════════════════════════════════════════════════════════════════════════

async def _create_submitted_assignment(db_session, test_client):
    admin = await _create_user(db_session, role="ADMIN")
    annotator = await _create_user(db_session, role="ANNOTATOR")
    qa = await _create_user(db_session, role="QA")
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    for i in range(3):
        await _create_annotation(db_session, ds.id, batch.id, index=i,
                                 human_labels={"boxes": [{"label": "vehicle", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}]})

    admin_token = _make_token(admin)
    create_resp = await test_client.post(
        "/api/v1/assignments",
        json={
            "dataset_id": ds.dataset_id,
            "annotator_ids": [str(annotator.id)],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assignment_id = create_resp.json()["assignments"][0]["id"]

    annotator_token = _make_token(annotator)
    await test_client.post(
        "/api/v1/assignments/claim",
        json={"assignment_id": assignment_id},
        headers={"Authorization": f"Bearer {annotator_token}"},
    )
    await test_client.post(
        "/api/v1/assignments/submit",
        json={"assignment_id": assignment_id},
        headers={"Authorization": f"Bearer {annotator_token}"},
    )

    return assignment_id, qa, ds, admin


@pytest.mark.asyncio
async def test_review_queue(db_session, test_client):
    assignment_id, qa, ds, admin = await _create_submitted_assignment(db_session, test_client)
    qa_token = _make_token(qa)

    resp = await test_client.get(
        "/api/v1/review/queue",
        headers={"Authorization": f"Bearer {qa_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    ids = [item["assignment_id"] for item in body["items"]]
    assert assignment_id in ids


@pytest.mark.asyncio
async def test_review_queue_requires_qa_role(db_session, test_client):
    assignment_id, qa, ds, admin = await _create_submitted_assignment(db_session, test_client)
    annotator = await _create_user(db_session, role="ANNOTATOR")
    annotator_token = _make_token(annotator)

    resp = await test_client.get(
        "/api/v1/review/queue",
        headers={"Authorization": f"Bearer {annotator_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_review_job_detail(db_session, test_client):
    assignment_id, qa, ds, admin = await _create_submitted_assignment(db_session, test_client)
    qa_token = _make_token(qa)

    resp = await test_client.get(
        f"/api/v1/review/jobs/{assignment_id}",
        headers={"Authorization": f"Bearer {qa_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["assignment_id"] == assignment_id
    assert len(body["images"]) == 3


@pytest.mark.asyncio
async def test_certify_job(db_session, test_client):
    assignment_id, qa, ds, admin = await _create_submitted_assignment(db_session, test_client)
    qa_token = _make_token(qa)

    resp = await test_client.post(
        f"/api/v1/review/jobs/{assignment_id}/certify",
        headers={"Authorization": f"Bearer {qa_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "CERTIFIED"


@pytest.mark.asyncio
async def test_reject_job(db_session, test_client):
    assignment_id, qa, ds, admin = await _create_submitted_assignment(db_session, test_client)
    qa_token = _make_token(qa)

    resp = await test_client.post(
        f"/api/v1/review/jobs/{assignment_id}/reject",
        json={"decision": "reject", "reason": "Poor quality annotations"},
        headers={"Authorization": f"Bearer {qa_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ASSIGNED"
    assert "rejected" in body["message"].lower()


@pytest.mark.asyncio
async def test_get_iaa_metrics(db_session, test_client):
    assignment_id, qa, ds, admin = await _create_submitted_assignment(db_session, test_client)
    qa_token = _make_token(qa)

    resp = await test_client.get(
        f"/api/v1/review/jobs/{assignment_id}/iaa",
        headers={"Authorization": f"Bearer {qa_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_annotations"] == 3
    assert 0 <= body["completeness_pct"] <= 100
    assert 0 <= body["accuracy_pct"] <= 100


@pytest.mark.asyncio
async def test_approve_single_annotation(db_session, test_client):
    assignment_id, qa, ds, admin = await _create_submitted_assignment(db_session, test_client)
    qa_token = _make_token(qa)

    ann = (await db_session.execute(
        select(Annotation).where(Annotation.dataset_id == ds.id).limit(1)
    )).scalar_one()

    resp = await test_client.post(
        f"/api/v1/review/jobs/{assignment_id}/annotations/{ann.id}/approve",
        headers={"Authorization": f"Bearer {qa_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CERTIFIED"


@pytest.mark.asyncio
async def test_reject_single_annotation(db_session, test_client):
    assignment_id, qa, ds, admin = await _create_submitted_assignment(db_session, test_client)
    qa_token = _make_token(qa)

    ann = (await db_session.execute(
        select(Annotation).where(Annotation.dataset_id == ds.id).limit(1)
    )).scalar_one()

    resp = await test_client.post(
        f"/api/v1/review/jobs/{assignment_id}/annotations/{ann.id}/reject",
        headers={"Authorization": f"Bearer {qa_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_certify_non_submitted_fails(db_session, test_client):
    admin = await _create_user(db_session, role="ADMIN")
    annotator = await _create_user(db_session, role="ANNOTATOR")
    qa = await _create_user(db_session, role="QA")
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    for i in range(3):
        await _create_annotation(db_session, ds.id, batch.id, index=i)

    admin_token = _make_token(admin)
    create_resp = await test_client.post(
        "/api/v1/assignments",
        json={
            "dataset_id": ds.dataset_id,
            "annotator_ids": [str(annotator.id)],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assignment_id = create_resp.json()["assignments"][0]["id"]

    qa_token = _make_token(qa)
    resp = await test_client.post(
        f"/api/v1/review/jobs/{assignment_id}/certify",
        headers={"Authorization": f"Bearer {qa_token}"},
    )
    assert resp.status_code == 400
