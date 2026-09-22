"""Add model_version to annotations table

T1: Model-version tagging on auto-labeled/AI-assisted annotations.

Records which model version produced auto-labels, enabling traceability
when a buyer disputes label quality.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-17

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "annotations",
        sa.Column("model_version", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("annotations", "model_version")
