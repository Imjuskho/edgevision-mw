from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CorridorNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: UUID
    node_label: str
    status: str
    district: str | None
    last_heartbeat_at: datetime | None
    category: str | None


class CorridorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    corridor_id: str
    name: str
    node_count: int
    nodes: list[CorridorNode]


class TrafficReportPoint(BaseModel):
    timestamp: datetime
    vehicle_count: int
    pedestrian_count: int
    cyclist_count: int
    motorcycle_count: int


class TrafficReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: UUID
    node_label: str
    period_start: datetime
    period_end: datetime
    data_points: list[TrafficReportPoint]
    total_vehicles: int
    total_pedestrians: int


class NearMissEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    node_id: UUID
    node_label: str
    latitude: float | None
    longitude: float | None
    timestamp: datetime
    distance_m: float | None
    velocity_mps: float | None
    severity_weight: float


class NearMissHeatmap(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str = "FeatureCollection"
    features: list[dict]


class PedestrianExposurePoint(BaseModel):
    hour_of_day: int
    count: int
    node_id: UUID
    node_label: str


class RoadConditionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: UUID
    node_label: str
    avg_drivable_ratio: float
    hazard_counts: dict[str, int]
    sample_count: int


class ReportRequest(BaseModel):
    node_ids: list[UUID] = Field(..., min_length=1, description="Nodes to include")
    period_start: datetime
    period_end: datetime


class ReportExportRequest(BaseModel):
    report_type: str = Field(..., pattern="^(traffic|near_miss|pedestrian_exposure|road_condition)$")
    node_ids: list[UUID] = Field(..., min_length=1)
    period_start: datetime
    period_end: datetime
    format: str = Field(default="pdf", pattern="^(pdf|csv|geojson)$")


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_number: str
    subscription_period_start: datetime
    subscription_period_end: datetime
    node_count: int
    unit_price_usd: Decimal
    subtotal_usd: Decimal
    subtotal_mwk: Decimal
    tax_usd: Decimal
    tax_mwk: Decimal
    total_usd: Decimal
    total_mwk: Decimal
    status: str
    paid_at: datetime | None
    pdf_url: str | None
    created_at: datetime


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    buyer_id: UUID
    node_count: int
    monthly_price_usd: Decimal
    monthly_price_mwk: Decimal
    status: str
    invoices: list[InvoiceResponse]
