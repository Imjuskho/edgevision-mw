from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobAssignRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    count: int = Field(default=10, ge=1, le=100, description="Number of jobs to assign")
    annotator_id: UUID | None = Field(default=None, description="Force-assign to specific annotator")


class JobAssignment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_id: UUID = Field(..., description="Annotation UUID")
    annotator_id: UUID = Field(..., description="Assigned annotator UUID")
    assigned_at: datetime = Field(..., description="Assignment timestamp")
    deadline: datetime | None = Field(default=None, description="Assignment deadline")


class AnnotationLabel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    class_name: str | None = Field(default=None, description="Detected class label")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Detection confidence 0-1")
    bbox: list[float] | None = Field(
        default=None,
        min_length=4,
        max_length=4,
        description="Bounding box as [x1, y1, x2, y2] or [x, y, w, h]",
    )

    @model_validator(mode="before")
    @classmethod
    def _rename_class_key(cls, data):
        if isinstance(data, dict) and "class" in data and "class_name" not in data:
            data = {**data, "class_name": data["class"]}
        return data


class LabelSubmission(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    labels: list[AnnotationLabel] = Field(..., min_length=1, description="Non-empty list of label objects")
    quality_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Self-reported quality score")


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_labels: dict = Field(..., description="QA reviewer label corrections")


class AnnotationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Annotation UUID")
    status: str = Field(..., description="Current annotation status")
    iaa_score: float | None = Field(default=None, description="IAA score after review")
    quality_score: float = Field(..., description="Quality score")
    annotator_id: UUID | None = Field(default=None, description="Assigned annotator")
    qa_reviewer_id: UUID | None = Field(default=None, description="QA reviewer")
    model_version: str | None = Field(default=None, description="Model version that produced auto-labels")


class AnnotatorLeaderboard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotator_id: UUID = Field(..., description="Annotator UUID")
    full_name: str = Field(..., description="Annotator name")
    total_annotated: int = Field(..., description="Total annotations completed")
    avg_quality_score: float = Field(..., description="Average quality score")
    iaa_score: float = Field(..., description="Average IAA score")
    weekly_count: int = Field(..., description="Annotations this week")
