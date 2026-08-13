from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExportRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str = Field(..., description="Dataset to export")
    license_type: str = Field(..., description="License type for this export")
    jurisdiction: str = Field(..., description="Buyer jurisdiction ISO code")


class ExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Export UUID")
    dataset_id: str = Field(..., description="Dataset identifier")
    buyer_id: UUID = Field(..., description="Buyer UUID")
    status: str = Field(..., description="Export status")
    license_key: str | None = Field(default=None, description="License key for the export")
    price_usd: Decimal = Field(default=Decimal("0.00"), description="Price charged in USD")
    export_path: str | None = Field(default=None, description="Secure download path")
    initiated_at: datetime = Field(..., description="Export initiation timestamp")


class InferenceUsageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_type: str = Field(..., description="Model type used for inference")
    total_inputs: int = Field(..., description="Total inputs processed")
    total_cost_usd: Decimal = Field(..., description="Total cost in USD")
    period: str = Field(..., description="Billing period (YYYY-MM)")


class RevenueBreakdown(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period: str = Field(..., description="Revenue period (YYYY-MM)")
    total_revenue_usd: Decimal = Field(..., description="Total revenue in USD")
    by_dataset: dict[str, Decimal] = Field(default_factory=dict, description="Revenue by dataset")
    by_license_type: dict[str, Decimal] = Field(default_factory=dict, description="Revenue by license type")
    monthly_trend: list[dict] = Field(default_factory=list, description="Monthly trend data")
    export_count: int = Field(default=0, description="Number of exports")
