from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.buyer import User
from app.models.dataset import Dataset
from app.models.enums import ExportStatus, LicenseType
from app.models.export import Export
from app.schemas.billing import ExportResponse, RevenueBreakdown

logger = logging.getLogger(__name__)


async def refund_escrow(db: AsyncSession, export_id: UUID, reason: str) -> None:
    """Refund the escrowed credit to the buyer when an export fails or is blocked.

    This restores the buyer's credit_balance_usd to the pre-deduction amount.
    The caller must have already loaded the Export row (ideally with FOR UPDATE).
    Idempotent: calling twice for the same export is safe (no double-refund).
    """
    result = await db.execute(
        select(Export).where(Export.id == export_id).with_for_update()
    )
    export = result.scalar_one_or_none()
    if export is None:
        logger.error("refund_escrow called for non-existent export %s", export_id)
        return

    if export.price_usd <= 0:
        return

    # Idempotency guard: check if already refunded
    existing_refund = await db.execute(
        select(AuditLog).where(
            AuditLog.event_type == "EXPORT_ESCROW_REFUNDED",
            AuditLog.resource_type == "export",
            AuditLog.resource_id == export_id,
        ).limit(1)
    )
    if existing_refund.scalar_one_or_none() is not None:
        logger.info("refund_escrow: export %s already refunded, skipping", export_id)
        return

    # Lock the buyer row to prevent TOCTOU
    user_result = await db.execute(
        select(User).where(User.id == export.buyer_id).with_for_update()
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        logger.error("refund_escrow: buyer %s not found for export %s", export.buyer_id, export_id)
        return

    user.credit_balance_usd += export.price_usd

    audit = AuditLog(
        event_type="EXPORT_ESCROW_REFUNDED",
        severity="INFO",
        resource_type="export",
        resource_id=export_id,
        details={
            "buyer_id": str(export.buyer_id),
            "amount_usd": str(export.price_usd),
            "reason": reason,
        },
        actor_type="SYSTEM",
    )
    db.add(audit)
    logger.info(
        "Refunded $%s to buyer %s for export %s: %s",
        export.price_usd, export.buyer_id, export_id, reason,
    )


async def initiate_export(db: AsyncSession, export_data: dict) -> ExportResponse:
    buyer_id = UUID(export_data["buyer_id"])
    dataset_id = export_data["dataset_id"]

    ready, message = await verify_buyer_ready(db, buyer_id, dataset_id)
    if not ready:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=message,
        )

    # Get dataset for pricing
    ds_result = await db.execute(select(Dataset).where(Dataset.dataset_id == dataset_id))
    dataset = ds_result.scalar_one_or_none()

    # Hold payment in escrow (deduct from buyer credit)
    # FOR UPDATE locks the row to prevent concurrent double-deduction (TOCTOU)
    user_result = await db.execute(
        select(User).where(User.id == buyer_id).with_for_update()
    )
    user = user_result.scalar_one_or_none()

    price = dataset.price_usd if dataset else Decimal("0.00")
    if user.credit_balance_usd < price:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credit: have ${user.credit_balance_usd}, need ${price}",
        )

    user.credit_balance_usd -= price

    export_id = uuid4()
    license_key = f"ev-{export_id.hex[:16]}"

    export = Export(
        id=export_id,
        dataset_id=UUID(dataset_id) if isinstance(dataset_id, str) else dataset_id,
        buyer_id=buyer_id,
        license_key=license_key,
        license_type=LicenseType(export_data.get("license_type", "ANNUAL")),
        status=ExportStatus.PENDING,
        price_usd=price,
        watermark_fingerprint=f"fp-{export_id.hex[:24]}",
        formats_delivered=export_data.get("formats", ["COCO", "YOLO"]),
        initiated_at=datetime.now(UTC),
        usage_rights=export_data.get("usage_rights", {}),
    )
    db.add(export)

    # Log the export initiation
    audit_log = AuditLog(
        event_type="EXPORT_INITIATED",
        severity="INFO",
        resource_type="export",
        resource_id=export_id,
        details={
            "buyer_id": str(buyer_id),
            "dataset_id": dataset_id,
            "price_usd": str(price),
            "license_key": license_key,
        },
        actor_type="USER",
        actor_id=buyer_id,
    )
    db.add(audit_log)

    await db.commit()

    return ExportResponse(
        id=export_id,
        dataset_id=dataset_id,
        buyer_id=buyer_id,
        status=ExportStatus.PENDING.value,
        license_key=license_key,
        price_usd=price,
        export_path=None,
        initiated_at=datetime.now(UTC),
    )


