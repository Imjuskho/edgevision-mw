from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str = Field(..., description="Dataset string ID or UUID")
    annotator_ids: list[str] = Field(..., min_length=1, description="List of annotator user IDs")
    deadline: datetime | None = Field(default=None, description="Assignment deadline")
    priority: int = Field(default=0, ge=0, le=10, description="Priority (0-10)")


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: str
    dataset_name: str
    annotator_id: str
    annotator_name: str
    status: str
    deadline: datetime | None = None
    priority: int
    total_images: int
    completed_images: int
    progress_pct: float
    is_overdue: bool
    created_at: datetime


class AssignmentListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignments: list[AssignmentResponse]
    total: int


class QueueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: UUID
    dataset_id: str
    dataset_name: str
    status: str
    deadline: datetime | None = None
    priority: int
    total_images: int
    completed_images: int
    progress_pct: float
    is_overdue: bool
    image_count_available: int


class QueueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[QueueItem]
    total: int


class AssignmentClaim(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: UUID
