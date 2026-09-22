from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubjectLookupRequest(BaseModel):
    subject_hash: str = Field(..., min_length=8, max_length=64)
    phone_number: str = Field(..., min_length=8, max_length=20)


class SubjectLookupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_hash: str
    portal_token: str
    expires_in_hours: int = 168  # 7 days


class SubjectPortalToken(BaseModel):
    subject_hash: str
    phone_number: str | None = None
    exp: datetime | None = None


class CaptureRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_id: UUID
    node_id: UUID
    node_label: str
    captured_at: datetime
    dataset_name: str | None
    categories_sold: list[str]


class ConsentStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_hash: str
    status: str
    purposes: list[str]
    recorded_at: datetime
    expiry: datetime | None


class SubjectHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_hash: str
    capture_count: int
    captures: list[CaptureRecord]
    consent_status: ConsentStatusResponse | None
    reward_balance_mwk: Decimal
    total_earned_mwk: Decimal


class SubjectWithdrawRequest(BaseModel):
    subject_hash: str = Field(..., min_length=8, max_length=64)
    reason: str | None = Field(default=None, max_length=500)


class SubjectWithdrawResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_hash: str
    status: str
    message: str


class SubjectRewardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_hash: str
    total_airtime_mwk: Decimal
    pending_airtime_mwk: Decimal
    last_payout_at: datetime | None
    payout_method: str
