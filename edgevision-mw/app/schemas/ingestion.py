from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .common import Detection, GeoPoint, WeatherData


class BatchUpload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: UUID = Field(..., description="UUID of the uploading node")
    batch_id: str = Field(..., min_length=3, max_length=128, description="Client-generated batch identifier")
    event_count: int = Field(..., description="Number of events in this batch", ge=1)
    file_size_bytes: int = Field(..., gt=0, description="Total file size in bytes")
    checksum_sha256: str = Field(..., pattern=r"^[0-9a-fA-F]{64}$", description="SHA-256 hex hash")
    compression_codec: str = Field(default="h265", description="Video compression codec used")
    quality_scores: dict = Field(default_factory=dict, description="Per-event quality scores")


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Server-assigned batch UUID")
    batch_id: str = Field(..., description="Batch identifier")
    status: str = Field(..., description="Batch status (PENDING, VALIDATING, INDEXING, COMPLETED, FAILED)")
    ingested_at: datetime | None = Field(default=None, description="Timestamp when ingestion completed")
    storage_path: str | None = Field(default=None, description="Object storage path for the batch")
    event_count: int = Field(..., description="Number of events in the batch")


class BatchValidation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    checksum_sha256: str = Field(..., pattern=r"^[0-9a-fA-F]{64}$", description="SHA-256 checksum of the batch payload")
    node_signature: str = Field(..., description="Base64-encoded Ed25519 signature of the batch")
    expected_node_id: UUID = Field(..., description="Expected UUID of the signing node")


class ValidationResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    valid: bool = Field(..., description="Whether the batch passed validation")
    errors: list[str] = Field(default_factory=list, description="Blocking validation errors")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking validation warnings")


class IngestionQueue(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_pending: int = Field(..., description="Number of batches waiting to be processed")
    total_processing: int = Field(..., description="Number of batches currently being processed")
    total_completed: int = Field(..., description="Number of successfully completed batches")
    avg_latency_seconds: float = Field(..., description="Average ingestion latency in seconds")
    oldest_pending: datetime | None = Field(default=None, description="Timestamp of the oldest pending batch")


class EventPacket(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: str = Field(..., description="Node identifier that captured the event")
    timestamp: datetime = Field(..., description="Capture timestamp")
    gps: GeoPoint = Field(..., description="GPS coordinates at capture time")
    thumbnail_base64: str = Field(..., description="Base64-encoded JPEG thumbnail")
    clip_path: str | None = Field(default=None, description="Storage path to the video clip")
    detections: list[Detection] = Field(default_factory=list, description="Object detections in this event")
    weather: WeatherData = Field(..., description="Weather conditions at capture time")
    pii_redacted: bool = Field(..., description="Whether PII redaction was applied on-device")
    quality_score: float = Field(..., description="Image quality score (0.0-1.0)", ge=0.0, le=1.0)
