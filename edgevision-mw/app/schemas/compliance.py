from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConsentRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_hash: str = Field(..., pattern=r"^[0-9a-fA-F]{64}$", description="SHA-256 hash of subject identifier")
    purposes: list[str] = Field(..., min_length=1, description="Consented purposes")
    media_types: list[str] = Field(..., min_length=1, description="Consented media types")
    geography_restrictions: list[str] = Field(default_factory=list, description="Geography restrictions")
    signed_at: datetime = Field(..., description="Consent signing timestamp")
    expiry: datetime = Field(..., description="Consent expiry timestamp")
    guardian_hash: str | None = Field(default=None, description="Guardian hash for minors")
    signature_bytes: str = Field(..., description="Base64-encoded consent signature")

    @model_validator(mode='after')
    def validate_expiry_after_signing(self):
        if self.expiry <= self.signed_at:
            raise ValueError('expiry must be after signed_at')
        return self


class ConsentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Consent ledger entry UUID")
    subject_hash: str = Field(..., pattern=r"^[0-9a-fA-F]{64}$", description="Subject hash")
    tx_hash: str = Field(..., description="Transaction hash")
    status: str = Field(..., description="Consent status")
    signed_at: datetime = Field(..., description="Signing timestamp")


class WithdrawConsent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_hash: str = Field(..., pattern=r"^[0-9a-fA-F]{64}$", description="Subject hash to withdraw consent for")


class ConsentVerification(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    valid: bool = Field(..., description="Whether consent is valid for the purpose")
    status: str = Field(..., description="Consent status")
    purposes: list[str] = Field(default_factory=list, description="Granted purposes")
    expiry: datetime | None = Field(default=None, description="Consent expiry")
    affected_images: int = Field(default=0, description="Number of affected images")


class ComplianceAudit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_date: datetime = Field(..., description="Audit date")
    total_subjects: int = Field(..., description="Total unique subjects")
    active_consents: int = Field(..., description="Active consent count")
    withdrawn: int = Field(..., description="Withdrawn consent count")
    expired: int = Field(..., description="Expired consent count")
    affected_images: int = Field(..., description="Images needing re-consent or removal")
    flagged_batches: list[str] = Field(default_factory=list, description="Batch IDs requiring action")


class PendingDeletionDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_hash: str = Field(..., description="Subject hash")
    withdrawn_at: datetime = Field(..., description="Withdrawal timestamp")
    scheduled_hard_delete: datetime = Field(..., description="Scheduled hard-delete timestamp")


class ConsentAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_active_consents: int = Field(..., description="Total active consents")
    withdrawn_last_30_days: int = Field(..., description="Consents withdrawn in last 30 days")
    expired_last_30_days: int = Field(..., description="Consents expired in last 30 days")
    pending_hard_deletions: int = Field(..., description="Consents pending hard-deletion")
    pending_deletion_details: list[PendingDeletionDetail] = Field(
        default_factory=list, description="Details of pending hard-deletions"
    )


class PIICheckRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str = Field(..., description="Dataset to check")
    sample_size: int = Field(default=100, ge=1, description="Number of samples to check")


class PIICheckResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str = Field(..., description="Dataset identifier")
    total_checked: int = Field(..., description="Total samples checked")
    pii_detected: int = Field(..., description="Samples with PII detected")
    detected_types: dict[str, int] = Field(default_factory=dict, description="PII type counts")
    passed: bool = Field(..., description="Whether the check passed")
