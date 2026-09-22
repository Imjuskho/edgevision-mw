"""Phase 3 integration tests: health score, dedup, export intelligence endpoints."""

from decimal import Decimal
from unittest.mock import MagicMock, patch
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
from app.models.ingestion import IngestionBatch
from app.models.node import Node
from app.models.studio import (
    DuplicateGroup,
    ExportJob,
)
from tests.conftest import _create_node

# ─── Test data factories (reuse pattern from test_studio.py) ───


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


async def _create_batch(db, node):
    batch = IngestionBatch(
        batch_id=f"SBATCH-PH3-{uuid4().hex[:8]}",
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
        id=uuid4(),
        dataset_id=f"DS-PH3-{uuid4().hex[:6]}",
        name="Phase3 Test Dataset",
        version="1.0",
        status=DatasetStatus.FOR_SALE,
        sample_count=10,
        classes={"vehicle": 5, "pedestrian": 3, "bicycle": 2},
        annotations_per_image=2.0,
        image_width=1920,
        image_height=1080,
        geographic_coverage={"districts": ["Lilongwe"]},
        demographic_report={"age_groups": {}},
        consent_coverage_pct=1.0,
        pii_scrub_verified=True,
        iaa_score=0.90,
        formats=["COCO"],
        price_usd=Decimal("100.00"),
        license_type=LicenseType.ANNUAL,
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


async def _create_annotation(db, dataset_id, batch_id, index=0, class_name="vehicle", quality=0.85, lat=None, lon=None):
    ann = Annotation(
        batch_id=batch_id,
        image_index=index,
        image_path=f"images/ph3/{index:04d}.jpg",
        thumbnail_path=f"thumbs/ph3/{index:04d}.jpg",
        detected_objects={"objects": []},
        auto_labels={"class": class_name, "confidence": quality},
        status=AnnotationStatus.PENDING,
        quality_score=quality,
        dataset_id=dataset_id,
        gps_lat=lat,
        gps_lon=lon,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return ann


def _make_token(user):
    return create_access_token(data={"sub": str(user.id), "role": user.role, "email": user.email})


# ─── Health Score Tests ───


@pytest.mark.asyncio
async def test_health_score_empty_dataset(db_session, test_client):
    """Health score for empty dataset returns 0 with recommendation."""
    user = await _create_user(db_session, role="ANNOTATOR")
    ds = await _create_dataset(db_session)
    token = _make_token(user)

    resp = await test_client.get(
        f"/api/v1/studio/datasets/{ds.id}/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_score"] == 0.0
    assert data["completeness_pct"] == 0.0
    assert data["accuracy_pct"] == 0.0
    assert len(data["recommendations"]) > 0


@pytest.mark.asyncio
async def test_health_score_with_annotations(db_session, test_client):
    """Health score returns valid dimensions when annotations exist."""
    user = await _create_user(db_session, role="ANNOTATOR")
    ds = await _create_dataset(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)

    classes = ["vehicle", "vehicle", "pedestrian", "pedestrian", "bicycle"]
    for i, cls in enumerate(classes):
        await _create_annotation(
            db_session,
            ds.id,
            batch.id,
            index=i,
            class_name=cls,
            quality=0.8 + i * 0.02,
            lat=-13.96 + i * 0.001,
            lon=33.77 + i * 0.001,
        )

    token = _make_token(user)
    resp = await test_client.get(
        f"/api/v1/studio/datasets/{ds.id}/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_score" in data
    assert "completeness_pct" in data
    assert "accuracy_pct" in data


@pytest.mark.asyncio
async def test_health_score_404_unknown_dataset(db_session, test_client):
    """Returns 404 for nonexistent dataset."""
    user = await _create_user(db_session, role="ANNOTATOR")
    token = _make_token(user)
    fake_id = uuid4()

    resp = await test_client.get(
        f"/api/v1/studio/datasets/{fake_id}/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_class_distribution(db_session, test_client):
    """Class distribution returns correct counts and percentages."""
    user = await _create_user(db_session, role="ANNOTATOR")
    ds = await _create_dataset(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)

    for i, cls in enumerate(["vehicle", "vehicle", "pedestrian"]):
        await _create_annotation(db_session, ds.id, batch.id, index=i, class_name=cls, quality=0.9)

    token = _make_token(user)
    resp = await test_client.get(
        f"/api/v1/studio/datasets/{ds.id}/class-distribution",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "vehicle" in data
    assert "pedestrian" in data
    assert data["vehicle"]["count"] == 2
    assert data["pedestrian"]["count"] == 1
    assert data["vehicle"]["percentage"] > 50.0


# ─── Dedup Tests ───


@pytest.mark.asyncio
async def test_dedup_analyze_empty_dataset(db_session, test_client):
    """Dedup analyze on empty dataset returns empty groups."""
    user = await _create_user(db_session, role="OPERATOR")
    ds = await _create_dataset(db_session)
    token = _make_token(user)

    mock_task = MagicMock()
    mock_task.id = str(uuid4())

    with patch("app.api.studio_intelligence.celery_app") as mock_celery:
        mock_celery.send_task.return_value = mock_task
        resp = await test_client.post(
            "/api/v1/studio/dedup/analyze",
            json={"dataset_id": str(ds.id), "methods": ["phash"], "threshold": 0.92},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "PENDING"


@pytest.mark.asyncio
async def test_dedup_analyze_requires_operator_role(db_session, test_client):
    """Dedup analyze requires OPERATOR or ADMIN role."""
    user = await _create_user(db_session, role="ANNOTATOR")
    ds = await _create_dataset(db_session)
    token = _make_token(user)

    resp = await test_client.post(
        "/api/v1/studio/dedup/analyze",
        json={"dataset_id": str(ds.id), "methods": ["phash"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dedup_resolve(db_session, test_client):
    """Dedup resolve accepts resolution actions."""
    user = await _create_user(db_session, role="OPERATOR")
    ds = await _create_dataset(db_session)

    group = DuplicateGroup(
        dataset_id=ds.id,
        detection_method="clip_semantic",
        similarity_score=0.95,
        strategy="auto",
        status="open",
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    token = _make_token(user)
    resp = await test_client.post(
        "/api/v1/studio/dedup/resolve",
        json={
            "dataset_id": str(ds.id),
            "resolutions": [{"group_id": str(group.id), "action": "keep_first"}],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "resolved"


# ─── Export Tests ───


@pytest.mark.asyncio
async def test_export_build_creates_job(db_session, test_client):
    """Export build creates an ExportJob and returns job_id."""
    user = await _create_user(db_session, role="OPERATOR")
    ds = await _create_dataset(db_session)
    token = _make_token(user)

    mock_task = MagicMock()
    mock_task.id = str(uuid4())

    with patch("app.api.studio_intelligence.celery_app") as mock_celery:
        mock_celery.send_task.return_value = mock_task
        resp = await test_client.post(
            "/api/v1/studio/export/build",
            json={
                "dataset_id": str(ds.id),
                "format": "coco",
                "split_ratio": {"train": 0.7, "val": 0.2, "test": 0.1},
                "stratify": ["district"],
                "watermark": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "PENDING"


@pytest.mark.asyncio
async def test_export_list(db_session, test_client):
    """Export list returns exports for the authenticated user."""
    user = await _create_user(db_session, role="ANNOTATOR")
    ds = await _create_dataset(db_session)

    job = ExportJob(
        dataset_id=ds.id,
        user_id=user.id,
        status="COMPLETED",
        format="coco",
        progress_pct=100.0,
    )
    db_session.add(job)
    await db_session.commit()

    token = _make_token(user)
    resp = await test_client.get(
        "/api/v1/studio/exports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_export_status(db_session, test_client):
    """Export status returns job details."""
    user = await _create_user(db_session, role="ANNOTATOR")
    ds = await _create_dataset(db_session)

    job = ExportJob(
        dataset_id=ds.id,
        user_id=user.id,
        status="RUNNING",
        format="yolo",
        progress_pct=45.0,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    token = _make_token(user)
    resp = await test_client.get(
        f"/api/v1/studio/exports/{job.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "RUNNING"
    assert data["progress_pct"] == 45.0


@pytest.mark.asyncio
async def test_export_status_wrong_user(db_session, test_client):
    """Export status returns 403 for wrong user."""
    user1 = await _create_user(db_session, role="ANNOTATOR")
    user2 = await _create_user(db_session, role="ANNOTATOR")
    ds = await _create_dataset(db_session)

    job = ExportJob(
        dataset_id=ds.id,
        user_id=user1.id,
        status="COMPLETED",
        format="coco",
        progress_pct=100.0,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    token = _make_token(user2)
    resp = await test_client.get(
        f"/api/v1/studio/exports/{job.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
