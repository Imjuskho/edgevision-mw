from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OperatorOTPRequest(BaseModel):
    phone_number: str = Field(..., min_length=8, max_length=20, description="Phone number in E.164 or local format")


class OperatorOTPVerify(BaseModel):
    phone_number: str = Field(..., min_length=8, max_length=20)
    otp_code: str = Field(..., min_length=4, max_length=6)


class OperatorRegister(BaseModel):
    phone_number: str = Field(..., min_length=8, max_length=20)
    full_name: str = Field(..., min_length=2, max_length=200)
    village: str | None = Field(default=None, max_length=200)
    district: str | None = Field(default=None, max_length=100)
    language_preference: str = Field(default="ny", pattern="^(en|ny)$")
    node_id: UUID | None = Field(default=None, description="Associated node UUID")


class OperatorTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str
    token_type: str = "bearer"
    operator_id: UUID
    phone_number: str


class OperatorAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    phone_number: str
    full_name: str
    village: str | None
    district: str | None
    language_preference: str
    associated_node_id: UUID | None
    stipend_balance_mwk: Decimal
    last_payout_at: datetime | None
    is_active: bool


class NodeStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: UUID
    node_label: str
    status: str
    last_heartbeat_at: datetime | None
    battery_voltage: float | None
    cpu_temp_celsius: float | None
    storage_used_gb: float | None
    lte_rssi_dbm: float | None
    category: str | None
    district: str | None


class OperatorAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    alert_type: str
    message: str
    severity: str
    acknowledged: bool
    acknowledged_at: datetime | None
    created_at: datetime


class OperatorPayoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount_mwk: Decimal
    period_start: datetime
    period_end: datetime
    status: str
    paid_at: datetime | None
    payment_ref: str | None
    created_at: datetime


class OperatorDashboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    operator_id: str
    phone: str | None = None
    associated_node_id: str | None = None
    total_earnings_mwk: Decimal = Decimal("0.00")
    total_annotations: int = 0
    pending_alerts: int = 0
    recent_alerts: list[OperatorAlertResponse] = []
    payout_history: list[OperatorPayoutResponse] = []
    account: OperatorAccountResponse | None = None
    node_status: NodeStatusResponse | None = None
    latest_payout: OperatorPayoutResponse | None = None
    stipend_balance_mwk: Decimal = Decimal("0.00")
