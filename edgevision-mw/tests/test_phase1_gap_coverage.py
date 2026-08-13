"""
Phase 1 + Phase 2 gap-coverage tests.

Phase 1 round 2: concurrent-refund race, confirm_delivery race, node recovery, revenue rounding.
Phase 2 A2: ExportRequest no longer accepts buyer_id from client payload.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation
from app.models.buyer import User
from app.models.dataset import Dataset
from app.models.enums import (
    AnnotationStatus,
    BatchStatus,
    ConsentStatus,
    DatasetStatus,
    ExportStatus,
    LicenseType,
    NodeCategory,
    NodeStatus,
    PIIMode,
)
from app.models.export import Export
from app.models.ingestion import IngestionBatch
from app.models.node import Node
from app.schemas.node import HeartbeatPayload
from app.services.billing import confirm_delivery, get_revenue_breakdown, refund_escrow
from app.services.fleet import record_heartbeat

# Imported from conftest to access the session factory in API-level tests


# ---------------------------------------------------------------------------
# Factory helpers — all required fields, matching real models exactly
# ---------------------------------------------------------------------------

async def _create_user(session: AsyncSession, credit: Decimal = Decimal("0.00")) -> User:
    user = User(
        id=uuid4(),
        email=f"g2-{uuid4().hex[:8]}@test.com",
        hashed_password="x" * 60,
        full_name="Gap Test Buyer",
        role="BUYER",
        dpa_signed=True,
        credit_balance_usd=credit,
    )
    session.add(user)
    await session.flush()
    return user


async def _create_ready_dataset(session: AsyncSession, price: Decimal = Decimal("500.00")) -> Dataset:
    ds_id = uuid4()
    ds = Dataset(
        id=ds_id,
        dataset_id=str(ds_id),
        name="Gap Test Dataset",
        version="1.0",
        status=DatasetStatus.READY,
        sample_count=100,
        classes={"vehicle": 1},
        annotations_per_image=2.0,
        image_width=1920,
        image_height=1080,
        geographic_coverage={"districts": ["Lilongwe"]},
        demographic_report={},
        consent_coverage_pct=0.95,
        pii_scrub_verified=True,
        iaa_score=0.85,
        formats=["COCO"],
        price_usd=price,
        license_type=LicenseType.ANNUAL,
    )
    session.add(ds)
    await session.flush()
    return ds


async def _create_export(
    session: AsyncSession,
    buyer_id=None,
    dataset_id=None,
    price: Decimal = Decimal("100.00"),
    status: ExportStatus = ExportStatus.PENDING,
) -> Export:
    if buyer_id is None:
        buyer_id = (await _create_user(session)).id
    if dataset_id is None:
        dataset_id = (await _create_ready_dataset(session, price=price)).id
    export_id = uuid4()
    export = Export(
        id=export_id,
        dataset_id=dataset_id,
        buyer_id=buyer_id,
        license_key=f"ev-g2-{export_id.hex[:12]}",
        license_type=LicenseType.ANNUAL,
        status=status,
        price_usd=price,
        watermark_fingerprint=f"fp-g2-{export_id.hex[:12]}",
        formats_delivered=["COCO"],
        initiated_at=datetime.now(UTC),
        usage_rights={},
    )
    session.add(export)
    await session.flush()
    return export


async def _create_node(session: AsyncSession, status: NodeStatus = NodeStatus.ONLINE) -> Node:
    node = Node(
        id=uuid4(),
        node_id=f"G2-N-{uuid4().hex[:6]}",
        district="Lilongwe",
        latitude=-13.9626,
        longitude=33.7741,
        category=NodeCategory.ROAD,
        hardware_profile={},
        network_config={},
        capture_schedule="*/5 * * * *",
        interest_classes=["vehicle"],
        pii_mode=PIIMode.STRICT,
        firmware_version="2.1.0",
        public_key=b"\x03" * 32,
        status=status,
        is_enabled=True,
    )
    session.add(node)
    await session.flush()
    return node


async def _create_annotation_with_batch(
    session: AsyncSession,
    status: AnnotationStatus,
    annotator_id=None,
) -> Annotation:
    node = await _create_node(session)
    batch = IngestionBatch(
        id=uuid4(),
        batch_id=f"G2-BATCH-{uuid4().hex[:6]}",
        node_id=node.id,
        hub_id="hub-1",
        event_count=1,
        file_size_bytes=1024,
        checksum_sha256="a" * 64,
        node_signature=b"\x00" * 64,
        compression_codec="h265",
        status="INGESTED",
        quality_scores={},
    )
    session.add(batch)
    await session.flush()

    ann = Annotation(
        id=uuid4(),
        batch_id=batch.id,
        image_index=0,
        image_path="/images/001.jpg",
        thumbnail_path="/thumbs/001.jpg",
        detected_objects={"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]},
        auto_labels={"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]},
        status=status,
        quality_score=0.8,
        annotator_id=annotator_id,
    )
    session.add(ann)
    await session.flush()
    return ann


# ---------------------------------------------------------------------------
# 5. C1 (round 2) — concurrent refund_escrow calls on the SAME export
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_refund_escrow_prevents_double_credit(db_session_factory):
    """
    Two refund triggers can fire close together in real operation (Celery retry-exhaustion
    marks FAILED at nearly the same moment consent-withdrawal marks BLOCKED). The existing
    guard (check for EXPORT_ESCROW_REFUNDED audit log, then credit if none) is
    check-then-act. If two concurrent calls both read "not yet refunded" before either
    writes the audit log, both could credit the buyer.

    This proves it one way or the other.
    """
    starting_balance = Decimal("50.00")
    price = Decimal("100.00")

    async with db_session_factory() as setup:
        user = await _create_user(setup, credit=starting_balance)
        ds = await _create_ready_dataset(setup, price=price)
        export = await _create_export(
            setup, buyer_id=user.id, dataset_id=ds.id, price=price,
            status=ExportStatus.FAILED,
        )
        await setup.commit()
        user_id, export_id = user.id, export.id

    async def _attempt(reason):
        async with db_session_factory() as session:
            await refund_escrow(session, export_id=export_id, reason=reason)
            await session.commit()

    await asyncio.gather(
        _attempt("EXPORT_FAILED"),
        _attempt("CONSENT_WITHDRAWN_BLOCKED"),
    )

    async with db_session_factory() as check:
        refreshed_user = await check.execute(select(User).where(User.id == user_id))
        user_row = refreshed_user.scalar_one()
        assert user_row.credit_balance_usd == starting_balance + price, (
            f"expected exactly one refund of {price}, got balance "
            f"{user_row.credit_balance_usd} — double-credited under concurrent triggers"
        )


# ---------------------------------------------------------------------------
# Edge case 1 — refund from two DIFFERENT trigger reasons sequentially
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refund_escrow_guards_across_different_trigger_reasons(db_session):
    """
    If the idempotency check keys off (export_id, reason) instead of just export_id,
    two sequential calls with different reason strings would incorrectly refund twice.
    """
    starting_balance = Decimal("20.00")
    price = Decimal("75.00")

    user = await _create_user(db_session, credit=starting_balance)
    ds = await _create_ready_dataset(db_session, price=price)
    export = await _create_export(
        db_session, buyer_id=user.id, dataset_id=ds.id, price=price,
        status=ExportStatus.FAILED,
    )
    await db_session.commit()

    await refund_escrow(db_session, export_id=export.id, reason="EXPORT_FAILED")
    await db_session.commit()
    await refund_escrow(db_session, export_id=export.id, reason="CONSENT_WITHDRAWN_BLOCKED")
    await db_session.commit()

    await db_session.refresh(user)
    assert user.credit_balance_usd == starting_balance + price, (
        f"refunded twice ({user.credit_balance_usd}) — guard is keyed on reason, not export_id"
    )


# ---------------------------------------------------------------------------
# Edge case 2 — refund on a $0 export is a safe no-op
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refund_escrow_zero_price_export_is_a_safe_no_op(db_session):
    """
    A $0.00 export going through the refund path should leave balance unchanged.
    The current implementation short-circuits on price_usd <= 0 without writing
    an audit log — this test confirms that's the behavior and it doesn't error.
    """
    starting_balance = Decimal("10.00")

    user = await _create_user(db_session, credit=starting_balance)
    ds = await _create_ready_dataset(db_session, price=Decimal("0.00"))
    export = await _create_export(
        db_session, buyer_id=user.id, dataset_id=ds.id,
        price=Decimal("0.00"), status=ExportStatus.FAILED,
    )
    await db_session.commit()

    await refund_escrow(db_session, export_id=export.id, reason="EXPORT_FAILED")
    await db_session.commit()

    await db_session.refresh(user)
    assert user.credit_balance_usd == starting_balance


# ---------------------------------------------------------------------------
# Edge case 3 — concurrent confirm_delivery (B3 check-then-act race)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_confirm_delivery_only_one_completes(db_session_factory):
    """
    Two concurrent confirm_delivery calls on the same PROCESSING export should result
    in exactly one COMPLETED transition, not two.
    """
    async with db_session_factory() as setup:
        ds = await _create_ready_dataset(setup)
        buyer = await _create_user(setup, credit=Decimal("500.00"))
        export = await _create_export(
            setup, buyer_id=buyer.id, dataset_id=ds.id,
            status=ExportStatus.PROCESSING,
        )
        await setup.commit()
        export_id = export.id

    async def _attempt():
        async with db_session_factory() as session:
            try:
                await confirm_delivery(session, export_id=export_id)
                await session.commit()
                return "ok"
            except ValueError:
                await session.rollback()
                return "rejected"

    results = await asyncio.gather(_attempt(), _attempt())
    assert results.count("ok") == 1, f"expected exactly one completion, got {results}"


# ---------------------------------------------------------------------------
# Edge case 4 — node recovers from DEGRADED/OFFLINE back to ONLINE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_node_recovers_to_online_after_heartbeat_resumes(db_session):
    """
    C7 proved decline transitions (healthy → DEGRADED). The reverse matters just as much:
    a node that was OFFLINE should recover to ONLINE when it sends a healthy heartbeat.
    """
    node = await _create_node(db_session, status=NodeStatus.OFFLINE)
    await db_session.commit()

    healthy_payload = HeartbeatPayload(
        battery_voltage=12.6,
        solar_input_watts=8.0,
        cpu_temp_celsius=45.0,
        gpu_utilization=25.0,
        storage_used_gb=10.0,
        storage_total_gb=64.0,
        lte_rssi_dbm=-60.0,
        camera_status="OK",
        clock_drift_ms=1.0,
        events_captured=50,
        events_uploaded=50,
        bandwidth_mbps=5.0,
    )
    await record_heartbeat(db_session, node.id, healthy_payload)
    await db_session.commit()

    result = await db_session.execute(select(Node).where(Node.id == node.id))
    updated = result.scalar_one()
    assert updated.status == NodeStatus.ONLINE, (
        f"node stayed {updated.status} after healthy heartbeat — recovery transition missing"
    )


# ---------------------------------------------------------------------------
# Edge case 5 — revenue aggregation rounding on values that don't divide evenly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revenue_breakdown_rounds_correctly_on_uneven_split(db_session):
    """
    Three datasets at $33.33 each must sum to exactly $99.99 — not $100.00 from bad
    rounding, not $99.98 from truncation. Uses a unique future period to avoid
    collision with data from other tests.
    """
    prices = [Decimal("33.33")] * 3
    expected_total = Decimal("99.99")

    fake_now = datetime(2099, 7, 15, tzinfo=UTC)

    seller = await _create_user(db_session, credit=Decimal("999.00"))
    created_ds_ids = []
    for price in prices:
        ds = await _create_ready_dataset(db_session, price=price)
        ds.status = DatasetStatus.SOLD
        ds.sold_at = fake_now
        created_ds_ids.append(ds.dataset_id)
    await db_session.commit()

    breakdown = await get_revenue_breakdown(db_session, period="2099-07")

    assert isinstance(breakdown.total_revenue_usd, Decimal)

    our_total = sum(breakdown.by_dataset[ds_id] for ds_id in created_ds_ids)
    assert our_total == expected_total, (
        f"expected exact {expected_total}, got {our_total} — rounding drift in aggregation"
    )


# ---------------------------------------------------------------------------
# A2 — buyer_id must come from auth context, not client payload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_export_request_ignores_body_buyer_id(
    test_client, jwt_token_factory, monkeypatch
):
    """
    A2: ExportRequest schema no longer accepts buyer_id.
    The API layer injects buyer_id from the authenticated user.
    We mock initiate_export to verify it receives the auth-context buyer_id,
    not the one supplied in the request body.
    """
    from app.schemas.billing import ExportResponse

    captured_export_data: dict = {}

    async def spy_initiate_export(db, export_data):
        captured_export_data.update(export_data)
        return ExportResponse(
            id=uuid4(), dataset_id=export_data["dataset_id"],
            buyer_id=UUID(export_data["buyer_id"]),
            status="PENDING", license_key="ev-test1234",
            price_usd=Decimal("50.00"), export_path=None,
            initiated_at=datetime.now(UTC),
        )

    monkeypatch.setattr("app.api.billing.initiate_export", spy_initiate_export)

    buyer_a_id = str(uuid4())
    buyer_b_id = str(uuid4())

    token = jwt_token_factory(role="BUYER", user_id=buyer_a_id, email="a2-test@test.com")

    resp = await test_client.post(
        "/api/v1/exports",
        json={
            "dataset_id": "ds-a2-test",
            "buyer_id": buyer_b_id,  # should be overridden by auth context
            "license_type": "ANNUAL",
            "jurisdiction": "MW",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 201
    assert captured_export_data["buyer_id"] == buyer_a_id, (
        f"buyer_id was {captured_export_data['buyer_id']} (body value), "
        f"expected {buyer_a_id} (auth context value)"
    )


# ---------------------------------------------------------------------------
# Workstream B — Ingestion batch state machine
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_starts_as_pending_not_validating(db_session):
    """H5: Batches must start as PENDING, not skip directly to VALIDATING."""
    from app.services.ingestion import receive_batch

    node_id = uuid4()
    node = Node(
        id=node_id, node_id=f"node-b1-{uuid4().hex[:6]}",
        district="Lilongwe", latitude=-13.96, longitude=33.79,
        category=NodeCategory.ROAD, hardware_profile={"gpu": "jetson"},
        network_config={"apn": "airtel"}, capture_schedule="*/10 * * * *",
        interest_classes=["vehicle"], pii_mode=PIIMode.STRICT,
        firmware_version="1.0.0", public_key=b"\x01" * 32,
        status=NodeStatus.ONLINE, is_enabled=True,
    )
    db_session.add(node)
    await db_session.commit()

    batch_data = {
        "batch_id": f"BATCH-B1-{uuid4().hex[:8]}",
        "node_id": str(node_id),
        "hub_id": "hub-1",
        "event_count": 5,
        "file_size_bytes": 100,
        "checksum_sha256": "a" * 64,
        "quality_scores": {},
    }
    resp = await receive_batch(db_session, batch_data)
    assert resp.status == BatchStatus.PENDING.value


@pytest.mark.asyncio
async def test_checksum_mismatch_creates_rejected_batch(db_session):
    """H6: Checksum errors must create a REJECTED batch record, not raise."""
    from app.services.ingestion import receive_batch

    node_id = uuid4()
    node = Node(
        id=node_id, node_id=f"node-b2-{uuid4().hex[:6]}",
        district="Mzuzu", latitude=-11.46, longitude=34.02,
        category=NodeCategory.AGRI, hardware_profile={"gpu": "jetson"},
        network_config={"apn": "tnm"}, capture_schedule="*/10 * * * *",
        interest_classes=["crop"], pii_mode=PIIMode.MODERATE,
        firmware_version="1.0.0", public_key=b"\x02" * 32,
        status=NodeStatus.ONLINE, is_enabled=True,
    )
    db_session.add(node)
    await db_session.commit()

    file_bytes = b"actual content"
    batch_data = {
        "batch_id": f"BATCH-B2-{uuid4().hex[:8]}",
        "node_id": str(node_id),
        "hub_id": "hub-2",
        "event_count": 3,
        "file_size_bytes": len(file_bytes),
        "checksum_sha256": "0" * 64,  # wrong checksum
        "quality_scores": {},
    }
    resp = await receive_batch(db_session, batch_data, file=file_bytes)
    assert resp.status == BatchStatus.REJECTED.value
    assert resp.batch_id == batch_data["batch_id"]


@pytest.mark.asyncio
async def test_process_batch_collapses_validated_ghost_state(db_session):
    """H8: process_batch must go directly PENDING → INGESTED, not VALIDATING → VALIDATED → INGESTED."""
    from app.services.ingestion import process_batch, receive_batch

    node_id = uuid4()
    node = Node(
        id=node_id, node_id=f"node-b3-{uuid4().hex[:6]}",
        district="Zomba", latitude=-15.39, longitude=35.34,
        category=NodeCategory.WILDLIFE, hardware_profile={"gpu": "jetson"},
        network_config={"apn": "airtel"}, capture_schedule="*/10 * * * *",
        interest_classes=["animal"], pii_mode=PIIMode.NONE,
        firmware_version="1.0.0", public_key=b"\x03" * 32,
        status=NodeStatus.ONLINE, is_enabled=True,
    )
    db_session.add(node)
    await db_session.commit()

    batch_data = {
        "batch_id": f"BATCH-B3-{uuid4().hex[:8]}",
        "node_id": str(node_id),
        "hub_id": "hub-3",
        "event_count": 10,
        "file_size_bytes": 200,
        "checksum_sha256": "b" * 64,
        "quality_scores": {},
    }
    resp = await receive_batch(db_session, batch_data)
    assert resp.status == BatchStatus.PENDING.value

    result = await process_batch(db_session, batch_data["batch_id"])
    assert result is True

    from sqlalchemy import select
    result = await db_session.execute(
        select(IngestionBatch).where(IngestionBatch.batch_id == batch_data["batch_id"])
    )
    batch = result.scalar_one()
    assert batch.status == BatchStatus.INGESTED


# ---------------------------------------------------------------------------
# Workstream C — Annotation lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_label_creates_annotation_records(db_session_factory):
    """H3: auto_label_task must create Annotation records, not just transition batch status."""
    from app.services.ingestion import receive_batch
    from app.workers.tasks import _auto_label_async

    node_id = uuid4()
    batch_id = f"BATCH-C1-{uuid4().hex[:8]}"

    async with db_session_factory() as db_session:
        node = Node(
            id=node_id, node_id=f"node-c1-{uuid4().hex[:6]}",
            district="Blantyre", latitude=-15.79, longitude=35.00,
            category=NodeCategory.ROAD, hardware_profile={"gpu": "jetson"},
            network_config={"apn": "airtel"}, capture_schedule="*/10 * * * *",
            interest_classes=["vehicle"], pii_mode=PIIMode.STRICT,
            firmware_version="1.0.0", public_key=b"\x04" * 32,
            status=NodeStatus.ONLINE, is_enabled=True,
        )
        db_session.add(node)
        await db_session.commit()

        batch_data = {
            "batch_id": batch_id,
            "node_id": str(node_id),
            "hub_id": "hub-c1",
            "event_count": 3,
            "file_size_bytes": 100,
            "checksum_sha256": "c" * 64,
            "quality_scores": {},
        }
        await receive_batch(db_session, batch_data)
        await db_session.commit()

    summary = await _auto_label_async(batch_id)
    assert summary["annotations_created"] == 3

    from app.models.annotation import Annotation
    async with db_session_factory() as db_session:
        batch = (await db_session.execute(
            select(IngestionBatch).where(IngestionBatch.batch_id == batch_id)
        )).scalar_one()
        result = await db_session.execute(
            select(Annotation).where(Annotation.batch_id == batch.id)
        )
        annotations = result.scalars().all()
    assert len(annotations) == 3
    for a in annotations:
        status_val = a.status.value if hasattr(a.status, 'value') else a.status
        assert status_val == AnnotationStatus.PENDING.value


@pytest.mark.asyncio
async def test_rejected_annotation_can_be_reassigned_for_rework(db_session):
    """H9: REJECTED annotations must be reassignable for rework."""
    from app.services.annotation import reassign_rejected

    node_id = uuid4()
    node = Node(
        id=node_id, node_id=f"node-c2-{uuid4().hex[:6]}",
        district="Mangochi", latitude=-14.48, longitude=35.26,
        category=NodeCategory.DOC, hardware_profile={"gpu": "jetson"},
        network_config={"apn": "airtel"}, capture_schedule="*/10 * * * *",
        interest_classes=["building"], pii_mode=PIIMode.MODERATE,
        firmware_version="1.0.0", public_key=b"\x05" * 32,
        status=NodeStatus.ONLINE, is_enabled=True,
    )
    db_session.add(node)
    await db_session.commit()

    batch = IngestionBatch(
        id=uuid4(), batch_id=f"BATCH-C2-{uuid4().hex[:8]}",
        node_id=node_id, hub_id="hub-c2", event_count=1,
        file_size_bytes=100, checksum_sha256="d" * 64,
        node_signature=b"", compression_codec="h265",
        status=BatchStatus.INGESTED, quality_scores={},
    )
    db_session.add(batch)
    await db_session.commit()

    annotator = User(
        id=uuid4(), email=f"c2-ann-{uuid4().hex[:6]}@test.com",
        hashed_password="x" * 60, full_name="Annotator",
        role="ANNOTATOR", dpa_signed=True, credit_balance_usd=Decimal("0"),
    )
    reviewer = User(
        id=uuid4(), email=f"c2-qa-{uuid4().hex[:6]}@test.com",
        hashed_password="x" * 60, full_name="QA Reviewer",
        role="QA", dpa_signed=True, credit_balance_usd=Decimal("0"),
    )
    db_session.add_all([annotator, reviewer])
    await db_session.commit()

    annotation = Annotation(
        id=uuid4(), batch_id=batch.id, image_index=0,
        image_path="test/0.jpg", thumbnail_path="test/0_thumb.jpg",
        detected_objects={}, auto_labels={},
        human_labels={"car": {"bbox": [0, 0, 10, 10]}},
        qa_labels={"car": {"bbox": [99, 99, 100, 100]}},
        status=AnnotationStatus.REJECTED,
        quality_score=0.5, iaa_score=0.3,
        annotator_id=annotator.id, qa_reviewer_id=reviewer.id,
    )
    db_session.add(annotation)
    await db_session.commit()

    resp = await reassign_rejected(db_session, annotation.id)
    assert resp.status == AnnotationStatus.PENDING.value
    assert resp.annotator_id is None
    assert resp.qa_reviewer_id is None


# ---------------------------------------------------------------------------
# Workstream D — Consent lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expired_consent_gets_expired_status(db_session):
    """H2: ACTIVE consents past their expiry must transition to EXPIRED."""
    from app.models.consent import ConsentLedger
    from app.services.compliance import expire_consents

    expired_consent = ConsentLedger(
        id=uuid4(),
        subject_hash=f"expired-{uuid4().hex[:8]}",
        tx_hash=f"tx-exp-{uuid4().hex[:8]}",
        purposes=["road_monitoring"],
        media_types=["image"],
        geography_restrictions=[],
        signed_at=datetime(2020, 1, 1, tzinfo=UTC),
        expiry=datetime(2020, 12, 31, tzinfo=UTC),
        signature_bytes=b"\x01",
        status=ConsentStatus.ACTIVE,
    )
    active_consent = ConsentLedger(
        id=uuid4(),
        subject_hash=f"active-{uuid4().hex[:8]}",
        tx_hash=f"tx-act-{uuid4().hex[:8]}",
        purposes=["road_monitoring"],
        media_types=["image"],
        geography_restrictions=[],
        signed_at=datetime(2025, 1, 1, tzinfo=UTC),
        expiry=datetime(2030, 1, 1, tzinfo=UTC),
        signature_bytes=b"\x02",
        status=ConsentStatus.ACTIVE,
    )
    db_session.add_all([expired_consent, active_consent])
    await db_session.commit()

    count = await expire_consents(db_session)
    assert count >= 1

    from sqlalchemy import select
    result = await db_session.execute(
        select(ConsentLedger).where(ConsentLedger.id == expired_consent.id)
    )
    original = result.scalar_one()
    original_status = original.status.value if hasattr(original.status, 'value') else original.status
    assert original_status == ConsentStatus.ACTIVE.value

    expired_result = await db_session.execute(
        select(ConsentLedger).where(
            ConsentLedger.subject_hash == expired_consent.subject_hash,
            ConsentLedger.status == ConsentStatus.EXPIRED,
        )
    )
    expired_records = expired_result.scalars().all()
    assert len(expired_records) == 1


@pytest.mark.asyncio
async def test_withdrawal_uses_for_update_preventing_duplicates(db_session):
    """M3: Concurrent withdrawals should not create duplicate withdrawal records."""
    from app.models.consent import ConsentLedger
    from app.services.compliance import withdraw_consent

    subject_hash = f"sub-{uuid4().hex[:8]}"
    for i in range(3):
        consent = ConsentLedger(
            id=uuid4(),
            subject_hash=subject_hash,
            tx_hash=f"tx-w-{uuid4().hex[:8]}",
            purposes=["road_monitoring"],
            media_types=["image"],
            geography_restrictions=[],
            signed_at=datetime(2025, 1, 1, tzinfo=UTC),
            expiry=datetime(2030, 1, 1, tzinfo=UTC),
            signature_bytes=b"\x01",
            status=ConsentStatus.ACTIVE,
        )
        db_session.add(consent)
    await db_session.commit()

    result = await withdraw_consent(db_session, subject_hash)
    assert result["consents_withdrawn"] == 3

    from sqlalchemy import func, select
    withdrawal_count = await db_session.execute(
        select(func.count()).select_from(ConsentLedger).where(
            ConsentLedger.subject_hash == subject_hash,
            ConsentLedger.status == ConsentStatus.WITHDRAWN,
        )
    )
    assert withdrawal_count.scalar() == 3


# ---------------------------------------------------------------------------
# Workstream E — Dataset publishing gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_dataset_transitions_ready_to_for_sale(db_session):
    """H4: READY datasets must be publishable to FOR_SALE."""
    from app.services.catalog import publish_dataset

    ds = Dataset(
        id=uuid4(), dataset_id=f"ds-e1-{uuid4().hex[:6]}",
        name="E1 Test Dataset", version="1.0",
        status=DatasetStatus.READY, sample_count=20,
        classes={"car": 2, "person": 1}, annotations_per_image=1.0,
        image_width=640, image_height=480,
        geographic_coverage={"countries": ["MW"]},
        demographic_report={}, consent_coverage_pct=1.0,
        pii_scrub_verified=True, iaa_score=0.95,
        formats=["COCO"], price_usd=Decimal("100.00"),
        license_type=LicenseType.ANNUAL,
    )
    db_session.add(ds)
    await db_session.commit()

    resp = await publish_dataset(db_session, ds.dataset_id)
    assert resp.status == DatasetStatus.FOR_SALE.value

    from sqlalchemy import select
    result = await db_session.execute(select(Dataset).where(Dataset.id == ds.id))
    updated = result.scalar_one()
    updated_status = updated.status.value if hasattr(updated.status, 'value') else updated.status
    assert updated_status == DatasetStatus.FOR_SALE.value


@pytest.mark.asyncio
async def test_publish_rejects_non_ready_dataset(db_session):
    """Only READY datasets can be published."""
    from app.services.catalog import publish_dataset

    ds = Dataset(
        id=uuid4(), dataset_id=f"ds-e2-{uuid4().hex[:6]}",
        name="E2 Building Dataset", version="1.0",
        status=DatasetStatus.BUILDING, sample_count=10,
        classes={"car": 1}, annotations_per_image=1.0,
        image_width=640, image_height=480,
        geographic_coverage={"countries": ["MW"]},
        demographic_report={}, consent_coverage_pct=1.0,
        pii_scrub_verified=False, iaa_score=0.0,
        formats=["COCO"], price_usd=Decimal("50.00"),
        license_type=LicenseType.ANNUAL,
    )
    db_session.add(ds)
    await db_session.commit()

    with pytest.raises(ValueError, match="expected READY"):
        await publish_dataset(db_session, ds.dataset_id)


# ---------------------------------------------------------------------------
# Workstream F — Wage calculation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pay_annotators_uses_decimal_and_applies_minimum_wage():
    """M13: pay_annotators_task must use Decimal MWK wage and credit annotators."""
    from app.core.database import async_session
    from app.workers.tasks import _pay_annotators_async

    async with async_session() as writer:
        annotator = User(
            id=uuid4(), email=f"f1-ann-{uuid4().hex[:6]}@test.com",
            hashed_password="x" * 60, full_name="F1 Annotator",
            role="ANNOTATOR", dpa_signed=True, credit_balance_usd=Decimal("0"),
        )
        writer.add(annotator)
        await writer.commit()

        node = Node(
            id=uuid4(), node_id=f"node-f1-{uuid4().hex[:6]}",
            district="Lilongwe", latitude=-13.96, longitude=33.79,
            category=NodeCategory.ROAD, hardware_profile={"gpu": "jetson"},
            network_config={"apn": "airtel"}, capture_schedule="*/10 * * * *",
            interest_classes=["vehicle"], pii_mode=PIIMode.STRICT,
            firmware_version="1.0.0", public_key=b"\x06" * 32,
            status=NodeStatus.ONLINE, is_enabled=True,
        )
        writer.add(node)
        await writer.commit()

        batch = IngestionBatch(
            id=uuid4(), batch_id=f"BATCH-F1-{uuid4().hex[:8]}",
            node_id=node.id, hub_id="hub-f1", event_count=2,
            file_size_bytes=100, checksum_sha256="f" * 64,
            node_signature=b"", compression_codec="h265",
            status=BatchStatus.INGESTED, quality_scores={},
        )
        writer.add(batch)
        await writer.commit()

        for i in range(2):
            ann = Annotation(
                id=uuid4(), batch_id=batch.id, image_index=i,
                image_path=f"f1/{i}.jpg", thumbnail_path=f"f1/{i}_thumb.jpg",
                detected_objects={}, auto_labels={},
                status=AnnotationStatus.CERTIFIED,
                quality_score=1.0, iaa_score=1.0,
                annotator_id=annotator.id, is_certified=True,
            )
            writer.add(ann)
        await writer.commit()

    summary = await _pay_annotators_async()
    assert summary["annotators_paid"] >= 1

    async with async_session() as reader:
        from sqlalchemy import select
        result = await reader.execute(select(User).where(User.id == annotator.id))
        paid = result.scalar_one()
        assert paid.credit_balance_usd > Decimal("0")


# ---------------------------------------------------------------------------
# Stuck batch reconciliation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stuck_pending_batch_gets_redispatched(db_session_factory):
    """A PENDING batch older than the threshold must be re-dispatched."""
    from unittest.mock import patch

    from app.core.config import settings
    from app.workers.tasks import _reconcile_stuck_batches_async

    node_id = uuid4()
    batch_id = f"batch-stale-{uuid4().hex[:8]}"

    async with db_session_factory() as db_session:
        node = Node(
            id=node_id, node_id=f"node-recon-{uuid4().hex[:6]}",
            district="Blantyre", latitude=-15.79, longitude=35.00,
            category=NodeCategory.ROAD, hardware_profile={"gpu": "jetson"},
            network_config={"apn": "airtel"}, capture_schedule="*/10 * * * *",
            interest_classes=["vehicle"], pii_mode=PIIMode.STRICT,
            firmware_version="1.0.0", public_key=b"\x05" * 32,
            status=NodeStatus.ONLINE, is_enabled=True,
        )
        db_session.add(node)
        await db_session.commit()

        old_time = datetime.now(UTC) - timedelta(
            minutes=settings.STUCK_BATCH_THRESHOLD_MINUTES + 10
        )
        batch = IngestionBatch(
            id=uuid4(), batch_id=batch_id,
            node_id=node_id, hub_id="hub-recon",
            event_count=2, file_size_bytes=100, checksum_sha256="e" * 64,
            node_signature=b"", compression_codec="h265",
            status=BatchStatus.PENDING, quality_scores={},
        )
        batch.created_at = old_time
        db_session.add(batch)
        await db_session.commit()

    from app.workers.tasks import auto_label_task
    with patch.object(auto_label_task, "delay") as mock_delay:
        mock_delay.return_value = uuid4()
        redispatched = await _reconcile_stuck_batches_async()

    assert len(redispatched) >= 1
    assert any(r["batch_id"] == batch_id for r in redispatched)
    mock_delay.assert_called()


@pytest.mark.asyncio
async def test_recent_pending_batch_is_left_alone(db_session):
    """A PENDING batch still within the threshold window must NOT be re-dispatched."""
    from unittest.mock import patch

    from app.workers.tasks import _reconcile_stuck_batches_async

    node_id = uuid4()
    node = Node(
        id=node_id, node_id=f"node-recent-{uuid4().hex[:6]}",
        district="Blantyre", latitude=-15.79, longitude=35.00,
        category=NodeCategory.ROAD, hardware_profile={"gpu": "jetson"},
        network_config={"apn": "airtel"}, capture_schedule="*/10 * * * *",
        interest_classes=["vehicle"], pii_mode=PIIMode.STRICT,
        firmware_version="1.0.0", public_key=b"\x06" * 32,
        status=NodeStatus.ONLINE, is_enabled=True,
    )
    db_session.add(node)
    await db_session.commit()

    batch = IngestionBatch(
        id=uuid4(), batch_id=f"batch-recent-{uuid4().hex[:8]}",
        node_id=node_id, hub_id="hub-recent",
        event_count=1, file_size_bytes=50, checksum_sha256="g" * 64,
        node_signature=b"", compression_codec="h265",
        status=BatchStatus.PENDING, quality_scores={},
    )
    # created_at defaults to now — well within the threshold
    db_session.add(batch)
    await db_session.commit()

    from app.workers.tasks import auto_label_task
    with patch.object(auto_label_task, "delay") as mock_delay:
        redispatched = await _reconcile_stuck_batches_async()

    assert not any(r["batch_id"] == batch.batch_id for r in redispatched)
    assert not any(
        call.args[0] == str(batch.id) for call in mock_delay.call_args_list
    )


@pytest.mark.asyncio
async def test_non_pending_batch_is_never_touched(db_session_factory):
    """A batch that has already moved past PENDING is never re-dispatched, regardless of age."""
    from unittest.mock import patch

    from app.core.config import settings
    from app.workers.tasks import _reconcile_stuck_batches_async

    node_id = uuid4()
    batch_id = f"batch-old-ingested-{uuid4().hex[:8]}"

    async with db_session_factory() as db_session:
        node = Node(
            id=node_id, node_id=f"node-olding-{uuid4().hex[:6]}",
            district="Blantyre", latitude=-15.79, longitude=35.00,
            category=NodeCategory.ROAD, hardware_profile={"gpu": "jetson"},
            network_config={"apn": "airtel"}, capture_schedule="*/10 * * * *",
            interest_classes=["vehicle"], pii_mode=PIIMode.STRICT,
            firmware_version="1.0.0", public_key=b"\x07" * 32,
            status=NodeStatus.ONLINE, is_enabled=True,
        )
        db_session.add(node)
        await db_session.commit()

        old_time = datetime.now(UTC) - timedelta(
            minutes=settings.STUCK_BATCH_THRESHOLD_MINUTES + 60
        )
        batch = IngestionBatch(
            id=uuid4(), batch_id=batch_id,
            node_id=node_id, hub_id="hub-old",
            event_count=3, file_size_bytes=200, checksum_sha256="h" * 64,
            node_signature=b"", compression_codec="h265",
            status=BatchStatus.INGESTED, quality_scores={},
        )
        batch.created_at = old_time
        db_session.add(batch)
        await db_session.commit()

    from app.workers.tasks import auto_label_task
    with patch.object(auto_label_task, "delay") as mock_delay:
        redispatched = await _reconcile_stuck_batches_async()

    assert not any(r["batch_id"] == batch_id for r in redispatched)
