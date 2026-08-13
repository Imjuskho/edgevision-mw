from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReviewQueueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: UUID
    dataset_id: str
    dataset_name: str
    annotator_id: str
    annotator_name: str
    total_images: int
    completed_images: int
    submitted_at: datetime | None = None
    deadline: datetime | None = None
    priority: int


class ReviewQueueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[ReviewQueueItem]
    total: int


class ReviewJobDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: UUID
    dataset_id: str
    dataset_name: str
    annotator_id: str
    annotator_name: str
    total_images: int
    completed_images: int
    images: list[dict]
    deadline: datetime | None = None
    priority: int


class ReviewDecision(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    decision: str = Field(..., pattern="^(certify|reject)$", description="certify or reject")
    reason: str | None = Field(default=None, max_length=1000, description="Rejection reason")


class ReviewDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: str
    status: str
    message: str


class IAAMetrics(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: str
    total_annotations: int
    annotations_with_labels: int
    annotations_certified: int
    annotations_rejected: int
    completeness_pct: float
    accuracy_pct: float
    overall_iaa: float


class AnnotationReviewAction(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_id: str
    decision: str = Field(..., pattern="^(approve|reject)$")


class LiveReviewBulkRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_ids: list[str] = Field(..., min_length=1)
    reason: str | None = Field(default=None, max_length=1000)


class LiveReviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_id: str
    image_path: str
    thumbnail_url: str
    status: str
    orientation: str = "normal"
    depth_available: bool = False
    annotation_count: int = 0
    created_at: datetime | None = None
    live_capture: bool = True


class LiveReviewQueueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[LiveReviewItem]
    total: int
