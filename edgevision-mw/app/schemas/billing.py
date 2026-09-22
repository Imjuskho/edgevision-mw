from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import LicenseType


class ExportRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str = Field(..., description="Dataset to export")
    license_type: LicenseType = Field(..., description="License type for this export")
    jurisdiction: str = Field(..., min_length=2, max_length=3, description="Buyer jurisdiction ISO code")


class ExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Export UUID")
    dataset_id: str = Field(..., description="Dataset identifier")
    buyer_id: UUID = Field(..., description="Buyer UUID")
    status: str = Field(..., description="Export status")
    license_key: str | None = Field(default=None, description="License key for the export")
    delivery_url: str | None = Field(default=None, description="Secure download URL")
    price_usd: Decimal = Field(default=Decimal("0.00"), description="Price charged in USD")
    file_size_bytes: int | None = Field(default=None, description="File size in bytes")
    formats_delivered: list[str] = Field(default_factory=list, description="Formats delivered")
    initiated_at: datetime = Field(..., description="Export initiation timestamp")
    completed_at: datetime | None = Field(default=None, description="Export completion timestamp")


class ExportDownloadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    download_url: str = Field(..., description="Temporary signed download URL")
    expires_in_seconds: int = Field(..., description="URL validity period in seconds")
    filename: str = Field(..., description="Suggested filename")
    content_type: str = Field(default="application/octet-stream", description="MIME type")


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
