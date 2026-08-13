"""Phase 8: AgriAnnotation table for crop/health instance segmentation

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agri_annotations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("annotation_id", UUID(as_uuid=True), sa.ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("crop_type", sa.String(30), nullable=False, server_default="maize"),
        sa.Column("health_status", sa.String(30), nullable=False, server_default="healthy"),
        sa.Column("instances", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("model_version", sa.String(50), nullable=False, server_default="yolov8n-seg-v1"),
        sa.Column("auto_generated", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index(
        "ix_agri_annotations_crop_type",
        "agri_annotations",
        ["crop_type"],
    )

    op.create_index(
        "ix_agri_annotations_health_status",
        "agri_annotations",
        ["health_status"],
    )

    op.create_index(
        "ix_agri_annotations_annotation_crop",
        "agri_annotations",
        ["annotation_id", "crop_type"],
    )

    op.create_index(
        "ix_agri_annotations_annotation_health",
        "agri_annotations",
        ["annotation_id", "health_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_agri_annotations_annotation_health")
    op.drop_index("ix_agri_annotations_annotation_crop")
    op.drop_index("ix_agri_annotations_health_status")
    op.drop_index("ix_agri_annotations_crop_type")
    op.drop_table("agri_annotations")
