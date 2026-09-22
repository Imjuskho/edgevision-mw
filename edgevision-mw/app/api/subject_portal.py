from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import create_access_token
from app.models.annotation import Annotation
from app.models.consent import ConsentLedger
from app.models.subject import SubjectAnnotation
from app.models.subject_reward import SubjectReward
from app.schemas.subject_portal import (
    CaptureRecord,
    ConsentStatusResponse,
    SubjectHistoryResponse,
    SubjectLookupRequest,
    SubjectLookupResponse,
    SubjectRewardResponse,
    SubjectWithdrawRequest,
    SubjectWithdrawResponse,
)

subject_portal_router = APIRouter(prefix="/subject", tags=["Subject Portal"])
logger = get_logger("edgevision.api.subject_portal")


@subject_portal_router.get("/lookup")
async def subject_lookup_get(hash: str = "", db: AsyncSession = Depends(get_db)):
    """Look up a subject by hash (GET variant for frontend search)."""
    subject_hash = hash.strip()
    if not subject_hash:
        return {"subject_hash": "", "exists": False, "token": None, "total_rewards_mwk": 0}

    consent_result = await db.execute(
        select(ConsentLedger)
        .where(ConsentLedger.subject_hash == subject_hash)
        .order_by(ConsentLedger.created_at.desc())
        .limit(1)
    )
    consent = consent_result.scalar_one_or_none()
    if not consent:
        return {"subject_hash": subject_hash, "exists": False, "token": None, "total_rewards_mwk": 0}

    reward_result = await db.execute(
        select(SubjectReward).where(SubjectReward.subject_hash == subject_hash)
    )
    reward = reward_result.scalar_one_or_none()
    total_rewards = float(reward.pending_airtime_mwk) if reward else 0.0

    portal_token = create_access_token(
        data={"subject_hash": subject_hash, "type": "subject_portal"},
        expires_delta=timedelta(days=7),
    )

    return {
        "subject_hash": subject_hash,
        "exists": True,
        "token": portal_token,
        "total_rewards_mwk": total_rewards,
    }


@subject_portal_router.post(
    "/lookup",
    response_model=SubjectLookupResponse,
)
async def subject_lookup(body: SubjectLookupRequest, db: AsyncSession = Depends(get_db)):
    """Look up a subject by hash + phone, return a portal JWT token."""
    result = await db.execute(
        select(ConsentLedger)
        .where(ConsentLedger.subject_hash == body.subject_hash)
        .order_by(ConsentLedger.created_at.desc())
        .limit(1)
    )
    consent = result.scalar_one_or_none()
    if not consent:
        raise HTTPException(status_code=404, detail="Subject not found")

    reward_result = await db.execute(
        select(SubjectReward).where(SubjectReward.subject_hash == body.subject_hash)
    )
    reward = reward_result.scalar_one_or_none()
    if reward is None:
        reward = SubjectReward(
            id=uuid4(),
            subject_hash=body.subject_hash,
            phone_number=body.phone_number,
            is_active=True,
        )
        db.add(reward)
        await db.commit()

    portal_token = create_access_token(
        data={"subject_hash": body.subject_hash, "phone": body.phone_number, "type": "subject_portal"},
        expires_delta=timedelta(days=7),
    )

    return SubjectLookupResponse(
        subject_hash=body.subject_hash,
        portal_token=portal_token,
        expires_in_hours=168,
    )


