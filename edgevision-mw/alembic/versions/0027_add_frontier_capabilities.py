"""Add frontier capabilities tables

Trajectory prediction, open-set anomaly detection, and living 3D
scene reconstruction.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-17

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # trajectory_predictions
    # ------------------------------------------------------------------
    op.create_table(
        "trajectory_predictions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("frame_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_position", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_velocity", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("heading_rad", sa.Float(), nullable=False),
        sa.Column("predicted_positions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("predicted_times", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("time_to_road_intersection", sa.Float(), nullable=True),
        sa.Column("will_intersect_road", sa.Boolean(), nullable=False),
        sa.Column("intersection_confidence", sa.Float(), nullable=False),
        sa.Column("class_name", sa.String(length=50), nullable=True),
        sa.Column("prediction_method", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trajectory_predictions_track_id",
        "trajectory_predictions",
        ["track_id"],
    )
    op.create_index(
        "ix_trajectory_predictions_frame_timestamp",
        "trajectory_predictions",
        ["frame_timestamp"],
    )
    op.create_index(
        "ix_trajectory_predictions_created_at",
        "trajectory_predictions",
        ["created_at"],
    )

    # ------------------------------------------------------------------
    # anomaly_events
    # ------------------------------------------------------------------
    op.create_table(
        "anomaly_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("camera_node_id", sa.String(length=100), nullable=False),
        sa.Column("frame_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("anomaly_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("embedding_distance", sa.Float(), nullable=True),
        sa.Column("bounding_box", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scene_snapshot_path", sa.String(length=500), nullable=True),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("resolution_note", sa.String(length=500), nullable=True),
        sa.Column("feedback_for_labeling", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_anomaly_events_camera_node_id",
        "anomaly_events",
        ["camera_node_id"],
    )
    op.create_index(
        "ix_anomaly_events_frame_timestamp",
        "anomaly_events",
        ["frame_timestamp"],
    )
    op.create_index(
        "ix_anomaly_events_created_at",
        "anomaly_events",
        ["created_at"],
    )
    op.create_index(
        "ix_anomaly_events_type_score",
        "anomaly_events",
        ["anomaly_type", "anomaly_score"],
    )

    # ------------------------------------------------------------------
    # scene_reconstructions
    # ------------------------------------------------------------------
    op.create_table(
        "scene_reconstructions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("camera_node_id", sa.String(length=100), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("num_gaussians", sa.Integer(), nullable=False),
        sa.Column("num_keyframes", sa.Integer(), nullable=False),
        sa.Column("scene_bounds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dominant_classes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("static_objects", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dynamic_objects", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("change_events", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("artifact_path", sa.String(length=500), nullable=True),
        sa.Column("thumbnail_path", sa.String(length=500), nullable=True),
        sa.Column("reconstruction_quality", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scene_reconstructions_camera_node_id",
        "scene_reconstructions",
        ["camera_node_id"],
    )
    op.create_index(
        "ix_scene_reconstructions_timestamp",
        "scene_reconstructions",
        ["timestamp"],
    )
    op.create_index(
        "ix_scene_reconstructions_created_at",
        "scene_reconstructions",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_scene_reconstructions_created_at", table_name="scene_reconstructions")
    op.drop_index("ix_scene_reconstructions_timestamp", table_name="scene_reconstructions")
    op.drop_index("ix_scene_reconstructions_camera_node_id", table_name="scene_reconstructions")
    op.drop_table("scene_reconstructions")

    op.drop_index("ix_anomaly_events_type_score", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_created_at", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_frame_timestamp", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_camera_node_id", table_name="anomaly_events")
    op.drop_table("anomaly_events")

    op.drop_index("ix_trajectory_predictions_created_at", table_name="trajectory_predictions")
    op.drop_index("ix_trajectory_predictions_frame_timestamp", table_name="trajectory_predictions")
    op.drop_index("ix_trajectory_predictions_track_id", table_name="trajectory_predictions")
    op.drop_table("trajectory_predictions")
