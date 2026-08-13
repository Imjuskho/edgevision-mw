"""Add deployed_models table for model registry

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deployed_models",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("training_job_id", UUID(as_uuid=True), sa.ForeignKey("training_jobs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("model_name", sa.String(150), nullable=False),
        sa.Column("model_type", sa.String(40), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("dataset_id", sa.String(100), nullable=False),
        sa.Column("artifact_path", sa.String(500), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deployed_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index(
        "ix_deployed_models_model_type",
        "deployed_models",
        ["model_type"],
    )

    op.create_index(
        "ix_deployed_models_type_active",
        "deployed_models",
        ["model_type", "is_active"],
    )

    # Enforce at most one active deployment per model_type at the DB level,
    # in addition to the application-level swap in the /activate endpoint.
    op.create_index(
        "ux_deployed_models_active_per_type",
        "deployed_models",
        ["model_type"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("ux_deployed_models_active_per_type", table_name="deployed_models")
    op.drop_index("ix_deployed_models_type_active", table_name="deployed_models")
    op.drop_index("ix_deployed_models_model_type", table_name="deployed_models")
    op.drop_table("deployed_models")
