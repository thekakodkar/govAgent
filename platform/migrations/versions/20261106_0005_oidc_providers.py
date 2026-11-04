"""OIDC provider registry. The secret column stores a locator, not a secret.

Revision ID: 20261106_0005
Revises: 20261105_0004
"""

from __future__ import annotations

from alembic import op

revision = "20261106_0005"
down_revision = "20261105_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE oidc_providers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid REFERENCES tenants(id) ON DELETE RESTRICT,
            issuer text NOT NULL,
            client_id text NOT NULL,
            client_secret_locator text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE oidc_providers OWNER TO govagent_owner")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON oidc_providers TO govagent_app")
    op.execute("ALTER TABLE oidc_providers ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE oidc_providers FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY oidc_providers_read ON oidc_providers
        FOR SELECT
        USING (
            current_setting('app.actor_scope', true) IN ('platform', 'authenticate')
            OR tenant_id IS NULL
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )
    op.execute(
        """
        CREATE POLICY oidc_providers_write ON oidc_providers
        FOR INSERT
        WITH CHECK (
            current_setting('app.actor_scope', true) = 'platform'
            OR (
                tenant_id IS NOT NULL
                AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY oidc_providers_update ON oidc_providers
        FOR UPDATE
        USING (
            current_setting('app.actor_scope', true) = 'platform'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.actor_scope', true) = 'platform'
            OR (
                tenant_id IS NOT NULL
                AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY oidc_providers_delete ON oidc_providers
        FOR DELETE
        USING (
            current_setting('app.actor_scope', true) = 'platform'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS oidc_providers_delete ON oidc_providers")
    op.execute("DROP POLICY IF EXISTS oidc_providers_update ON oidc_providers")
    op.execute("DROP POLICY IF EXISTS oidc_providers_write ON oidc_providers")
    op.execute("DROP POLICY IF EXISTS oidc_providers_read ON oidc_providers")
    op.execute("ALTER TABLE oidc_providers NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE oidc_providers DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS oidc_providers")
