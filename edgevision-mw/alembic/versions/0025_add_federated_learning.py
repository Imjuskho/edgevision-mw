"""Federated learning tables (already created via Python, no-op migration).

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables already exist from direct Python creation.
    # This migration only documents them in the chain.
    pass


def downgrade() -> None:
    pass
