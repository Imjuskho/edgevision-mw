"""Tests for the Buyer Dashboard API (D2)."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.annotation import Annotation
from app.models.buyer import User
from app.models.dataset import Dataset
from app.models.enums import (
    AnnotationStatus,
    BatchStatus,
    DatasetStatus,
    ExportStatus,
    LicenseType,
    NodeCategory,
    NodeStatus,
    PIIMode,
)
from app.models.export import Export
from app.models.ingestion import IngestionBatch
from app.models.invoice import Invoice
from app.models.node import Node


async def _create_buyer(db: AsyncSession, *, email: str | None = None) -> User:
    uid = uuid4()
    user = User(
        id=uid,
        email=email or f"buyer-{uid.hex[:8]}@test.com",
        hashed_password="fake",
        role="BUYER",
        full_name="Test Buyer",
    )
    db.add(user)
    await db.flush()
    return user


async def _create_node_in_db(db: AsyncSession) -> Node:
    node = Node(
        id=uuid4(),
        node_id=f"NODE-{uuid4().hex[:8]}",
        district="Blantyre",
        latitude=-15.7861,
        longitude=35.0058,
        category=NodeCategory.ROAD,
        hardware_profile={},
        network_config={},
        capture_schedule="*/10 * * * *",
        interest_classes=["vehicle"],
        pii_mode=PIIMode.STRICT,
        public_key=b"\x01" * 32,
        firmware_version="1.0.0",
        status=NodeStatus.ONLINE,
        is_enabled=True,
    )
    db.add(node)
    await db.flush()
    return node


async def _create_owned_node(db: AsyncSession, buyer: User) -> Node:
    """Create a node linked to a buyer through the full ownership chain.

    Chain: Node → IngestionBatch → Annotation(dataset_id) → Dataset ← Export(buyer_id)
    """
    node = await _create_node_in_db(db)

    ds = Dataset(
        id=uuid4(),
        dataset_id=f"DS-{uuid4().hex[:6]}",
        name="Dashboard Test Dataset",
        version="1.0",
        status=DatasetStatus.FOR_SALE,
        sample_count=10,
        classes={"vehicle": 1},
        annotations_per_image=1.0,
        image_width=1920,
        image_height=1080,
        geographic_coverage={"districts": ["Blantyre"]},
        demographic_report={},
        consent_coverage_pct=1.0,
        pii_scrub_verified=True,
        iaa_score=0.97,
        formats=["COCO"],
        price_usd=Decimal("100.00"),
        license_type=LicenseType.ANNUAL,
    )
    db.add(ds)
    await db.flush()

    batch = IngestionBatch(
        batch_id=f"BATCH-{uuid4().hex[:8]}",
        node_id=node.id,
        hub_id="test-hub",
        event_count=1,
        file_size_bytes=1024,
        checksum_sha256="0" * 64,
        node_signature=b"\x01" * 64,
        compression_codec="none",
        quality_scores={},
        status=BatchStatus.INGESTED,
    )
    db.add(batch)
    await db.flush()

    ann = Annotation(
        batch_id=batch.id,
        image_index=0,
        image_path="test/images/0001.jpg",
        thumbnail_path="test/thumbs/0001.jpg",
        detected_objects={"objects": [{"class_name": "vehicle", "bbox": [10, 20, 100, 50], "confidence": 0.9}]},
        auto_labels={},
        status=AnnotationStatus.CERTIFIED,
        quality_score=0.95,
        iaa_score=0.97,
        dataset_id=ds.id,
    )
    db.add(ann)
    await db.flush()

    export = Export(
        id=uuid4(),
        dataset_id=ds.id,
        buyer_id=buyer.id,
        license_key=f"ev-dash-{uuid4().hex[:12]}",
        license_type=LicenseType.ANNUAL,
        status=ExportStatus.COMPLETED,
        price_usd=Decimal("100.00"),
        watermark_fingerprint=f"fp-dash-{uuid4().hex[:12]}",
        formats_delivered=["COCO"],
        initiated_at=datetime.now(UTC),
        usage_rights={},
    )
    db.add(export)
    await db.flush()

    return node


def _buyer_token(user_id: str) -> str:
    return create_access_token(data={"sub": user_id, "role": "BUYER", "email": "test@test.com"})


# ── Corridors ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_corridors_empty(test_client: AsyncClient, db_session: AsyncSession):
    user = await _create_buyer(db_session)
    await db_session.commit()
    token = _buyer_token(str(user.id))
    resp = await test_client.get(
        "/api/v1/buyer/corridors",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_corridors_unauthenticated(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/buyer/corridors")
    assert resp.status_code in (401, 403)


# ── Subscription ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_subscription(test_client: AsyncClient, db_session: AsyncSession):
    user = await _create_buyer(db_session)
    await db_session.commit()
    token = _buyer_token(str(user.id))
    resp = await test_client.get(
        "/api/v1/buyer/subscription",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["node_count"] >= 5
    assert float(data["monthly_price_usd"]) > 0


# ── Invoices ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_invoices(test_client: AsyncClient, db_session: AsyncSession):
    user = await _create_buyer(db_session)
    inv = Invoice(
        id=uuid4(),
        buyer_id=user.id,
        invoice_number="INV-2026-001",
        subscription_period_start=datetime(2026, 7, 1, tzinfo=UTC),
        subscription_period_end=datetime(2026, 7, 31, tzinfo=UTC),
        node_count=5,
        unit_price_usd=Decimal("50.00"),
        subtotal_usd=Decimal("250.00"),
        subtotal_mwk=Decimal("416666.67"),
        tax_usd=Decimal("0.00"),
        tax_mwk=Decimal("0.00"),
        total_usd=Decimal("250.00"),
        total_mwk=Decimal("416666.67"),
        status="pending",
    )
    db_session.add(inv)
    await db_session.commit()

    token = _buyer_token(str(user.id))
    resp = await test_client.get(
        "/api/v1/buyer/invoices",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["invoice_number"] == "INV-2026-001"


@pytest.mark.asyncio
async def test_list_invoices_empty(test_client: AsyncClient, db_session: AsyncSession):
    user = await _create_buyer(db_session)
    await db_session.commit()
    token = _buyer_token(str(user.id))
    resp = await test_client.get(
        "/api/v1/buyer/invoices",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ── Reports (with ownership chain) ──────────────────────────────────
@pytest.mark.asyncio
async def test_traffic_report(test_client: AsyncClient, db_session: AsyncSession):
    user = await _create_buyer(db_session)
    node = await _create_owned_node(db_session, user)
    await db_session.commit()
    token = _buyer_token(str(user.id))
    resp = await test_client.get(
        "/api/v1/buyer/reports/traffic",
        params={
            "node_ids": str(node.id),
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-31T23:59:59Z",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["total_vehicles"] >= 0


@pytest.mark.asyncio
async def test_near_miss_heatmap(test_client: AsyncClient, db_session: AsyncSession):
    user = await _create_buyer(db_session)
    node = await _create_owned_node(db_session, user)
    await db_session.commit()
    token = _buyer_token(str(user.id))
    resp = await test_client.get(
        "/api/v1/buyer/reports/near-miss",
        params={
            "node_ids": str(node.id),
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-31T23:59:59Z",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert isinstance(data["features"], list)


@pytest.mark.asyncio
async def test_pedestrian_exposure(test_client: AsyncClient, db_session: AsyncSession):
    user = await _create_buyer(db_session)
    node = await _create_owned_node(db_session, user)
    await db_session.commit()
    token = _buyer_token(str(user.id))
    resp = await test_client.get(
        "/api/v1/buyer/reports/pedestrian-exposure",
        params={
            "node_ids": str(node.id),
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-31T23:59:59Z",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_road_condition_report(test_client: AsyncClient, db_session: AsyncSession):
    user = await _create_buyer(db_session)
    node = await _create_owned_node(db_session, user)
    await db_session.commit()
    token = _buyer_token(str(user.id))
    resp = await test_client.get(
        "/api/v1/buyer/reports/road-condition",
        params={
            "node_ids": str(node.id),
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-31T23:59:59Z",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


@pytest.mark.asyncio
async def test_report_export_trigger(test_client: AsyncClient, db_session: AsyncSession):
    user = await _create_buyer(db_session)
    node = await _create_owned_node(db_session, user)
    await db_session.commit()
    token = _buyer_token(str(user.id))
    resp = await test_client.post(
        "/api/v1/buyer/reports/export",
        json={
            "report_type": "traffic",
            "node_ids": [str(node.id)],
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-31T23:59:59Z",
            "format": "csv",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] in ("pending", "completed")


# ── IDOR rejection tests ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_traffic_report_idor_rejected(test_client: AsyncClient, db_session: AsyncSession):
    """Buyer A cannot query traffic for a node only Buyer B owns."""
    buyer_a = await _create_buyer(db_session, email="a@test.com")
    buyer_b = await _create_buyer(db_session, email="b@test.com")
    node = await _create_owned_node(db_session, buyer_b)
    await db_session.commit()

    token = _buyer_token(str(buyer_a.id))
    resp = await test_client.get(
        "/api/v1/buyer/reports/traffic",
        params={
            "node_ids": str(node.id),
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-31T23:59:59Z",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_near_miss_report_idor_rejected(test_client: AsyncClient, db_session: AsyncSession):
    """Buyer A cannot query near-miss for a node only Buyer B owns."""
    buyer_a = await _create_buyer(db_session, email="a@test.com")
    buyer_b = await _create_buyer(db_session, email="b@test.com")
    node = await _create_owned_node(db_session, buyer_b)
    await db_session.commit()

    token = _buyer_token(str(buyer_a.id))
    resp = await test_client.get(
        "/api/v1/buyer/reports/near-miss",
        params={
            "node_ids": str(node.id),
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-31T23:59:59Z",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_pedestrian_exposure_idor_rejected(test_client: AsyncClient, db_session: AsyncSession):
    """Buyer A cannot query pedestrian-exposure for a node only Buyer B owns."""
    buyer_a = await _create_buyer(db_session, email="a@test.com")
    buyer_b = await _create_buyer(db_session, email="b@test.com")
    node = await _create_owned_node(db_session, buyer_b)
    await db_session.commit()

    token = _buyer_token(str(buyer_a.id))
    resp = await test_client.get(
        "/api/v1/buyer/reports/pedestrian-exposure",
        params={
            "node_ids": str(node.id),
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-31T23:59:59Z",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_road_condition_idor_rejected(test_client: AsyncClient, db_session: AsyncSession):
    """Buyer A cannot query road-condition for a node only Buyer B owns."""
    buyer_a = await _create_buyer(db_session, email="a@test.com")
    buyer_b = await _create_buyer(db_session, email="b@test.com")
    node = await _create_owned_node(db_session, buyer_b)
    await db_session.commit()

    token = _buyer_token(str(buyer_a.id))
    resp = await test_client.get(
        "/api/v1/buyer/reports/road-condition",
        params={
            "node_ids": str(node.id),
            "period_start": "2026-07-01T00:00:00Z",
            "period_end": "2026-07-31T23:59:59Z",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
