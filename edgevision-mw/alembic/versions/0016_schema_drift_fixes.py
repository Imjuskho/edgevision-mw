"""Close model/migration schema drift

Adds columns and tables that exist in the SQLAlchemy models but were
never created by any migration:

- consent_ledger.hard_deleted_at      (model: app/models/consent.py)
- buyer_api_keys.key_id               (model: app/models/buyer.py)
- buyer_api_keys.key_hash widened 64 -> 255 to match model
- deployed_models.format              (model: app/models/deployed_model.py)
- inference_usage table               (model: app/models/inference_usage.py)

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-31

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consent_ledger",
        sa.Column("hard_deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "buyer_api_keys",
        sa.Column("key_id", sa.String(32), nullable=True),
    )
    op.execute(
        "UPDATE buyer_api_keys SET key_id = left(gen_random_uuid()::text, 32)"
        " WHERE key_id IS NULL"
    )
    op.alter_column("buyer_api_keys", "key_id", nullable=False)
    op.create_index("ix_buyer_api_keys_key_id", "buyer_api_keys", ["key_id"], unique=True)

    op.alter_column(
        "buyer_api_keys",
        "key_hash",
        existing_type=sa.String(64),
        type_=sa.String(255),
        existing_nullable=False,
    )

    op.add_column(
        "deployed_models",
        sa.Column(
            "format",
            sa.String(20),
            nullable=False,
            server_default="ultralytics",
        ),
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("inference_usage"):
        op.create_table(
            "inference_usage",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("model_type", sa.String(40), nullable=False),
            sa.Column("input_count", sa.Integer, nullable=False, server_default="1"),
            sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0.000000"),
            sa.Column("billed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("inference_usage")

    op.drop_column("deployed_models", "format")

    op.alter_column(
        "buyer_api_keys",
        "key_hash",
        existing_type=sa.String(255),
        type_=sa.String(64),
        existing_nullable=False,
    )

    op.drop_index("ix_buyer_api_keys_key_id", table_name="buyer_api_keys")
    op.drop_column("buyer_api_keys", "key_id")

    op.drop_column("consent_ledger", "hard_deleted_at")
