from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StudioDatasetCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=200, description="Human-readable dataset name")
    dataset_id: str | None = Field(
        default=None,
        max_length=36,
        description="Optional slug ID; generated from name if omitted",
    )
    source_type: str = Field(default="studio", description="Dataset source type (studio, sync, photo, phase)")
    description: str | None = Field(default=None, max_length=500, description="Optional description")


class StudioDatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: str
    name: str
    status: str
    sample_count: int
    source_type: str | None = None
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class SessionCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str = Field(..., description="Dataset string ID (e.g. DS-LILONGWE-001)")


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    dataset_id: UUID
    started_at: datetime
    ended_at: datetime | None = None
    image_count: int
    annotations_created: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BBoxAnnotation(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    x: float = Field(..., ge=0.0, le=1.0, description="Left edge (0-1)")
    y: float = Field(..., ge=0.0, le=1.0, description="Top edge (0-1)")
    width: float = Field(..., gt=0.0, le=1.0, description="Width (0-1)")
    height: float = Field(..., gt=0.0, le=1.0, description="Height (0-1)")
    label: str = Field(..., min_length=1, description="Annotation class label (taxonomy ID)")
    category: str | None = Field(default=None, description="Taxonomy category ID")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    attributes: list[str] = Field(default_factory=list, description="Scene-level attribute tags")
    polygon: list[list[float]] | None = Field(
        default=None,
        description="Optional normalized polygon [[x,y], ...] from segmentation prelabel",
    )


class SaveAnnotationRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    image_index: int = Field(..., ge=0)
    annotations: list[BBoxAnnotation]
    tool_used: str = Field(default="bbox", description="Annotation tool used")


class SaveAnnotationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action_id: UUID
    annotation_id: UUID | None = None
    saved: bool
    image_index: int
    annotation_count: int


class ImageListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    annotation_id: UUID
    image_path: str
    thumbnail_path: str
    status: str
    has_human_labels: bool


class ImageListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    total: int
    page: int
    page_size: int
    images: list[ImageListItem]


class HealthScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: UUID
    overall_score: float
    completeness_pct: float
    consistency_pct: float
    accuracy_pct: float
    timeliness_pct: float
    recommendations: list[str]


class ExportJobCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dataset_id: str = Field(..., description="Dataset string ID (e.g. DS-LILONGWE-001)")
    format: str = Field(default="coco", description="Export format: coco, yolo, csv")
    include_images: bool = True
    include_annotations: bool = True
    include_metadata: bool = True


class ExportJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    user_id: UUID
    status: str
    format: str
    progress_pct: float
    file_size_bytes: int | None = None
    download_url: str | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class DuplicateGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    similarity_score: float
    strategy: str
    resolved: bool
    resolution_action: str | None = None
    member_count: int


class AnnotationsResponse(BaseModel):
    annotation_id: UUID
    image_index: int
    annotations: list[BBoxAnnotation]
    tool_used: str | None = None
    qa_labels: dict | None = Field(
        default=None,
        description="QA metadata including optional refines (2D projection corrections)",
    )
    detected_objects: list[dict] = Field(
        default_factory=list,
        description="Prelabel/mask targets from detected_objects when human_labels empty",
    )
    frame_width: int | None = None
    frame_height: int | None = None
    label_source: str | None = None
    ai_draft: bool = False
