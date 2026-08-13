"""Add subject_annotations junction table for efficient consent withdrawal lookups.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subject_annotations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("subject_hash", sa.String(64), index=True, nullable=False),
        sa.Column("annotation_id", UUID(as_uuid=True), sa.ForeignKey("annotations.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
    )

    op.create_index(
        "ix_subject_annotations_hash_annotation",
        "subject_annotations",
        ["subject_hash", "annotation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_subject_annotations_hash_annotation", table_name="subject_annotations")
    op.drop_table("subject_annotations")
