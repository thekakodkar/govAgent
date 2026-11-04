"""Dedicated-schema bookkeeping and the snapshot archive.

Revision ID: 20261107_0006
Revises: 20261106_0005

Expand only. Audit and ledger tables are not altered.
"""

from __future__ import annotations

from alembic import op

revision = "20261107_0006"
down_revision = "20261106_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenants ADD COLUMN schema_name text")
    op.execute(
        """
        CREATE TABLE isolation_promotions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            from_tier varchar(32) NOT NULL,
            to_tier varchar(32) NOT NULL,
            schema_name text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE retention_archives (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            source_table varchar(64) NOT NULL,
            source_id uuid NOT NULL,
            payload jsonb NOT NULL,
            archived_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    for table in ("isolation_promotions", "retention_archives"):
        op.execute(f"ALTER TABLE {table} OWNER TO govagent_owner")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute("GRANT SELECT, INSERT ON isolation_promotions TO govagent_app")
    op.execute("GRANT SELECT, INSERT ON retention_archives TO govagent_app")
    op.execute(
        """
        CREATE POLICY isolation_promotions_read ON isolation_promotions
        FOR SELECT
        USING (
            current_setting('app.actor_scope', true) = 'platform'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )
    op.execute(
        """
        CREATE POLICY isolation_promotions_insert ON isolation_promotions
        FOR INSERT
        WITH CHECK (current_setting('app.actor_scope', true) = 'platform')
        """
    )
    op.execute(
        """
        CREATE POLICY retention_archives_read ON retention_archives
        FOR SELECT
        USING (
            (
                current_setting('app.actor_scope', true) = 'platform'
                AND current_setting('app.platform_break_glass', true) = 'on'
            )
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )
    op.execute(
        """
        CREATE POLICY retention_archives_insert ON retention_archives
        FOR INSERT
        WITH CHECK (
            (
                current_setting('app.actor_scope', true) = 'platform'
                AND current_setting('app.platform_break_glass', true) = 'on'
            )
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            dbname text := current_database();
        BEGIN
            EXECUTE format('GRANT CREATE ON DATABASE %I TO govagent_app', dbname);
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS retention_archives_insert ON retention_archives")
    op.execute("DROP POLICY IF EXISTS retention_archives_read ON retention_archives")
    op.execute("DROP POLICY IF EXISTS isolation_promotions_insert ON isolation_promotions")
    op.execute("DROP POLICY IF EXISTS isolation_promotions_read ON isolation_promotions")
    op.execute("DROP TABLE IF EXISTS retention_archives")
    op.execute("DROP TABLE IF EXISTS isolation_promotions")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS schema_name")
