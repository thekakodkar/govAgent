"""Ledger rows are append-only, and roles can carry SCIM labels.

Revision ID: 20261108_0007
Revises: 20261107_0006

Expand only. UPDATE and DELETE are revoked from govagent_app on the ledger,
matching audit_events. Copies of those tables inside a tenant_<uuid> schema,
if any exist, get the same revoke.
"""

from __future__ import annotations

from alembic import op

revision = "20261108_0007"
down_revision = "20261107_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE roles ADD COLUMN display_name text")
    op.execute("ALTER TABLE roles ADD COLUMN external_id text")
    op.execute("REVOKE UPDATE, DELETE ON fiscal_ledger_entries FROM govagent_app")
    op.execute(
        """
        DO $$
        DECLARE
            sch text;
            rel text;
        BEGIN
            FOR sch IN
                SELECT nspname FROM pg_namespace WHERE nspname LIKE 'tenant_%'
            LOOP
                FOREACH rel IN ARRAY ARRAY['fiscal_ledger_entries', 'audit_events']
                LOOP
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = sch AND table_name = rel
                    ) THEN
                        EXECUTE format(
                            'REVOKE UPDATE, DELETE ON %I.%I FROM govagent_app',
                            sch,
                            rel
                        );
                    END IF;
                END LOOP;
            END LOOP;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON fiscal_ledger_entries TO govagent_app")
    op.execute("ALTER TABLE roles DROP COLUMN IF EXISTS external_id")
    op.execute("ALTER TABLE roles DROP COLUMN IF EXISTS display_name")