async def verify_buyer_ready(
    db: AsyncSession, buyer_id: UUID, dataset_id: str
) -> tuple[bool, str]:
    user_result = await db.execute(select(User).where(User.id == buyer_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return False, "Buyer not found"

    if not user.dpa_signed:
        return False, "DPA not signed"

    if user.credit_balance_usd <= 0:
        return False, "Insufficient credit balance"

    ds_result = await db.execute(
        select(Dataset).where(Dataset.dataset_id == dataset_id)
    )
    dataset = ds_result.scalar_one_or_none()
    if dataset is None:
        return False, "Dataset not found"

    ds_status = dataset.status.value if hasattr(dataset.status, 'value') else dataset.status
    if ds_status != "FOR_SALE":
        return False, f"Dataset status is {ds_status}, expected FOR_SALE"

    return True, "Buyer ready for export"


async def confirm_delivery(db: AsyncSession, export_id: UUID) -> bool:
    from app.models.export import Export

    result = await db.execute(
        select(Export).where(Export.id == export_id).with_for_update()
    )
    export = result.scalar_one_or_none()
    if export is None:
        return False

    # Only PENDING/PROCESSING exports can be confirmed as delivered
    current_status = export.status.value if hasattr(export.status, "value") else export.status
    if current_status not in ("PENDING", "PROCESSING"):
        raise ValueError(
            f"Cannot confirm delivery for export in {current_status} status"
        )

    export.status = ExportStatus.COMPLETED
    export.completed_at = datetime.now(UTC)
    export.delivery_confirmed = True

    # Mark dataset as SOLD so revenue tracking works (A5)
    ds_result = await db.execute(
        select(Dataset).where(Dataset.id == export.dataset_id).with_for_update()
    )
    dataset = ds_result.scalar_one_or_none()
    if dataset:
        from app.models.enums import DatasetStatus
        dataset.status = DatasetStatus.SOLD
        dataset.sold_at = datetime.now(UTC)

    # Log delivery
    audit_log = AuditLog(
        event_type="EXPORT_DELIVERED",
        severity="INFO",
        resource_type="export",
        resource_id=export_id,
        details={"license_key": export.license_key},
        actor_type="SYSTEM",
    )
    db.add(audit_log)

    await db.commit()
    return True


async def get_revenue_breakdown(
    db: AsyncSession, period: str | None = None
) -> RevenueBreakdown:
    from datetime import timedelta

    if period is None:
        period = datetime.now(UTC).strftime("%Y-%m")

    # Parse period and create date range
    try:
        year, month = map(int, period.split("-"))
        start_date = datetime(year, month, 1, tzinfo=UTC)
        end_date = datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12 else datetime(year, month + 1, 1, tzinfo=UTC)
    except (ValueError, TypeError):
        start_date = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=32)
        end_date = end_date.replace(day=1)

    result = await db.execute(
        select(Dataset).where(
            Dataset.price_usd > 0,
            Dataset.sold_at >= start_date,
            Dataset.sold_at < end_date,
        )
    )
    datasets = result.scalars().all()

    total_revenue = Decimal("0.00")
    by_dataset: dict[str, Decimal] = {}
    by_license: dict[str, Decimal] = {}
    export_count = 0

    for ds in datasets:
        price = ds.price_usd
        total_revenue += price
        by_dataset[ds.dataset_id] = by_dataset.get(ds.dataset_id, Decimal("0.00")) + price
        lic = ds.license_type.value if hasattr(ds.license_type, "value") else ds.license_type
        by_license[lic] = by_license.get(lic, Decimal("0.00")) + price
        if ds.sold_at:
            export_count += 1

    return RevenueBreakdown(
        period=period,
        total_revenue_usd=total_revenue,
        by_dataset=by_dataset,
        by_license_type=by_license,
        monthly_trend=[],
        export_count=export_count,
    )


MAX_WEBHOOK_RETRIES = 3
WEBHOOK_TIMEOUT_SECONDS = 10


async def send_buyer_notification(
    db: AsyncSession,
    buyer_id: UUID,
    event_type: str,
    details: dict,
) -> dict:
    """Send webhook notification to a buyer with retry and audit logging.

    Returns a dict with notification result including attempts made.
    """
    user_result = await db.execute(select(User).where(User.id == buyer_id))
    user = user_result.scalar_one_or_none()

    webhook_url = getattr(user, "webhook_url", None) if user else None

    notification_id = uuid4()
    attempts = 0
    last_error = None
    delivered = False

    if not webhook_url:
        logger.info("No webhook_url for buyer %s, skipping notification", buyer_id)
        audit = AuditLog(
            event_type="BUYER_NOTIFICATION_SKIPPED",
            severity="INFO",
            resource_type="notification",
            resource_id=notification_id,
            details={
                "buyer_id": str(buyer_id),
                "event_type": event_type,
                "reason": "no_webhook_url",
            },
            actor_type="SYSTEM",
        )
        db.add(audit)
        await db.commit()
        return {
            "notification_id": str(notification_id),
            "delivered": False,
            "attempts": 0,
            "reason": "no_webhook_url",
        }

    payload = {
        "notification_id": str(notification_id),
        "event_type": event_type,
        "buyer_id": str(buyer_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "details": details,
    }

    for attempt in range(1, MAX_WEBHOOK_RETRIES + 1):
        attempts = attempt
        try:
            async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
                resp = await client.post(webhook_url, json=payload)
                if resp.status_code < 300:
                    delivered = True
                    break
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:
            last_error = str(exc)[:200]

        if attempt < MAX_WEBHOOK_RETRIES:
            await asyncio.sleep(0.1 * (2 ** (attempt - 1)))

    severity = "INFO" if delivered else "WARNING"
    audit = AuditLog(
        event_type="BUYER_NOTIFICATION_SENT" if delivered else "BUYER_NOTIFICATION_FAILED",
        severity=severity,
        resource_type="notification",
        resource_id=notification_id,
        details={
            "buyer_id": str(buyer_id),
            "event_type": event_type,
            "webhook_url": webhook_url,
            "attempts": attempts,
            "delivered": delivered,
            "last_error": last_error,
        },
        actor_type="SYSTEM",
    )
    db.add(audit)
    await db.commit()

    return {
        "notification_id": str(notification_id),
        "delivered": delivered,
        "attempts": attempts,
        "last_error": last_error,
    }
