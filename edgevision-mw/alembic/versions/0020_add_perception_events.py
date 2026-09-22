"""Add perception_events table

Rule-triggered events from live annotation streams (dwell, presence,
confidence drop) plus auto-saved clip metadata.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "perception_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("rule_name", sa.String(length=200), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=True),
        sa.Column("class_name", sa.String(length=64), nullable=True),
        sa.Column("taxonomy_label", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("clip_frames", sa.Integer(), nullable=False),
        sa.Column("clip_storage_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("auto_save", sa.Boolean(), nullable=False),
        sa.Column(
            "dataset_id",
            sa.Uuid(),
            sa.ForeignKey("datasets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_perception_events_type_created",
        "perception_events",
        ["event_type", "created_at"],
    )
    op.create_index(
        "ix_perception_events_track",
        "perception_events",
        ["track_id", "created_at"],
    )
    op.create_index(
        "ix_perception_events_rule_id",
        "perception_events",
        ["rule_id"],
    )
    op.create_index(
        "ix_perception_events_dataset_id",
        "perception_events",
        ["dataset_id"],
    )
    op.create_index(
        "ix_perception_events_tenant_id",
        "perception_events",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_perception_events_tenant_id", table_name="perception_events")
    op.drop_index("ix_perception_events_dataset_id", table_name="perception_events")
    op.drop_index("ix_perception_events_rule_id", table_name="perception_events")
    op.drop_index("ix_perception_events_track", table_name="perception_events")
    op.drop_index("ix_perception_events_type_created", table_name="perception_events")
    op.drop_table("perception_events")
