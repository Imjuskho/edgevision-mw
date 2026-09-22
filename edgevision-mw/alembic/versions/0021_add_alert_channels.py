"""Add alert_channels table

Outbound delivery channels (webhook / sms / push) for perception-event push
alerting.  Config is channel-specific JSON (webhook URL, phone number, push
token, …).

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_channels",
        sa.Column("channel_type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_alert_channels_tenant_enabled",
        "alert_channels",
        ["tenant_id", "enabled"],
    )


def downgrade() -> None:
    op.drop_index("ix_alert_channels_tenant_enabled", table_name="alert_channels")
    op.drop_table("alert_channels")
