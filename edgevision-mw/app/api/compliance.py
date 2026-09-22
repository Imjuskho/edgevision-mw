from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.schemas.compliance import (
    ComplianceAudit,
    ConsentAuditResponse,
    ConsentRecord,
    ConsentResponse,
    ConsentVerification,
    PIICheckRequest,
    PIICheckResult,
    SubjectWithdrawalImpact,
    WithdrawConsent,
)
from app.services.compliance import (
    get_consent_audit,
    get_subject_withdrawal_impact,
    record_consent,
    run_daily_audit,
    run_pii_check,
    verify_consent,
    withdraw_consent,
)
from app.services.idempotency import check_idempotency

compliance_router = APIRouter(prefix="/consent", tags=["Compliance"])


@compliance_router.post(
    "/record",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_consent(
    body: ConsentRecord,
    user: dict = Depends(require_role(["ADMIN", "OPERATOR", "FIELD_TECH"])),
    db: AsyncSession = Depends(get_db),
):
    consent_data = body.model_dump()
    consent_data["signature_bytes"] = body.signature_bytes
    return await record_consent(db, consent_data)


@compliance_router.post("/withdraw")
async def withdraw(
    body: WithdrawConsent,
    user: dict = Depends(require_role(["ADMIN", "OPERATOR"])),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        idempotency_key = f"withdraw:{body.subject_hash}:{user['sub']}"

    if await check_idempotency(f"consent:{idempotency_key}"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate request: consent withdrawal for this subject was already processed",
        )

    return await withdraw_consent(db, body.subject_hash)


@compliance_router.get("/verify", response_model=ConsentVerification)
async def check_consent(
    subject_hash: str = Query(..., description="Subject hash to verify"),
    purpose: str = Query(..., description="Intended purpose"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await verify_consent(db, subject_hash, purpose)


@compliance_router.get("/audit", response_model=ComplianceAudit)
async def daily_audit(
    user: dict = Depends(require_role(["ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    return await run_daily_audit(db)


@compliance_router.get("/audit/consent", response_model=ConsentAuditResponse)
async def consent_audit(
    user: dict = Depends(require_role(["ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    return await get_consent_audit(db)


@compliance_router.post(
    "/pii/audit",
    response_model=PIICheckResult,
)
async def pii_audit(
    body: PIICheckRequest,
    user: dict = Depends(require_role(["ADMIN", "QA"])),
    db: AsyncSession = Depends(get_db),
):
    from app.services.compliance import _check_pii_model

    if not _check_pii_model():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PII audit model not loaded (onnxruntime not installed)",
        )
    return await run_pii_check(db, body.dataset_id)


@compliance_router.get(
    "/subject/{subject_hash}/impact",
    response_model=SubjectWithdrawalImpact,
)
async def subject_impact(
    subject_hash: str,
    user: dict = Depends(require_role(["ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    affected = await get_subject_withdrawal_impact(db, subject_hash)
    return SubjectWithdrawalImpact(
        subject_hash=subject_hash,
        affected_datasets=affected,
        total_affected=len(affected),
    )
