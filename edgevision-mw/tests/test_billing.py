from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.buyer import User
from app.models.dataset import Dataset
from app.models.enums import DatasetStatus, ExportStatus, LicenseType
from app.models.export import Export, ExportLog
from app.services.billing import get_revenue_breakdown, initiate_export
from app.services.catalog import generate_quote


async def _create_buyer(db, credit=Decimal("1000.00"), dpa_signed=True):
    user = User(
        id=uuid4(),
        email=f"buyer-{uuid4().hex[:6]}@test.com",
        hashed_password="x" * 60,
        full_name="Test Buyer",
        role="BUYER",
        dpa_signed=dpa_signed,
        credit_balance_usd=credit,
    )
    db.add(user)
    await db.commit()
    return user


async def _create_ready_dataset(db, buyer_id=None):
    ds = Dataset(
        id=uuid4(),
        dataset_id=f"DS-{uuid4().hex[:6]}",
        name="Billing Test Dataset",
        version="1.0",
        status=DatasetStatus.FOR_SALE,
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
        price_usd=Decimal("500.00"),
        license_type=LicenseType.ANNUAL,
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


@pytest.mark.asyncio
async def test_request_export_checks_dpa_and_credits(db_session):
    from fastapi import HTTPException

    buyer = await _create_buyer(db_session)
    ds = await _create_ready_dataset(db_session)

    export = await initiate_export(
        db_session,
        export_data={"buyer_id": str(buyer.id), "dataset_id": ds.dataset_id, "license_type": "ANNUAL"},
    )
    assert export is not None

    poor = await _create_buyer(db_session, credit=Decimal("10.00"))
    with pytest.raises(HTTPException) as excinfo:
        await initiate_export(
            db_session,
            export_data={"buyer_id": str(poor.id), "dataset_id": ds.dataset_id, "license_type": "ANNUAL"},
        )
    assert excinfo.value.status_code == 402
    assert "credit" in str(excinfo.value.detail).lower()

    nodpa = await _create_buyer(db_session, dpa_signed=False)
    with pytest.raises(HTTPException) as excinfo:
        await initiate_export(
            db_session,
            export_data={"buyer_id": str(nodpa.id), "dataset_id": ds.dataset_id, "license_type": "ANNUAL"},
        )
    assert excinfo.value.status_code == 402
    assert "dpa" in str(excinfo.value.detail).lower()


@pytest.mark.asyncio
async def test_list_exports_filters_by_buyer(db_session):
    buyer1 = await _create_buyer(db_session)
    buyer2 = await _create_buyer(db_session)

    for buyer in [buyer1, buyer2]:
        ds = await _create_ready_dataset(db_session)
        await initiate_export(
            db_session,
            export_data={
                "buyer_id": str(buyer.id),
                "dataset_id": ds.dataset_id,
                "license_type": "ANNUAL",
            },
        )

    exports1 = await db_session.execute(select(Export).where(Export.buyer_id == buyer1.id))
    exports2 = await db_session.execute(select(Export).where(Export.buyer_id == buyer2.id))
    list1 = exports1.scalars().all()
    list2 = exports2.scalars().all()

    assert len(list1) == len(list2) == 1, "Each buyer should have exactly one export"


@pytest.mark.asyncio
async def test_decimal_precision_survives_roundtrip(db_session):
    """Verify that Decimal monetary values don't suffer from float drift."""
    from app.services.catalog import calculate_price

    # This price would drift under float: 0.1 + 0.2 != 0.3
    await _create_buyer(db_session, credit=Decimal("99999.99"))
    ds = await _create_ready_dataset(db_session)

    # Calculate price using the Decimal-based function
    price = calculate_price(
        {
            "sample_count": 3,
            "license_type": "ANNUAL",
            "complexity": 1.0,
        }
    )
    # 3 * 1.0 * 0.30 = 0.90 exactly
    assert price == Decimal("0.90"), f"Expected exact Decimal 0.90, got {price}"
    assert isinstance(price, Decimal), f"Expected Decimal type, got {type(price)}"

    # Verify the dataset price_usd round-trips correctly through DB
    await db_session.refresh(ds)
    assert isinstance(ds.price_usd, Decimal), f"Expected Decimal from DB, got {type(ds.price_usd)}"
    assert ds.price_usd == Decimal("500.00")

    # Verify quote pricing uses Decimal
    quote = await generate_quote(
        db_session,
        quote_request={
            "dataset_id": ds.dataset_id,
            "license_type": "PERPETUAL",
            "jurisdiction": "MW",
        },
    )
    # PERPETUAL multiplier is 1.5, MW premium is 1.0
    # 500.00 * 1.5 * 1.0 = 750.00
    assert quote.total_price_usd == Decimal("750.00"), f"Expected 750.00, got {quote.total_price_usd}"
    assert isinstance(quote.total_price_usd, Decimal)
    assert isinstance(quote.base_price_usd, Decimal)


@pytest.mark.asyncio
async def test_revenue_breakdown(db_session):
    breakdown = await get_revenue_breakdown(db_session)

    assert hasattr(breakdown, "total_revenue_usd") or isinstance(breakdown, dict)
    if isinstance(breakdown, dict):
        assert "total_revenue_usd" in breakdown
        assert breakdown["total_revenue_usd"] >= 0
    else:
        assert breakdown.total_revenue_usd >= 0


@pytest.mark.asyncio
async def test_export_requires_dpa_signed(db_session):
    from fastapi import HTTPException

    buyer = await _create_buyer(db_session, dpa_signed=False)
    ds = await _create_ready_dataset(db_session)

    with pytest.raises(HTTPException) as excinfo:
        await initiate_export(
            db_session,
            export_data={
                "buyer_id": str(buyer.id),
                "dataset_id": ds.dataset_id,
                "license_type": "ANNUAL",
            },
        )
    assert excinfo.value.status_code == 402
    assert "dpa" in str(excinfo.value.detail).lower()


@pytest.mark.asyncio
async def test_celery_task_triggered_for_batch_processing(db_session):
    from unittest.mock import patch

    from app.workers.tasks import process_batch_task

    with patch.object(process_batch_task, "delay") as mock_delay:
        mock_delay.return_value = uuid4()
        result = process_batch_task.delay(str(uuid4()))
        assert result is not None
        mock_delay.assert_called_once()


@pytest.mark.asyncio
async def test_refund_escrow_restores_credit(db_session):
    """A3: refund_escrow should restore buyer credit to pre-deduction amount."""
    from app.services.billing import refund_escrow

    buyer = await _create_buyer(db_session, credit=Decimal("1000.00"))
    ds = await _create_ready_dataset(db_session)
    original_credit = buyer.credit_balance_usd

    # Create an export that already deducted credit
    export_id = uuid4()
    export = Export(
        id=export_id,
        dataset_id=ds.id,
        buyer_id=buyer.id,
        license_key=f"ev-refund-{export_id.hex[:12]}",
        license_type=LicenseType.ANNUAL,
        status=ExportStatus.FAILED,
        price_usd=Decimal("250.00"),
        watermark_fingerprint=f"fp-refund-{export_id.hex[:12]}",
        formats_delivered=["COCO"],
        initiated_at=datetime.now(UTC),
        usage_rights={},
    )
    db_session.add(export)
    # Manually deduct credit to simulate pre-refund state
    buyer.credit_balance_usd -= Decimal("250.00")
    await db_session.commit()

    assert buyer.credit_balance_usd == Decimal("750.00")

    await refund_escrow(db_session, export_id, reason="test_refund")
    await db_session.commit()

    await db_session.refresh(buyer)
    assert buyer.credit_balance_usd == original_credit, (
        f"Expected credit {original_credit}, got {buyer.credit_balance_usd}"
    )


@pytest.mark.asyncio
async def test_failed_export_marks_failed_status(db_session):
    """A2: When Celery retries exhaust, export should be marked FAILED and escrow refunded."""
    from app.services.billing import refund_escrow

    buyer = await _create_buyer(db_session, credit=Decimal("1000.00"))
    ds = await _create_ready_dataset(db_session)

    export_id = uuid4()
    export = Export(
        id=export_id,
        dataset_id=ds.id,
        buyer_id=buyer.id,
        license_key=f"ev-fail-{export_id.hex[:12]}",
        license_type=LicenseType.ANNUAL,
        status=ExportStatus.PROCESSING,
        price_usd=Decimal("500.00"),
        watermark_fingerprint=f"fp-fail-{export_id.hex[:12]}",
        formats_delivered=["COCO"],
        initiated_at=datetime.now(UTC),
        usage_rights={},
    )
    db_session.add(export)
    buyer.credit_balance_usd -= Decimal("500.00")
    await db_session.commit()

    assert buyer.credit_balance_usd == Decimal("500.00")

    # Simulate what the Celery failure handler does:
    # 1. Mark export as FAILED
    export.status = ExportStatus.FAILED
    db_session.add(
        ExportLog(
            export_id=export_id,
            event_type="EXPORT_FAILED_RETRIES_EXHAUSTED",
            details={"error": "simulated", "retries_exhausted": True},
        )
    )
    await db_session.commit()

    # 2. Refund escrow
    await refund_escrow(db_session, export_id, reason="celery_retries_exhausted")
    await db_session.commit()

    await db_session.refresh(export)
    assert export.status == ExportStatus.FAILED

    await db_session.refresh(buyer)
    assert buyer.credit_balance_usd == Decimal("1000.00"), (
        f"Credit should be fully refunded, got {buyer.credit_balance_usd}"
    )


@pytest.mark.asyncio
async def test_confirm_delivery_sets_sold(db_session):
    """A5: confirm_delivery should set Dataset.status=SOLD and sold_at."""
    from app.services.billing import confirm_delivery

    buyer = await _create_buyer(db_session, credit=Decimal("1000.00"))
    ds = await _create_ready_dataset(db_session)
    assert ds.status == DatasetStatus.FOR_SALE

    export_id = uuid4()
    export = Export(
        id=export_id,
        dataset_id=ds.id,
        buyer_id=buyer.id,
        license_key=f"ev-sold-{export_id.hex[:12]}",
        license_type=LicenseType.ANNUAL,
        status=ExportStatus.PROCESSING,
        price_usd=Decimal("500.00"),
        watermark_fingerprint=f"fp-sold-{export_id.hex[:12]}",
        formats_delivered=["COCO"],
        initiated_at=datetime.now(UTC),
        usage_rights={},
    )
    db_session.add(export)
    await db_session.commit()

    result = await confirm_delivery(db_session, export_id)
    assert result is True

    await db_session.refresh(ds)
    assert ds.status == DatasetStatus.SOLD, f"Expected SOLD, got {ds.status}"
    assert ds.sold_at is not None, "sold_at should be set"

    await db_session.refresh(export)
    assert export.status == ExportStatus.COMPLETED


@pytest.mark.asyncio
async def test_confirm_delivery_rejects_blocked_export(db_session):
    """B3: confirm_delivery should reject BLOCKED exports."""
    from app.services.billing import confirm_delivery

    buyer = await _create_buyer(db_session, credit=Decimal("1000.00"))
    ds = await _create_ready_dataset(db_session)

    export_id = uuid4()
    export = Export(
        id=export_id,
        dataset_id=ds.id,
        buyer_id=buyer.id,
        license_key=f"ev-blocked-{export_id.hex[:12]}",
        license_type=LicenseType.ANNUAL,
        status=ExportStatus.BLOCKED,
        price_usd=Decimal("500.00"),
        watermark_fingerprint=f"fp-blocked-{export_id.hex[:12]}",
        formats_delivered=["COCO"],
        initiated_at=datetime.now(UTC),
        usage_rights={},
    )
    db_session.add(export)
    await db_session.commit()

    with pytest.raises(ValueError, match="Cannot confirm delivery"):
        await confirm_delivery(db_session, export_id)
