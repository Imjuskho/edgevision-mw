from __future__ import annotations

import math
from datetime import datetime
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

T = TypeVar("T")


class GeoPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees (-90 to 90)")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees (-180 to 180)")

    @model_validator(mode="after")
    def reject_zero_origin(self) -> GeoPoint:
        if self.lat == 0.0 and self.lng == 0.0:
            raise ValueError("invalid coordinates: (0.0, 0.0) is not a valid location")
        return self


class Detection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    class_id: int = Field(..., ge=0, description="Numeric class identifier (>= 0)")
    class_name: str = Field(..., min_length=1, description="Human-readable class name (e.g. CAR, PERSON)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence score (0.0-1.0)")
    bbox: list[float] = Field(..., min_length=4, max_length=4, description="Bounding box [x, y, w, h]")
    mask: str | None = Field(default=None, description="RLE-encoded segmentation mask (optional)")
    track_id: int | None = Field(default=None, description="Object tracking ID across frames")

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: list[float]) -> list[float]:
        if not all(0.0 <= x <= 1.0 for x in v):
            raise ValueError("all bbox values must be in range [0.0, 1.0]")
        return v


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=50, ge=1, description="Items per page")

    @field_validator("page_size")
    @classmethod
    def cap_page_size(cls, v: int) -> int:
        if v > 100:
            raise ValueError("page_size must be <= 100")
        return v


class PaginatedResponse[T](BaseModel):
    items: list[T] = Field(..., description="List of items for the current page")
    total: int = Field(..., description="Total number of items across all pages")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    pages: int = Field(..., description="Total number of pages")

    @classmethod
    def create(cls, items: list[T], total: int, page: int, page_size: int) -> PaginatedResponse[T]:
        pages = math.ceil(total / page_size) if page_size > 0 else 0
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class ErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    error: str = Field(..., description="Short error category or code name")
    detail: str | None = Field(default=None, description="Human-readable error detail")
    code: str = Field(..., description="Machine-readable error code")


class SuccessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str = Field(..., description="Success message")
    id: UUID | None = Field(default=None, description="ID of the created or affected resource")


class TimeRange(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start: datetime = Field(..., description="Start of the time range (inclusive)")
    end: datetime = Field(..., description="End of the time range (exclusive)")


class WeatherData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    temp_c: float = Field(..., description="Temperature in degrees Celsius")
    humidity_pct: float = Field(..., description="Relative humidity as percentage (0-100)")
    lux: float = Field(..., description="Ambient light level in lux")
