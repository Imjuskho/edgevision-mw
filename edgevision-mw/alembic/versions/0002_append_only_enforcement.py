"""append-only enforcement for consent_ledger and audit_logs

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-25 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Phase 1.3: Drop updated_at from audit_logs
    op.drop_column("audit_logs", "updated_at")

    # Phase 1.2: Consent ledger append-only triggers
    op.execute("""
        CREATE OR REPLACE FUNCTION block_consent_ledger_update()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'consent_ledger is append-only: UPDATE is not permitted';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_block_consent_update ON consent_ledger")
    op.execute("""
        CREATE TRIGGER trg_block_consent_update
            BEFORE UPDATE ON consent_ledger
            FOR EACH ROW
            EXECUTE FUNCTION block_consent_ledger_update()
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION block_consent_ledger_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'consent_ledger is append-only: DELETE is not permitted';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_block_consent_delete ON consent_ledger")
    op.execute("""
        CREATE TRIGGER trg_block_consent_delete
            BEFORE DELETE ON consent_ledger
            FOR EACH ROW
            EXECUTE FUNCTION block_consent_ledger_delete()
    """)

    # Phase 1.3: Audit logs append-only triggers
    op.execute("""
        CREATE OR REPLACE FUNCTION block_audit_logs_update()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only: UPDATE is not permitted';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_block_audit_update ON audit_logs")
    op.execute("""
        CREATE TRIGGER trg_block_audit_update
            BEFORE UPDATE ON audit_logs
            FOR EACH ROW
            EXECUTE FUNCTION block_audit_logs_update()
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION block_audit_logs_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only: DELETE is not permitted';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_block_audit_delete ON audit_logs")
    op.execute("""
        CREATE TRIGGER trg_block_audit_delete
            BEFORE DELETE ON audit_logs
            FOR EACH ROW
            EXECUTE FUNCTION block_audit_logs_delete()
    """)


def downgrade() -> None:
    # Remove triggers
    op.execute("DROP TRIGGER IF EXISTS trg_block_audit_delete ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_block_audit_update ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS block_audit_logs_delete()")
    op.execute("DROP FUNCTION IF EXISTS block_audit_logs_update()")

    op.execute("DROP TRIGGER IF EXISTS trg_block_consent_delete ON consent_ledger")
    op.execute("DROP TRIGGER IF EXISTS trg_block_consent_update ON consent_ledger")
    op.execute("DROP FUNCTION IF EXISTS block_consent_ledger_delete()")
    op.execute("DROP FUNCTION IF EXISTS block_consent_ledger_update()")

    # Restore updated_at on audit_logs
    op.add_column(
        "audit_logs",
        op.f("updated_at"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
