"""Add activation tables: events, scenario_cards, synthetic_scenarios,
fl_sync_rounds, fl_model_distributions, annotator_payouts, subject_rewards,
compliance_audit_log, sms_log.

These tables were created via Python scripts in earlier sessions.
This migration formalises them in the Alembic chain with proper DDL.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-18
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, table_name: str) -> bool:
    """Check if a table already exists in the public schema."""
    from sqlalchemy import inspect

    inspector = inspect(conn)
    return table_name in inspector.get_table_names(schema="public")


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------
    if not _table_exists(conn, "events"):
        op.create_table(
            "events",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("node_id", sa.String(length=32), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("confidence", sa.Float(), server_default=sa.text("0.0"), nullable=False),
            sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("image_path", sa.Text(), nullable=True),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_events_node_id_timestamp", "events", ["node_id", sa.text("timestamp DESC")])
        op.create_index("ix_events_event_type", "events", ["event_type"])
        op.create_index("ix_events_created_at", "events", ["created_at"])

    # ------------------------------------------------------------------
    # scenario_cards
    # ------------------------------------------------------------------
    if not _table_exists(conn, "scenario_cards"):
        op.create_table(
            "scenario_cards",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("scenario_type", sa.String(length=64), nullable=False),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("severity", sa.String(length=16), server_default=sa.text("'info'::character varying"), nullable=False),
            sa.Column("node_id", sa.String(length=32), nullable=False),
            sa.Column("image_path", sa.Text(), nullable=True),
            sa.Column("detections", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
            sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("exported", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_scenario_cards_node_id", "scenario_cards", ["node_id"])
        op.create_index("ix_scenario_cards_severity", "scenario_cards", ["severity"])
        op.create_index("ix_scenario_cards_created_at", "scenario_cards", ["created_at"])

    # ------------------------------------------------------------------
    # synthetic_scenarios
    # ------------------------------------------------------------------
    if not _table_exists(conn, "synthetic_scenarios"):
        op.create_table(
            "synthetic_scenarios",
            sa.Column("id", sa.String(length=128), nullable=False),
            sa.Column("source_path", sa.String(length=512), nullable=True),
            sa.Column("augmentations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("output_path", sa.String(length=512), nullable=True),
            sa.Column("quality_score", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    # ------------------------------------------------------------------
    # fl_sync_rounds
    # ------------------------------------------------------------------
    if not _table_exists(conn, "fl_sync_rounds"):
        op.create_table(
            "fl_sync_rounds",
            sa.Column("id", sa.String(length=128), nullable=False),
            sa.Column("model_type", sa.String(length=64), nullable=True),
            sa.Column("base_model_version", sa.String(length=128), nullable=True),
            sa.Column("aggregated_model_version", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=True),
            sa.Column("num_contributors", sa.Integer(), nullable=True),
            sa.Column("target_contributors", sa.Integer(), nullable=True),
            sa.Column("aggregation_method", sa.String(length=32), nullable=True),
            sa.Column("noise_multiplier", sa.Float(), nullable=True),
            sa.Column("learning_rate", sa.Float(), nullable=True),
            sa.Column("global_loss", sa.Float(), nullable=True),
            sa.Column("global_accuracy", sa.Float(), nullable=True),
            sa.Column("artifact_path", sa.String(length=512), nullable=True),
            sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_fl_sync_rounds_status", "fl_sync_rounds", ["status"])
        op.create_index("ix_fl_sync_rounds_created_at", "fl_sync_rounds", ["created_at"])

    # ------------------------------------------------------------------
    # fl_model_distributions
    # ------------------------------------------------------------------
    if not _table_exists(conn, "fl_model_distributions"):
        op.create_table(
            "fl_model_distributions",
            sa.Column("id", sa.String(length=128), nullable=False),
            sa.Column("round_id", sa.String(length=128), nullable=True),
            sa.Column("node_id", sa.String(length=32), nullable=True),
            sa.Column("model_version", sa.String(length=128), nullable=True),
            sa.Column("artifact_path", sa.String(length=512), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("bandwidth_mbps", sa.Float(), nullable=True),
            sa.Column("node_validation_score", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_fl_model_distributions_round_id", "fl_model_distributions", ["round_id"])
        op.create_index("ix_fl_model_distributions_node_id", "fl_model_distributions", ["node_id"])

    # ------------------------------------------------------------------
    # annotator_payouts
    # ------------------------------------------------------------------
    if not _table_exists(conn, "annotator_payouts"):
        op.create_table(
            "annotator_payouts",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("annotator_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("amount_mwk", sa.Numeric(), nullable=True),
            sa.Column("annotation_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=16), server_default=sa.text("'pending'::character varying"), nullable=False),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_annotator_payouts_annotator_id", "annotator_payouts", ["annotator_id"])
        op.create_index("ix_annotator_payouts_status", "annotator_payouts", ["status"])

    # ------------------------------------------------------------------
    # subject_rewards
    # ------------------------------------------------------------------
    if not _table_exists(conn, "subject_rewards"):
        op.create_table(
            "subject_rewards",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("subject_hash", sa.String(length=128), nullable=True),
            sa.Column("phone_number", sa.String(length=32), nullable=True),
            sa.Column("total_airtime_mwk", sa.Numeric(), server_default=sa.text("0.00"), nullable=False),
            sa.Column("pending_airtime_mwk", sa.Numeric(), server_default=sa.text("0.00"), nullable=False),
            sa.Column("last_payout_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("payout_method", sa.String(length=16), server_default=sa.text("'airtime'::character varying"), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_subject_rewards_subject_hash", "subject_rewards", ["subject_hash"])

    # ------------------------------------------------------------------
    # compliance_audit_log
    # ------------------------------------------------------------------
    if not _table_exists(conn, "compliance_audit_log"):
        op.create_table(
            "compliance_audit_log",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("audit_type", sa.String(length=64), nullable=True),
            sa.Column("subject_hash", sa.String(length=128), nullable=True),
            sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("status", sa.String(length=16), server_default=sa.text("'pass'::character varying"), nullable=False),
            sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
            sa.Column("scanned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_compliance_audit_log_subject_hash", "compliance_audit_log", ["subject_hash"])
        op.create_index("ix_compliance_audit_log_created_at", "compliance_audit_log", ["created_at"])

    # ------------------------------------------------------------------
    # sms_log
    # ------------------------------------------------------------------
    if not _table_exists(conn, "sms_log"):
        op.create_table(
            "sms_log",
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("recipient_hash", sa.String(length=128), nullable=True),
            sa.Column("phone_last4", sa.String(length=4), nullable=True),
            sa.Column("message_type", sa.String(length=32), nullable=True),
            sa.Column("message_text", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=16), server_default=sa.text("'pending'::character varying"), nullable=False),
            sa.Column("provider_response", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_sms_log_recipient_hash", "sms_log", ["recipient_hash"])
        op.create_index("ix_sms_log_created_at", "sms_log", ["created_at"])


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "sms_log"):
        op.drop_index("ix_sms_log_created_at", table_name="sms_log")
        op.drop_index("ix_sms_log_recipient_hash", table_name="sms_log")
        op.drop_table("sms_log")

    if _table_exists(conn, "compliance_audit_log"):
        op.drop_index("ix_compliance_audit_log_created_at", table_name="compliance_audit_log")
        op.drop_index("ix_compliance_audit_log_subject_hash", table_name="compliance_audit_log")
        op.drop_table("compliance_audit_log")

    if _table_exists(conn, "subject_rewards"):
        op.drop_index("ix_subject_rewards_subject_hash", table_name="subject_rewards")
        op.drop_table("subject_rewards")

    if _table_exists(conn, "annotator_payouts"):
        op.drop_index("ix_annotator_payouts_status", table_name="annotator_payouts")
        op.drop_index("ix_annotator_payouts_annotator_id", table_name="annotator_payouts")
        op.drop_table("annotator_payouts")

    if _table_exists(conn, "fl_model_distributions"):
        op.drop_index("ix_fl_model_distributions_node_id", table_name="fl_model_distributions")
        op.drop_index("ix_fl_model_distributions_round_id", table_name="fl_model_distributions")
        op.drop_table("fl_model_distributions")

    if _table_exists(conn, "fl_sync_rounds"):
        op.drop_index("ix_fl_sync_rounds_created_at", table_name="fl_sync_rounds")
        op.drop_index("ix_fl_sync_rounds_status", table_name="fl_sync_rounds")
        op.drop_table("fl_sync_rounds")

    if _table_exists(conn, "synthetic_scenarios"):
        op.drop_table("synthetic_scenarios")

    if _table_exists(conn, "scenario_cards"):
        op.drop_index("ix_scenario_cards_created_at", table_name="scenario_cards")
        op.drop_index("ix_scenario_cards_severity", table_name="scenario_cards")
        op.drop_index("ix_scenario_cards_node_id", table_name="scenario_cards")
        op.drop_table("scenario_cards")

    if _table_exists(conn, "events"):
        op.drop_index("ix_events_created_at", table_name="events")
        op.drop_index("ix_events_event_type", table_name="events")
        op.drop_index("ix_events_node_id_timestamp", table_name="events")
        op.drop_table("events")
