"""Add quotes table for persistent quote storage.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quotes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("buyer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True),
        sa.Column("dataset_id", sa.String(36), index=True, nullable=False),
        sa.Column("base_price_usd", sa.Float, nullable=False),
        sa.Column("exclusivity_multiplier", sa.Float, nullable=False),
        sa.Column("geography_premium", sa.Float, nullable=False),
        sa.Column("total_price_usd", sa.Float, nullable=False),
        sa.Column("license_type", sa.String(20), nullable=False),
        sa.Column("jurisdiction", sa.String(10), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("quotes")
