"""Add dataset_subject_memberships join table

G1: Maps which subjects appear in which datasets so that when consent is
withdrawn we can find all affected datasets and exports efficiently.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-17

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_subject_memberships",
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("subject_hash", sa.String(length=128), nullable=False),
        sa.Column("first_seen_batch_id", sa.String(length=64), nullable=True),
        sa.Column("annotation_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.dataset_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_batch_id"],
            ["ingestion_batches.batch_id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_dsm_dataset_id",
        "dataset_subject_memberships",
        ["dataset_id"],
    )
    op.create_index(
        "ix_dsm_subject_hash",
        "dataset_subject_memberships",
        ["subject_hash"],
    )
    op.create_index(
        "ix_dsm_dataset_subject",
        "dataset_subject_memberships",
        ["dataset_id", "subject_hash"],
        unique=True,
    )
    op.create_index(
        "ix_dsm_subject_dataset",
        "dataset_subject_memberships",
        ["subject_hash", "dataset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_dsm_subject_dataset", table_name="dataset_subject_memberships")
    op.drop_index("ix_dsm_dataset_subject", table_name="dataset_subject_memberships")
    op.drop_index("ix_dsm_subject_hash", table_name="dataset_subject_memberships")
    op.drop_index("ix_dsm_dataset_id", table_name="dataset_subject_memberships")
    op.drop_table("dataset_subject_memberships")
