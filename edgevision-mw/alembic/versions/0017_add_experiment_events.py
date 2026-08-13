"""Add experiment_events table

Records A/B experiment exposure/conversion/dismissal events flushed
from the frontend analytics client.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "experiment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("experiment_id", sa.String(length=100), nullable=False),
        sa.Column("variant_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_experiment_events_experiment_type",
        "experiment_events",
        ["experiment_id", "event_type"],
    )
    op.create_index(
        "ix_experiment_events_user_id",
        "experiment_events",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_experiment_events_user_id", table_name="experiment_events")
    op.drop_index(
        "ix_experiment_events_experiment_type",
        table_name="experiment_events",
    )
    op.drop_table("experiment_events")
