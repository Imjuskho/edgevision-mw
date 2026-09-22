"""Add revenue interface tables + dashboard indexes

D1: operator_accounts, operator_payouts, operator_alerts
D2: invoices
D3: subject_rewards
D4.2: performance indexes for new dashboard queries

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- D1: operator_accounts ---
    op.create_table(
        "operator_accounts",
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("village", sa.String(length=200), nullable=True),
        sa.Column("district", sa.String(length=100), nullable=True),
        sa.Column("language_preference", sa.String(length=5), nullable=False, server_default="ny"),
        sa.Column("associated_node_id", sa.Uuid(), nullable=True),
        sa.Column("stipend_balance_mwk", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("last_payout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["associated_node_id"], ["nodes.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_operator_accounts_phone", "operator_accounts", ["phone_number"], unique=True)
    op.create_index("ix_operator_accounts_node", "operator_accounts", ["associated_node_id"])

    # --- D1: operator_payouts ---
    op.create_table(
        "operator_payouts",
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("amount_mwk", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_ref", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["operator_id"], ["operator_accounts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_operator_payouts_operator", "operator_payouts", ["operator_id"])

    # --- D1: operator_alerts ---
    op.create_table(
        "operator_alerts",
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=True),
        sa.Column("alert_type", sa.String(length=50), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
        sa.Column("details", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operator_id"], ["operator_accounts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_operator_alerts_node", "operator_alerts", ["node_id"])
    op.create_index("ix_operator_alerts_operator", "operator_alerts", ["operator_id"])

    # --- D2: invoices ---
    op.create_table(
        "invoices",
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(length=50), nullable=False),
        sa.Column("subscription_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subscription_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("unit_price_usd", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("subtotal_usd", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("subtotal_mwk", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tax_usd", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("tax_mwk", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("total_usd", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_mwk", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("line_items", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_invoices_buyer", "invoices", ["buyer_id"])

    # --- D3: subject_rewards ---
    op.create_table(
        "subject_rewards",
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("total_airtime_mwk", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("pending_airtime_mwk", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0.00"),
        sa.Column("last_payout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payout_method", sa.String(length=20), nullable=False, server_default="airtime"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subject_rewards_hash", "subject_rewards", ["subject_hash"], unique=True)
    op.create_index("ix_subject_rewards_phone", "subject_rewards", ["phone_number"])

    # --- D4.2: Performance indexes for dashboard queries ---
    # ix_heartbeats_node_created and ix_annotations_dataset_id already exist;
    # only create the consent_ledger composite index and a covering annotation index.
    op.create_index(
        "ix_annotations_status_time",
        "annotations",
        ["dataset_id", "status", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_consent_ledger_subject_status",
        "consent_ledger",
        ["subject_hash", "status", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_consent_ledger_subject_status", table_name="consent_ledger")
    op.drop_index("ix_annotations_status_time", table_name="annotations")
    op.drop_index("ix_subject_rewards_phone", table_name="subject_rewards")
    op.drop_index("ix_subject_rewards_hash", table_name="subject_rewards")
    op.drop_table("subject_rewards")
    op.drop_index("ix_invoices_buyer", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index("ix_operator_alerts_operator", table_name="operator_alerts")
    op.drop_index("ix_operator_alerts_node", table_name="operator_alerts")
    op.drop_table("operator_alerts")
    op.drop_index("ix_operator_payouts_operator", table_name="operator_payouts")
    op.drop_table("operator_payouts")
    op.drop_index("ix_operator_accounts_node", table_name="operator_accounts")
    op.drop_index("ix_operator_accounts_phone", table_name="operator_accounts")
    op.drop_table("operator_accounts")
