"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY


# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- nodes ---
    op.create_table(
        "nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("node_id", sa.String(20), unique=True, index=True, nullable=False),
        sa.Column("district", sa.String(100), nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("hardware_profile", JSONB, nullable=False),
        sa.Column("network_config", JSONB, nullable=False),
        sa.Column("capture_schedule", sa.String(50), nullable=False),
        sa.Column("interest_classes", ARRAY(sa.String), nullable=False),
        sa.Column("pii_mode", sa.String(20), nullable=False),
        sa.Column("firmware_version", sa.String(20), nullable=False),
        sa.Column("public_key", sa.LargeBinary, nullable=False),
        sa.Column("status", sa.String(20), server_default="ONLINE", nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_enabled", sa.Boolean, server_default="true", nullable=False),
    )

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("email", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("organization", sa.String(200), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("api_key_hash", sa.String(64), unique=True, nullable=True),
        sa.Column("jurisdiction", sa.String(10), nullable=True),
        sa.Column("dpa_signed", sa.Boolean, server_default="false", nullable=False),
        sa.Column("dpa_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credit_balance_usd", sa.Numeric(12, 2), server_default="0.0", nullable=False),
    )

    # --- heartbeats ---
    op.create_table(
        "heartbeats",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("node_id", UUID(as_uuid=True), sa.ForeignKey("nodes.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("battery_voltage", sa.Float, nullable=False),
        sa.Column("solar_input_watts", sa.Float, nullable=False),
        sa.Column("cpu_temp_celsius", sa.Float, nullable=False),
        sa.Column("gpu_utilization", sa.Float, nullable=False),
        sa.Column("storage_used_gb", sa.Float, nullable=False),
        sa.Column("storage_total_gb", sa.Float, nullable=False),
        sa.Column("lte_rssi_dbm", sa.Float, nullable=False),
        sa.Column("camera_status", sa.String(20), nullable=False),
        sa.Column("clock_drift_ms", sa.Float, nullable=False),
        sa.Column("events_captured", sa.Integer, nullable=False),
        sa.Column("events_uploaded", sa.Integer, nullable=False),
        sa.Column("bandwidth_mbps", sa.Float, nullable=False),
        sa.Column("raw_diagnostics", JSONB, nullable=True),
    )

    # --- ingestion_batches ---
    op.create_table(
        "ingestion_batches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("batch_id", sa.String(50), unique=True, nullable=False),
        sa.Column("node_id", UUID(as_uuid=True), sa.ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hub_id", sa.String(20), nullable=False),
        sa.Column("event_count", sa.Integer, nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("node_signature", sa.LargeBinary, nullable=False),
        sa.Column("compression_codec", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("validation_errors", JSONB, nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=True),
        sa.Column("quality_scores", JSONB, nullable=False),
    )

    # --- datasets ---
    op.create_table(
        "datasets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("dataset_id", sa.String(36), unique=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="BUILDING", nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("classes", JSONB, nullable=False),
        sa.Column("annotations_per_image", sa.Float, nullable=False),
        sa.Column("image_width", sa.Integer, nullable=False),
        sa.Column("image_height", sa.Integer, nullable=False),
        sa.Column("geographic_coverage", JSONB, nullable=False),
        sa.Column("demographic_report", JSONB, nullable=False),
        sa.Column("consent_coverage_pct", sa.Float, nullable=False),
        sa.Column("pii_scrub_verified", sa.Boolean, server_default="false", nullable=False),
        sa.Column("iaa_score", sa.Float, nullable=False),
        sa.Column("formats", ARRAY(sa.String), nullable=False),
        sa.Column("buyer_fingerprint", sa.String(128), nullable=True),
        sa.Column("price_usd", sa.Float, nullable=False),
        sa.Column("license_type", sa.String(20), nullable=False),
        sa.Column("buyer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
    )

    # --- annotations ---
    op.create_table(
        "annotations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("batch_id", UUID(as_uuid=True), sa.ForeignKey("ingestion_batches.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("image_index", sa.Integer, nullable=False),
        sa.Column("image_path", sa.String(500), nullable=False),
        sa.Column("thumbnail_path", sa.String(500), nullable=False),
        sa.Column("gps_lat", sa.Float, nullable=True),
        sa.Column("gps_lon", sa.Float, nullable=True),
        sa.Column("detected_objects", JSONB, nullable=False),
        sa.Column("auto_labels", JSONB, nullable=False),
        sa.Column("human_labels", JSONB, nullable=True),
        sa.Column("qa_labels", JSONB, nullable=True),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("quality_score", sa.Float, nullable=False),
        sa.Column("iaa_score", sa.Float, nullable=True),
        sa.Column("annotator_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("qa_reviewer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_certified", sa.Boolean, server_default="false", nullable=False),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="SET NULL"), index=True, nullable=True),
    )

    # --- annotation_assignments ---
    op.create_table(
        "annotation_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("annotation_id", UUID(as_uuid=True), sa.ForeignKey("annotations.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("annotator_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
    )

    # --- consent_ledger ---
    op.create_table(
        "consent_ledger",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("subject_hash", sa.String(64), index=True, nullable=False),
        sa.Column("tx_hash", sa.String(128), unique=True, nullable=False),
        sa.Column("purposes", ARRAY(sa.String), nullable=False),
        sa.Column("media_types", ARRAY(sa.String), nullable=False),
        sa.Column("geography_restrictions", ARRAY(sa.String), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expiry", sa.DateTime(timezone=True), nullable=False),
        sa.Column("guardian_hash", sa.String(64), nullable=True),
        sa.Column("signature_bytes", sa.LargeBinary, nullable=False),
        sa.Column("status", sa.String(20), server_default="ACTIVE", nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- exports ---
    op.create_table(
        "exports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("datasets.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("buyer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("license_key", sa.String(128), unique=True, nullable=False),
        sa.Column("license_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("price_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_ref", sa.String(200), nullable=True),
        sa.Column("delivery_url", sa.String(500), nullable=True),
        sa.Column("delivery_confirmed", sa.Boolean, server_default="false", nullable=False),
        sa.Column("watermark_fingerprint", sa.String(128), nullable=False),
        sa.Column("formats_delivered", ARRAY(sa.String), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_rights", JSONB, nullable=False),
    )

    # --- export_logs ---
    op.create_table(
        "export_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("export_id", UUID(as_uuid=True), sa.ForeignKey("exports.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("details", JSONB, nullable=True),
    )

    # --- buyer_api_keys ---
    op.create_table(
        "buyer_api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("scopes", ARRAY(sa.String), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("event_type", sa.String(50), index=True, nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True), nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("buyer_api_keys")
    op.drop_table("export_logs")
    op.drop_table("exports")
    op.drop_table("consent_ledger")
    op.drop_table("annotation_assignments")
    op.drop_table("annotations")
    op.drop_table("datasets")
    op.drop_table("ingestion_batches")
    op.drop_table("heartbeats")
    op.drop_table("users")
    op.drop_table("nodes")
