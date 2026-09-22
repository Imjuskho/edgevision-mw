from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.logging import get_logger
from app.core.security import create_access_token
from app.models.annotation import Annotation
from app.models.node import Node
from app.models.operator import OperatorAccount, OperatorPayout
from app.models.operator_alert import OperatorAlert
from app.schemas.operator import (
    OperatorAccountResponse,
    OperatorAlertResponse,
    OperatorDashboardResponse,
    OperatorOTPRequest,
    OperatorOTPVerify,
    OperatorPayoutResponse,
    OperatorRegister,
    OperatorTokenResponse,
    NodeStatusResponse,
)

operator_router = APIRouter(prefix="/operator", tags=["Operator"])
logger = get_logger("edgevision.api.operator")

OTP_TTL_SECONDS = 300  # 5 minutes


async def _otp_store_set(phone: str, otp: str) -> None:
    """Store OTP in Redis with 5-minute TTL; falls back to in-memory dict."""
    try:
        import redis.asyncio as aioredis

        from app.core.config import settings as _cfg

        r = aioredis.from_url(
            _cfg.REDIS_URL,
            password=_cfg.REDIS_PASSWORD,
            decode_responses=True,
        )
        await r.setex(f"otp:{phone}", OTP_TTL_SECONDS, otp)
        await r.aclose()
    except Exception as exc:
        logger.warning("redis_otp_store_failed, falling back to memory", error=str(exc))
        _otp_memory_store[phone] = (otp, datetime.now(UTC) + timedelta(minutes=5))


async def _otp_store_get(phone: str) -> str | None:
    """Retrieve OTP from Redis; falls back to in-memory dict."""
    try:
        import redis.asyncio as aioredis

        from app.core.config import settings as _cfg

        r = aioredis.from_url(
            _cfg.REDIS_URL,
            password=_cfg.REDIS_PASSWORD,
            decode_responses=True,
        )
        otp = await r.get(f"otp:{phone}")
        await r.aclose()
        return otp
    except Exception:
        stored = _otp_memory_store.get(phone)
        if stored is None:
            return None
        code, expires_at = stored
        if datetime.now(UTC) > expires_at:
            _otp_memory_store.pop(phone, None)
            return None
        return code


async def _otp_store_delete(phone: str) -> None:
    """Delete OTP from Redis after verification; falls back to in-memory dict."""
    try:
        import redis.asyncio as aioredis

        from app.core.config import settings as _cfg

        r = aioredis.from_url(
            _cfg.REDIS_URL,
            password=_cfg.REDIS_PASSWORD,
            decode_responses=True,
        )
        await r.delete(f"otp:{phone}")
        await r.aclose()
    except Exception:
        _otp_memory_store.pop(phone, None)


# In-memory fallback when Redis is unavailable
_otp_memory_store: dict[str, tuple[str, datetime]] = {}


@operator_router.post(
    "/auth/otp-request",
    status_code=status.HTTP_200_OK,
)
async def otp_request(body: OperatorOTPRequest, request: Request):
    """Request an OTP code for phone-based login."""
    otp_code = f"{secrets.randbelow(1000000):06d}"
    await _otp_store_set(body.phone_number, otp_code)
    logger.info(
        "otp_sent",
        phone=body.phone_number,
        ip=request.client.host if request.client else "unknown",
    )
    # Production: send via SMS_GATEWAY_URL
    if settings.SMS_GATEWAY_URL:
        logger.info("sms_gateway_would_send", phone=body.phone_number)
    response: dict = {"message": "OTP sent"}
    if settings.ENVIRONMENT != "production":
        response["otp_dev_hint"] = otp_code
    return response


@operator_router.post(
    "/auth/otp-verify",
    response_model=OperatorTokenResponse,
)
async def otp_verify(body: OperatorOTPVerify, db: AsyncSession = Depends(get_db)):
    """Verify OTP and return JWT token. Requires prior registration."""
    stored_otp = await _otp_store_get(body.phone_number)
    if not stored_otp:
        raise HTTPException(status_code=400, detail="OTP not requested")
    if stored_otp != body.otp_code:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    await _otp_store_delete(body.phone_number)

    result = await db.execute(select(OperatorAccount).where(OperatorAccount.phone_number == body.phone_number))
    operator = result.scalar_one_or_none()
    if operator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operator account not found. Please register first.",
        )

    token = create_access_token(
        data={"sub": str(operator.id), "role": "OPERATOR", "phone": body.phone_number},
        expires_delta=timedelta(hours=24),
    )
    return OperatorTokenResponse(
        access_token=token,
        operator_id=operator.id,
        phone_number=operator.phone_number,
    )


