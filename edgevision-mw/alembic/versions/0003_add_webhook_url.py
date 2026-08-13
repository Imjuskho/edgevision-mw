"""Add webhook_url to users for buyer notifications.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("webhook_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "webhook_url")
