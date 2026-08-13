"""Create Studio tables for EdgeVision Studio annotation platform.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, UUID

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

UUID_PK = lambda: UUID(as_uuid=True, primary_key=True, server_default=sa.text("gen_random_uuid()"))
TS_CREATED = lambda: sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
TS_UPDATED = lambda: sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "annotation_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("image_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("annotations_created", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        TS_CREATED(),
        TS_UPDATED(),
    )

    op.create_table(
        "annotation_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("annotation_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("annotation_id", UUID(as_uuid=True), sa.ForeignKey("annotations.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("image_index", sa.Integer, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        TS_CREATED(),
        TS_UPDATED(),
    )

    op.create_table(
        "image_embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("image_path", sa.String(500), nullable=False),
        sa.Column("annotation_id", UUID(as_uuid=True), sa.ForeignKey("annotations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("embedding", JSONB, nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        TS_CREATED(),
        TS_UPDATED(),
    )
    op.create_index("ix_image_embeddings_image_path", "image_embeddings", ["image_path"])

    op.create_table(
        "duplicate_groups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("similarity_score", sa.Float, nullable=False),
        sa.Column("strategy", sa.String(50), nullable=False),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("resolution_action", sa.String(50), nullable=True),
        TS_CREATED(),
        TS_UPDATED(),
    )

    op.create_table(
        "duplicate_group_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("duplicate_groups.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("annotation_id", UUID(as_uuid=True), sa.ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        TS_CREATED(),
        TS_UPDATED(),
    )

    op.create_table(
        "dataset_health_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("overall_score", sa.Float, nullable=False),
        sa.Column("completeness_pct", sa.Float, nullable=False),
        sa.Column("consistency_pct", sa.Float, nullable=False),
        sa.Column("accuracy_pct", sa.Float, nullable=False),
        sa.Column("timeliness_pct", sa.Float, nullable=False),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("recommendations", ARRAY(sa.Text), nullable=True),
        TS_CREATED(),
        TS_UPDATED(),
    )

    op.create_table(
        "export_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("include_images", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("include_annotations", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("include_metadata", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("download_url", sa.String(1000), nullable=True),
        sa.Column("progress_pct", sa.Float, nullable=False, server_default=sa.text("0.0")),
        sa.Column("error_message", sa.Text, nullable=True),
        TS_CREATED(),
        TS_UPDATED(),
    )

    op.create_table(
        "consent_zones",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("geometry", JSONB, nullable=False),
        sa.Column("consent_id", UUID(as_uuid=True), sa.ForeignKey("consent_ledger.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        TS_CREATED(),
        TS_UPDATED(),
    )
    op.create_index("ix_consent_zones_consent_id", "consent_zones", ["consent_id"])


def downgrade() -> None:
    op.drop_table("consent_zones")
    op.drop_table("export_jobs")
    op.drop_table("dataset_health_snapshots")
    op.drop_table("duplicate_group_members")
    op.drop_table("duplicate_groups")
    op.drop_index("ix_image_embeddings_image_path", table_name="image_embeddings")
    op.drop_table("image_embeddings")
    op.drop_table("annotation_actions")
    op.drop_table("annotation_sessions")
