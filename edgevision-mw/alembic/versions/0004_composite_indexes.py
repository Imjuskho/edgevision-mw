"""Add composite indexes for common query patterns.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-25
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_heartbeats_node_created",
        "heartbeats",
        ["node_id", "created_at"],
    )
    op.create_index(
        "ix_annotations_status_annotator",
        "annotations",
        ["status", "annotator_id"],
    )
    op.create_index(
        "ix_consent_ledger_subject_status",
        "consent_ledger",
        ["subject_hash", "status"],
    )
    op.create_index(
        "ix_exports_buyer_completed",
        "exports",
        ["buyer_id", "completed_at"],
    )
    op.create_index(
        "ix_audit_logs_event_created",
        "audit_logs",
        ["event_type", "created_at"],
    )
    op.create_index(
        "ix_datasets_status_license",
        "datasets",
        ["status", "license_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_datasets_status_license", table_name="datasets")
    op.drop_index("ix_audit_logs_event_created", table_name="audit_logs")
    op.drop_index("ix_exports_buyer_completed", table_name="exports")
    op.drop_index("ix_consent_ledger_subject_status", table_name="consent_ledger")
    op.drop_index("ix_annotations_status_annotator", table_name="annotations")
    op.drop_index("ix_heartbeats_node_created", table_name="heartbeats")