@subject_portal_router.get(
    "/{subject_hash}/history",
)
async def get_subject_history(subject_hash: str, db: AsyncSession = Depends(get_db)):
    """Get consent history for a subject (matches frontend SubjectHistory shape)."""
    from sqlalchemy import func as sa_func
    from app.models.subject import SubjectAnnotation

    count_result = await db.execute(
        select(sa_func.count()).select_from(SubjectAnnotation).where(
            SubjectAnnotation.subject_hash == subject_hash
        )
    )
    capture_count = count_result.scalar() or 0

    consent_result = await db.execute(
        select(ConsentLedger)
        .where(ConsentLedger.subject_hash == subject_hash)
        .order_by(ConsentLedger.created_at.desc())
        .limit(1)
    )
    latest_consent = consent_result.scalar_one_or_none()
    consent_status = None
    if latest_consent:
        consent_status = {
            "subject_hash": subject_hash,
            "status": latest_consent.status.value if hasattr(latest_consent.status, "value") else str(latest_consent.status),
            "purposes": latest_consent.purposes or [],
            "recorded_at": latest_consent.created_at.isoformat() if latest_consent.created_at else None,
            "expiry": latest_consent.expiry.isoformat() if latest_consent.expiry else None,
        }

    reward_result = await db.execute(
        select(SubjectReward).where(SubjectReward.subject_hash == subject_hash)
    )
    reward = reward_result.scalar_one_or_none()
    reward_balance = Decimal("0.00")
    total_earned = Decimal("0.00")
    if reward:
        reward_balance = reward.pending_airtime_mwk or Decimal("0.00")
        total_earned = reward.total_airtime_mwk or Decimal("0.00")

    # Build captures list from SubjectAnnotation → Annotation → IngestionBatch
    from app.models.dataset import Dataset
    from app.models.ingestion import IngestionBatch

    capture_rows = await db.execute(
        select(
            SubjectAnnotation.annotation_id,
            SubjectAnnotation.dataset_id,
            SubjectAnnotation.created_at,
            Annotation.image_path,
            IngestionBatch.node_id,
            Dataset.name.label("dataset_name"),
        )
        .outerjoin(Annotation, SubjectAnnotation.annotation_id == Annotation.id)
        .outerjoin(IngestionBatch, Annotation.batch_id == IngestionBatch.id)
        .outerjoin(Dataset, SubjectAnnotation.dataset_id == Dataset.id)
        .where(SubjectAnnotation.subject_hash == subject_hash)
        .order_by(SubjectAnnotation.created_at.desc())
        .limit(20)
    )

    captures = []
    for row in capture_rows.all():
        annotations_result = await db.execute(
            select(sa_func.count()).select_from(Annotation).where(Annotation.id == row.annotation_id)
        )
        ann_count = annotations_result.scalar() or 0
        captures.append({
            "annotation_id": row.annotation_id,
            "node_id": row.node_id,
            "node_label": str(row.node_id)[:8] if row.node_id else "unknown",
            "captured_at": row.created_at.isoformat() if row.created_at else None,
            "dataset_name": row.dataset_name,
            "categories_sold": [],
        })

    return {
        "subject_hash": subject_hash,
        "capture_count": capture_count,
        "captures": captures,
        "consent_status": consent_status,
        "reward_balance_mwk": reward_balance,
        "total_earned_mwk": total_earned,
    }


@subject_portal_router.post(
    "/{subject_hash}/withdraw",
    response_model=SubjectWithdrawResponse,
)
async def subject_withdraw(
    subject_hash: str,
    body: SubjectWithdrawRequest,
    db: AsyncSession = Depends(get_db),
):
    """Subject opts out: triggers consent withdrawal via existing compliance logic."""
    from app.services.compliance import withdraw_consent

    try:
        result = await withdraw_consent(db, subject_hash=subject_hash)
        logger.info("subject_withdrawal_completed", subject_hash=subject_hash)
        return SubjectWithdrawResponse(
            subject_hash=subject_hash,
            status="withdrawn",
            message="Muli ufulu wosiya nthawi zilizonse. Zikwizikizo zanu zakonzedwa.",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@subject_portal_router.get(
    "/{subject_hash}/rewards",
)
async def get_subject_rewards(subject_hash: str, db: AsyncSession = Depends(get_db)):
    """Get reward balance (matches frontend SubjectRewards shape)."""
    result = await db.execute(
        select(SubjectReward).where(SubjectReward.subject_hash == subject_hash)
    )
    reward = result.scalar_one_or_none()
    if not reward:
        return {
            "subject_hash": subject_hash,
            "total_airtime_mwk": Decimal("0.00"),
            "pending_airtime_mwk": Decimal("0.00"),
            "last_payout_at": None,
            "payout_method": "airtime",
        }
    return {
        "subject_hash": subject_hash,
        "total_airtime_mwk": reward.total_airtime_mwk or Decimal("0.00"),
        "pending_airtime_mwk": reward.pending_airtime_mwk or Decimal("0.00"),
        "last_payout_at": reward.last_payout_at.isoformat() if getattr(reward, "last_payout_at", None) else None,
        "payout_method": getattr(reward, "payout_method", None) or "airtime",
    }
