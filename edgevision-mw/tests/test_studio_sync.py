"""Phase 4 integration tests: offline sync batch endpoint."""

from datetime import UTC
from uuid import uuid4

import pytest
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
from app.models.studio import AnnotationAction, AnnotationSession

# ─── Helpers ───


async def _create_user(db, role="ANNOTATOR"):
    user_id = uuid4()
    user = User(
        id=user_id,
        email=f"sync-{user_id.hex[:8]}@test.com",
        hashed_password="fakehash",
        full_name="Sync Test User",
        role=role,
        is_active=True,
        dpa_signed=True,
    )
    db.add(user)
    await db.commit()
    return user


async def _create_node(db):
    node = Node(
        id=uuid4(),
        node_id=f"SYNC-{uuid4().hex[:8]}",
        district="Lilongwe",
        latitude=-13.9626,
        longitude=33.7741,
        category=NodeCategory.ROAD,
        hardware_profile={"gpu": "jetson"},
        network_config={"apn": "airtel"},
        capture_schedule="*/10 * * * *",
        interest_classes=["vehicle", "pedestrian"],
        pii_mode=PIIMode.STRICT,
        firmware_version="1.0.0",
        public_key=b"\x01" * 32,
        status=NodeStatus.ONLINE,
        is_enabled=True,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


async def _create_dataset(db):
    ds = Dataset(
        id=uuid4(),
        dataset_id=f"DS-SYNC-{uuid4().hex[:6]}",
        name="Sync Test Dataset",
        version="1.0",
        status=DatasetStatus.READY,
        sample_count=5,
        classes={"vehicle": 3, "pedestrian": 2},
        annotations_per_image=2.0,
        image_width=1920,
        image_height=1080,
        geographic_coverage={"Lilongwe": 5},
        demographic_report={"age_groups": {"adult": 80}},
        price_usd=0,
        license_type=LicenseType.PERPETUAL,
        consent_coverage_pct=100.0,
        pii_scrub_verified=True,
        iaa_score=0.95,
        formats=["coco", "yolo"],
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


async def _create_batch(db, node):
    batch = IngestionBatch(
        batch_id=f"SBATCH-SYNC-{uuid4().hex[:8]}",
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


async def _create_annotation(db, dataset, batch, image_index=0, human_labels=None):
    ann = Annotation(
        id=uuid4(),
        dataset_id=dataset.id,
        batch_id=batch.id,
        image_index=image_index,
        image_path=f"images/{image_index:04d}.jpg",
        thumbnail_path=f"thumbs/{image_index:04d}.jpg",
        detected_objects={},
        auto_labels={},
        quality_score=1.0,
        status=AnnotationStatus.PENDING,
        human_labels=human_labels,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return ann


# ─── Tests ───


@pytest.mark.asyncio
async def test_sync_edit_updates_labels(db_session, test_client, jwt_token_factory):
    """Editing an annotation via sync updates its human_labels."""
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    ds = await _create_dataset(db_session)
    batch = await _create_batch(db_session, node)
    ann = await _create_annotation(db_session, ds, batch, image_index=0)

    sess = AnnotationSession(
        user_id=user.id,
        dataset_id=ds.id,
        started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        is_active=True,
        image_count=1,
        annotations_created=0,
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)

    token = create_access_token(data={"sub": str(user.id), "role": "ANNOTATOR", "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/studio/sync/batch",
        headers=headers,
        json={
            "session_id": str(sess.id),
            "actions": [
                {
                    "annotation_id": str(ann.id),
                    "action_type": "edit",
                    "payload": {
                        "human_labels": {"boxes": [{"label": "car", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}]}
                    },
                }
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["committed"]) == 1
    assert str(ann.id) in data["committed"]
    assert len(data["conflicts"]) == 0
    assert len(data["rejected"]) == 0

    await db_session.refresh(ann)
    assert ann.human_labels is not None
    assert ann.human_labels["boxes"][0]["label"] == "car"


@pytest.mark.asyncio
async def test_sync_edit_etag_conflict(db_session, test_client, jwt_token_factory):
    """Wrong etag triggers a conflict response."""
    from datetime import datetime

    user = await _create_user(db_session)
    node = await _create_node(db_session)
    ds = await _create_dataset(db_session)
    batch = await _create_batch(db_session, node)
    ann = await _create_annotation(db_session, ds, batch, image_index=1)

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

    token = create_access_token(data={"sub": str(user.id), "role": "ANNOTATOR", "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/studio/sync/batch",
        headers=headers,
        json={
            "session_id": str(sess.id),
            "actions": [
                {
                    "annotation_id": str(ann.id),
                    "action_type": "edit",
                    "payload": {"human_labels": {"boxes": []}},
                    "etag": "definitely_wrong_etag_value",
                }
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["conflicts"]) == 1
    assert data["conflicts"][0]["resolution"] == "server_wins"


@pytest.mark.asyncio
async def test_sync_approve_reject(db_session, test_client, jwt_token_factory):
    """Approve and reject actions update annotation status."""
    from datetime import datetime

    user = await _create_user(db_session)
    node = await _create_node(db_session)
    ds = await _create_dataset(db_session)
    batch = await _create_batch(db_session, node)

    ann1 = await _create_annotation(db_session, ds, batch, image_index=10)
    ann2 = await _create_annotation(db_session, ds, batch, image_index=11)

    sess = AnnotationSession(
        user_id=user.id,
        dataset_id=ds.id,
        started_at=datetime.now(UTC),
        is_active=True,
        image_count=2,
        annotations_created=0,
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)

    token = create_access_token(data={"sub": str(user.id), "role": "ANNOTATOR", "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/studio/sync/batch",
        headers=headers,
        json={
            "session_id": str(sess.id),
            "actions": [
                {"annotation_id": str(ann1.id), "action_type": "approve"},
                {"annotation_id": str(ann2.id), "action_type": "reject"},
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["committed"]) == 2

    await db_session.refresh(ann1)
    await db_session.refresh(ann2)
    assert ann1.status == AnnotationStatus.CERTIFIED
    assert ann1.is_certified is True
    assert ann2.status == AnnotationStatus.REJECTED


@pytest.mark.asyncio
async def test_sync_session_not_found(db_session, test_client, jwt_token_factory):
    """Syncing to a non-existent session returns 404."""

    user = await _create_user(db_session)
    fake_session_id = str(uuid4())

    token = create_access_token(data={"sub": str(user.id), "role": "ANNOTATOR", "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/studio/sync/batch",
        headers=headers,
        json={
            "session_id": fake_session_id,
            "actions": [],
        },
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sync_wrong_user_session(db_session, test_client, jwt_token_factory):
    """Syncing to another user's session returns 404."""
    from datetime import datetime

    user1 = await _create_user(db_session)
    user2 = await _create_user(db_session)
    await _create_node(db_session)
    ds = await _create_dataset(db_session)

    sess = AnnotationSession(
        user_id=user2.id,
        dataset_id=ds.id,
        started_at=datetime.now(UTC),
        is_active=True,
        image_count=0,
        annotations_created=0,
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)

    token = create_access_token(data={"sub": str(user1.id), "role": "ANNOTATOR", "email": user1.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/studio/sync/batch",
        headers=headers,
        json={
            "session_id": str(sess.id),
            "actions": [],
        },
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sync_delete_removes_labels(db_session, test_client, jwt_token_factory):
    """Delete action clears human_labels."""
    from datetime import datetime

    user = await _create_user(db_session)
    node = await _create_node(db_session)
    ds = await _create_dataset(db_session)
    batch = await _create_batch(db_session, node)
    ann = await _create_annotation(
        db_session, ds, batch, image_index=20,
        human_labels={"boxes": [{"label": "car", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}]},
    )

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

    token = create_access_token(data={"sub": str(user.id), "role": "ANNOTATOR", "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/studio/sync/batch",
        headers=headers,
        json={
            "session_id": str(sess.id),
            "actions": [
                {"annotation_id": str(ann.id), "action_type": "delete"},
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["committed"]) == 1

    await db_session.refresh(ann)
    assert ann.human_labels is None
    assert ann.status == AnnotationStatus.PENDING


@pytest.mark.asyncio
async def test_sync_creates_action_logs(db_session, test_client, jwt_token_factory):
    """Each committed action creates an AnnotationAction log."""
    from datetime import datetime

    user = await _create_user(db_session)
    node = await _create_node(db_session)
    ds = await _create_dataset(db_session)
    batch = await _create_batch(db_session, node)
    ann = await _create_annotation(db_session, ds, batch, image_index=30)

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

    token = create_access_token(data={"sub": str(user.id), "role": "ANNOTATOR", "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/studio/sync/batch",
        headers=headers,
        json={
            "session_id": str(sess.id),
            "actions": [
                {
                    "annotation_id": str(ann.id),
                    "action_type": "edit",
                    "payload": {"human_labels": {"boxes": []}},
                }
            ],
        },
    )

    assert resp.status_code == 200

    stmt = select(AnnotationAction).where(AnnotationAction.session_id == sess.id)
    result = await db_session.execute(stmt)
    actions = result.scalars().all()
    assert len(actions) == 1
    assert actions[0].action_type == "offline_edit"


@pytest.mark.asyncio
async def test_sync_status_returns_recent_changes(db_session, test_client, jwt_token_factory):
    """Sync status endpoint returns annotations modified since session start."""
    from datetime import datetime

    user = await _create_user(db_session)
    node = await _create_node(db_session)
    ds = await _create_dataset(db_session)
    batch = await _create_batch(db_session, node)
    await _create_annotation(db_session, ds, batch, image_index=40)

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

    token = create_access_token(data={"sub": str(user.id), "role": "ANNOTATOR", "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.get(
        f"/api/v1/studio/sync/status?session_id={sess.id}",
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == str(sess.id)
    assert data["session_active"] is True
    assert "server_changes" in data


@pytest.mark.asyncio
async def test_sync_status_session_not_found(db_session, test_client, jwt_token_factory):
    """Sync status for non-existent session returns 404."""
    user = await _create_user(db_session)
    token = create_access_token(data={"sub": str(user.id), "role": "ANNOTATOR", "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.get(
        f"/api/v1/studio/sync/status?session_id={uuid4()}",
        headers=headers,
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sync_batch_increments_counter(db_session, test_client, jwt_token_factory):
    """Session annotations_created counter increments by number of committed actions."""
    from datetime import datetime

    user = await _create_user(db_session)
    node = await _create_node(db_session)
    ds = await _create_dataset(db_session)
    batch = await _create_batch(db_session, node)

    anns = []
    for i in range(3):
        ann = await _create_annotation(db_session, ds, batch, image_index=50 + i)
        anns.append(ann)

    sess = AnnotationSession(
        user_id=user.id,
        dataset_id=ds.id,
        started_at=datetime.now(UTC),
        is_active=True,
        image_count=3,
        annotations_created=0,
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)

    token = create_access_token(data={"sub": str(user.id), "role": "ANNOTATOR", "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/studio/sync/batch",
        headers=headers,
        json={
            "session_id": str(sess.id),
            "actions": [
                {"annotation_id": str(a.id), "action_type": "approve"}
                for a in anns
            ],
        },
    )

    assert resp.status_code == 200
    assert len(resp.json()["committed"]) == 3

    await db_session.refresh(sess)
    assert sess.annotations_created == 3


@pytest.mark.asyncio
async def test_sync_reject_on_missing_labels(db_session, test_client, jwt_token_factory):
    """Create action without human_labels is rejected."""
    from datetime import datetime

    user = await _create_user(db_session)
    node = await _create_node(db_session)
    ds = await _create_dataset(db_session)
    batch = await _create_batch(db_session, node)
    ann = await _create_annotation(db_session, ds, batch, image_index=60)

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

    token = create_access_token(data={"sub": str(user.id), "role": "ANNOTATOR", "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/studio/sync/batch",
        headers=headers,
        json={
            "session_id": str(sess.id),
            "actions": [
                {
                    "annotation_id": str(ann.id),
                    "action_type": "create",
                    "payload": {"wrong_key": "no labels here"},
                }
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rejected"]) == 1
    assert "No human_labels" in data["rejected"][0]["reason"]


@pytest.mark.asyncio
async def test_sync_reject_on_missing_annotation(db_session, test_client, jwt_token_factory):
    """Action on non-existent annotation is rejected."""
    from datetime import datetime

    user = await _create_user(db_session)
    await _create_node(db_session)
    ds = await _create_dataset(db_session)

    sess = AnnotationSession(
        user_id=user.id,
        dataset_id=ds.id,
        started_at=datetime.now(UTC),
        is_active=True,
        image_count=0,
        annotations_created=0,
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)

    token = create_access_token(data={"sub": str(user.id), "role": "ANNOTATOR", "email": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    resp = await test_client.post(
        "/api/v1/studio/sync/batch",
        headers=headers,
        json={
            "session_id": str(sess.id),
            "actions": [
                {
                    "annotation_id": str(uuid4()),
                    "action_type": "edit",
                    "payload": {"human_labels": {"boxes": []}},
                }
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rejected"]) == 1
    assert "Not found" in data["rejected"][0]["reason"]
