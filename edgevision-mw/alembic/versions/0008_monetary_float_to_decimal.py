"""Migrate monetary fields from Float to Numeric for Decimal precision.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # datasets.price_usd: Float -> Numeric(12,2)
    # Data is preserved; Float values are cast to Numeric with no loss for typical price ranges.
    op.alter_column(
        "datasets",
        "price_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
    )

    # quotes: all price/multiplier fields from Float -> Numeric
    op.alter_column(
        "quotes",
        "base_price_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
    )
    op.alter_column(
        "quotes",
        "exclusivity_multiplier",
        existing_type=sa.Float(),
        type_=sa.Numeric(8, 4),
        existing_nullable=False,
    )
    op.alter_column(
        "quotes",
        "geography_premium",
        existing_type=sa.Float(),
        type_=sa.Numeric(8, 4),
        existing_nullable=False,
    )
    op.alter_column(
        "quotes",
        "total_price_usd",
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "quotes",
        "total_price_usd",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Float(),
        existing_nullable=False,
    )
    op.alter_column(
        "quotes",
        "geography_premium",
        existing_type=sa.Numeric(8, 4),
        type_=sa.Float(),
        existing_nullable=False,
    )
    op.alter_column(
        "quotes",
        "exclusivity_multiplier",
        existing_type=sa.Numeric(8, 4),
        type_=sa.Float(),
        existing_nullable=False,
    )
    op.alter_column(
        "quotes",
        "base_price_usd",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Float(),
        existing_nullable=False,
    )
    op.alter_column(
        "datasets",
        "price_usd",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Float(),
        existing_nullable=False,
    )