@operator_router.post(
    "/auth/register",
    response_model=OperatorAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_operator(body: OperatorRegister, db: AsyncSession = Depends(get_db)):
    """Register an operator profile (after OTP auth)."""
    result = await db.execute(select(OperatorAccount).where(OperatorAccount.phone_number == body.phone_number))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Phone number already registered")

    operator = OperatorAccount(
        id=uuid4(),
        phone_number=body.phone_number,
        full_name=body.full_name,
        village=body.village,
        district=body.district,
        language_preference=body.language_preference,
        associated_node_id=body.node_id,
        is_active=True,
    )
    db.add(operator)
    await db.commit()
    await db.refresh(operator)
    return operator


@operator_router.get(
    "/dashboard",
    response_model=OperatorDashboardResponse,
)
async def get_dashboard(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Operator dashboard: node status, alerts, stipend balance, latest payout."""
    operator_id = UUID(user["sub"])
    result = await db.execute(select(OperatorAccount).where(OperatorAccount.id == operator_id))
    operator = result.scalar_one_or_none()

    if not operator:
        raise HTTPException(status_code=404, detail="Operator account not found")

    # Node status
    node_status = None
    if operator.associated_node_id:
        node_result = await db.execute(select(Node).where(Node.id == operator.associated_node_id))
        node = node_result.scalar_one_or_none()
        if node:
            # Get latest heartbeat
            from app.models.heartbeat import Heartbeat

            hb_result = await db.execute(
                select(Heartbeat)
                .where(Heartbeat.node_id == node.id)
                .order_by(Heartbeat.created_at.desc())
                .limit(1)
            )
            hb = hb_result.scalar_one_or_none()
            node_status = NodeStatusResponse(
                node_id=node.id,
                node_label=node.node_id,
                status=node.status.value if hasattr(node.status, "value") else str(node.status),
                last_heartbeat_at=hb.created_at if hb else None,
                battery_voltage=hb.battery_voltage if hb else None,
                cpu_temp_celsius=hb.cpu_temp_celsius if hb else None,
                storage_used_gb=hb.storage_used_gb if hb else None,
                lte_rssi_dbm=hb.lte_rssi_dbm if hb else None,
                category=node.category.value if hasattr(node.category, "value") else str(node.category) if node.category else None,
                district=node.district,
            )

    # Recent alerts
    alerts_result = await db.execute(
        select(OperatorAlert)
        .where(OperatorAlert.operator_id == operator_id)
        .order_by(OperatorAlert.created_at.desc())
        .limit(10)
    )
    alerts = alerts_result.scalars().all()

    # Latest payout
    payout_result = await db.execute(
        select(OperatorPayout)
        .where(OperatorPayout.operator_id == operator_id)
        .order_by(OperatorPayout.created_at.desc())
        .limit(5)
    )
    payouts = payout_result.scalars().all()
    latest_payout = payouts[0] if payouts else None

    # Pending alerts count
    pending_count_result = await db.execute(
        select(OperatorAlert)
        .where(OperatorAlert.operator_id == operator_id, OperatorAlert.acknowledged == False)
    )
    pending_alerts = len(pending_count_result.scalars().all())

    # Total annotations count for this operator (annotator_id = operator's user ID)
    total_annotations_result = await db.execute(
        select(func.count(Annotation.id)).where(Annotation.annotator_id == operator_id)
    )
    total_annotations = total_annotations_result.scalar() or 0

    return OperatorDashboardResponse(
        operator_id=str(operator_id),
        phone=operator.phone_number,
        associated_node_id=str(operator.associated_node_id) if operator.associated_node_id else None,
        total_earnings_mwk=operator.stipend_balance_mwk,
        total_annotations=total_annotations,
        pending_alerts=pending_alerts,
        recent_alerts=alerts,
        payout_history=payouts,
        account=operator,
        node_status=node_status,
        latest_payout=latest_payout,
        stipend_balance_mwk=operator.stipend_balance_mwk,
    )


@operator_router.get(
    "/nodes/{node_id}/status",
    response_model=NodeStatusResponse,
)
async def get_node_status(node_id: UUID, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get detailed status for a specific node."""
    operator_id = UUID(user["sub"])
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    from app.models.heartbeat import Heartbeat

    hb_result = await db.execute(
        select(Heartbeat)
        .where(Heartbeat.node_id == node.id)
        .order_by(Heartbeat.created_at.desc())
        .limit(1)
    )
    hb = hb_result.scalar_one_or_none()
    return NodeStatusResponse(
        node_id=node.id,
        node_label=node.node_id,
        status=node.status.value if hasattr(node.status, "value") else str(node.status),
        last_heartbeat_at=hb.created_at if hb else None,
        battery_voltage=hb.battery_voltage if hb else None,
        cpu_temp_celsius=hb.cpu_temp_celsius if hb else None,
        storage_used_gb=hb.storage_used_gb if hb else None,
        lte_rssi_dbm=hb.lte_rssi_dbm if hb else None,
        category=node.category.value if hasattr(node.category, "value") else str(node.category) if node.category else None,
        district=node.district,
    )


@operator_router.get(
    "/alerts",
    response_model=list[OperatorAlertResponse],
)
async def get_alerts(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """List alerts for the operator's node."""
    operator_id = UUID(user["sub"])
    result = await db.execute(
        select(OperatorAlert)
        .where(OperatorAlert.operator_id == operator_id)
        .order_by(OperatorAlert.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@operator_router.post(
    "/alerts/{alert_id}/ack",
    status_code=status.HTTP_200_OK,
)
async def acknowledge_alert(alert_id: UUID, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Acknowledge an alert."""
    operator_id = UUID(user["sub"])
    result = await db.execute(
        select(OperatorAlert).where(
            OperatorAlert.id == alert_id,
            OperatorAlert.operator_id == operator_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    alert.acknowledged_at = datetime.now(UTC)
    await db.commit()
    return {"message": "Alert acknowledged"}


@operator_router.get(
    "/payouts",
    response_model=list[OperatorPayoutResponse],
)
async def get_payouts(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """List payout history for the operator."""
    operator_id = UUID(user["sub"])
    result = await db.execute(
        select(OperatorPayout)
        .where(OperatorPayout.operator_id == operator_id)
        .order_by(OperatorPayout.created_at.desc())
        .limit(24)
    )
    return result.scalars().all()
