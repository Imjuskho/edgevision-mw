from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import LicenseType


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Dataset UUID")
    dataset_id: str = Field(..., description="Dataset identifier")
    name: str = Field(..., description="Dataset name")
    version: str = Field(..., description="Version string")
    status: str = Field(..., description="Dataset status")
    sample_count: int = Field(..., description="Number of samples")
    classes: dict = Field(..., description="Class distribution")
    annotations_per_image: float = Field(..., description="Average annotations per image")
    image_width: int = Field(..., description="Image width in pixels")
    image_height: int = Field(..., description="Image height in pixels")
    geographic_coverage: dict = Field(..., description="Geographic coverage stats")
    demographic_report: dict = Field(..., description="Demographic breakdown")
    consent_coverage_pct: float = Field(..., description="Consent coverage percentage")
    pii_scrub_verified: bool = Field(..., description="PII scrub verified flag")
    iaa_score: float = Field(..., description="Overall IAA score")
    formats: list[str] = Field(..., description="Available export formats")
    price_usd: Decimal = Field(..., description="Price in USD")
    license_type: str = Field(..., description="License type")
    created_at: datetime = Field(..., description="Creation timestamp")


class DatasetBuildRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., max_length=200, description="Dataset name")
    annotation_ids: list[UUID] = Field(..., min_length=1, description="Certified annotation IDs to include")
    formats: list[str] = Field(default=["COCO", "YOLO"], description="Export formats to generate")
    license_type: LicenseType = Field(default=LicenseType.ANNUAL, description="License type")


class DatasetManifest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str = Field(..., description="Dataset identifier")
    format: str = Field(..., description="Manifest format (COCO, YOLO)")
    info: dict = Field(..., description="Dataset info block")
    images: list[dict] = Field(..., description="Image entries")
    annotations: list[dict] = Field(..., description="Annotation entries")
    categories: list[dict] = Field(..., description="Category definitions")


class QuoteRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str = Field(..., description="Dataset to quote")
    license_type: LicenseType = Field(..., description="Requested license type")
    jurisdiction: str = Field(..., min_length=2, max_length=3, description="Buyer jurisdiction ISO code")
    use_case: str = Field(default="", max_length=500, description="Intended use case description")


class QuoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Quote UUID")
    dataset_id: str = Field(..., description="Dataset identifier")
    base_price_usd: Decimal = Field(..., description="Base dataset price")
    exclusivity_multiplier: Decimal = Field(..., description="Exclusivity price multiplier")
    geography_premium: Decimal = Field(..., description="Geography-based premium")
    total_price_usd: Decimal = Field(..., description="Total quoted price")
    license_type: str = Field(..., description="License type")
    expires_at: datetime = Field(..., description="Quote expiry timestamp")
