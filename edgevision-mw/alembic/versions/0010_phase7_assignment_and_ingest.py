"""Phase 7: DatasetAssignment table for annotator workflow

Revision ID: 0010
Revises: 7e097577179d
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = '0010'
down_revision: Union[str, None] = '7e097577179d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("annotator_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("assigned_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ASSIGNED"),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_images", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_images", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejection_reason", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index(
        "ix_dataset_assignments_status",
        "dataset_assignments",
        ["status"],
    )

    op.create_index(
        "ix_dataset_assignments_dataset_annotator",
        "dataset_assignments",
        ["dataset_id", "annotator_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_assignments_dataset_annotator")
    op.drop_index("ix_dataset_assignments_status")
    op.drop_table("dataset_assignments")
