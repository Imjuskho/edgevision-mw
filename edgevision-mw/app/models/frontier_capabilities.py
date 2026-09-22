from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class TrajectoryPrediction(TimestampMixin, Base):
    """Predicted trajectory for a tracked object."""

    __tablename__ = "trajectory_predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    track_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    frame_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    current_position: Mapped[dict] = mapped_column(JSONB, nullable=False)
    current_velocity: Mapped[dict] = mapped_column(JSONB, nullable=False)
    heading_rad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    predicted_positions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    predicted_times: Mapped[dict] = mapped_column(JSONB, nullable=False)
    time_to_road_intersection: Mapped[float | None] = mapped_column(Float, nullable=True)
    will_intersect_road: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    intersection_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    class_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prediction_method: Mapped[str] = mapped_column(String(50), nullable=False, default="constant_velocity")


class AnomalyEvent(TimestampMixin, Base):
    """Detected anomaly in the scene."""

    __tablename__ = "anomaly_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    camera_node_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    frame_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    embedding_distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    bounding_box: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    scene_snapshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    feedback_for_labeling: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SceneReconstruction(TimestampMixin, Base):
    """A 3D scene reconstruction snapshot."""

    __tablename__ = "scene_reconstructions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    camera_node_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    num_gaussians: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_keyframes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scene_bounds: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dominant_classes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    static_objects: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    dynamic_objects: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    change_events: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reconstruction_quality: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
