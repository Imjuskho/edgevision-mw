"""Phase 8: RoadAnnotation table for road surface instance segmentation

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "road_annotations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("annotation_id", UUID(as_uuid=True), sa.ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("surface_type", sa.String(20), nullable=False, server_default="unpaved"),
        sa.Column("instances", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("model_version", sa.String(50), nullable=False, server_default="yolov8n-seg-v1"),
        sa.Column("auto_generated", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index(
        "ix_road_annotations_surface_type",
        "road_annotations",
        ["surface_type"],
    )

    op.create_index(
        "ix_road_annotations_annotation_surface",
        "road_annotations",
        ["annotation_id", "surface_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_road_annotations_annotation_surface")
    op.drop_index("ix_road_annotations_surface_type")
    op.drop_table("road_annotations")
