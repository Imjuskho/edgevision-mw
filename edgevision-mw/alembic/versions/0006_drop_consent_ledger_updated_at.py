"""Drop stale updated_at column from consent_ledger.

The consent_ledger is append-only (enforced by PostgreSQL trigger).
The updated_at column was inherited from TimestampMixin but is never written to.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("consent_ledger", "updated_at")


def downgrade() -> None:
    op.add_column(
        "consent_ledger",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default="now()", nullable=False),
    )
