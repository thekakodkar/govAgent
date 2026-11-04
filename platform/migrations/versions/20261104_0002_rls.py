"""Force row-level security for the app role.

Revision ID: 20261104_0002
Revises: 20261104_0001
"""

from __future__ import annotations

from alembic import op

revision = "20261104_0002"
down_revision = "20261104_0001"
branch_labels = None
depends_on = None

_TENANT_TABLES = (
    "roles",
    "tenant_memberships",
    "membership_roles",
    "tenant_policies",
    "agents",
    "tool_manifests",
    "approval_requests",
    "approval_signatures",
    "execution_snapshots",
    "fiscal_ledger_entries",
    "telemetry_sinks",
    "cost_centers",
    "secret_refs",
    "audit_events",
)

_PAYLOAD_TABLES = (
    "tenant_policies",
    "agents",
    "tool_manifests",
    "approval_requests",
    "approval_signatures",
    "execution_snapshots",
    "fiscal_ledger_entries",
    "telemetry_sinks",
    "cost_centers",
    "secret_refs",
)

_CATALOG_RLS = ("tenants", "plans", "global_policies")


def _exec_sql(sql: str) -> None:
    for statement in sql.split(";"):
        stmt = statement.strip()
        if stmt:
            op.execute(stmt)


def upgrade() -> None:
    for table in _TENANT_TABLES + _CATALOG_RLS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    for table in _PAYLOAD_TABLES:
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            FOR ALL
            USING (
                (
                    current_setting('app.actor_scope', true) = 'platform'
                    AND current_setting('app.platform_break_glass', true) = 'on'
                )
                OR {table}.tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            WITH CHECK (
                {table}.tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            """
        )

    _exec_sql(
        """
        CREATE POLICY roles_read ON roles
        FOR SELECT
        USING (
            tenant_id IS NULL
            OR current_setting('app.actor_scope', true) IN ('platform', 'authenticate')
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        );

        CREATE POLICY roles_write ON roles
        FOR INSERT
        WITH CHECK (
            current_setting('app.actor_scope', true) = 'platform'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        );

        CREATE POLICY roles_update ON roles
        FOR UPDATE
        USING (
            current_setting('app.actor_scope', true) = 'platform'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.actor_scope', true) = 'platform'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        );

        CREATE POLICY roles_delete ON roles
        FOR DELETE
        USING (
            current_setting('app.actor_scope', true) = 'platform'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        );

        CREATE POLICY memberships_isolation ON tenant_memberships
        FOR ALL
        USING (
            current_setting('app.actor_scope', true) IN ('platform', 'authenticate')
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.actor_scope', true) = 'platform'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        );

        CREATE POLICY membership_roles_isolation ON membership_roles
        FOR ALL
        USING (
            current_setting('app.actor_scope', true) IN ('platform', 'authenticate')
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.actor_scope', true) = 'platform'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        );

        CREATE POLICY audit_events_isolation ON audit_events
        FOR ALL
        USING (
            tenant_id IS NOT DISTINCT FROM NULLIF(current_setting('app.tenant_id', true), '')::uuid
            OR (
                current_setting('app.actor_scope', true) = 'platform'
                AND (
                    tenant_id IS NULL
                    OR current_setting('app.platform_break_glass', true) = 'on'
                )
            )
        )
        WITH CHECK (
            current_setting('app.actor_scope', true) = 'platform'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        );

        CREATE POLICY tenants_select ON tenants
        FOR SELECT
        USING (
            current_setting('app.actor_scope', true) IN ('platform', 'authenticate')
            OR id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        );

        CREATE POLICY tenants_insert ON tenants
        FOR INSERT
        WITH CHECK (current_setting('app.actor_scope', true) = 'platform');

        CREATE POLICY tenants_update ON tenants
        FOR UPDATE
        USING (current_setting('app.actor_scope', true) = 'platform')
        WITH CHECK (current_setting('app.actor_scope', true) = 'platform');

        CREATE POLICY tenants_delete ON tenants
        FOR DELETE
        USING (current_setting('app.actor_scope', true) = 'platform');

        CREATE POLICY plans_select ON plans
        FOR SELECT
        USING (true);

        CREATE POLICY plans_write ON plans
        FOR INSERT
        WITH CHECK (current_setting('app.actor_scope', true) = 'platform');

        CREATE POLICY plans_update ON plans
        FOR UPDATE
        USING (current_setting('app.actor_scope', true) = 'platform')
        WITH CHECK (current_setting('app.actor_scope', true) = 'platform');

        CREATE POLICY plans_delete ON plans
        FOR DELETE
        USING (current_setting('app.actor_scope', true) = 'platform');

        CREATE POLICY global_policies_select ON global_policies
        FOR SELECT
        USING (true);

        CREATE POLICY global_policies_insert ON global_policies
        FOR INSERT
        WITH CHECK (current_setting('app.actor_scope', true) = 'platform');

        CREATE POLICY global_policies_update ON global_policies
        FOR UPDATE
        USING (current_setting('app.actor_scope', true) = 'platform')
        WITH CHECK (current_setting('app.actor_scope', true) = 'platform');

        CREATE POLICY global_policies_delete ON global_policies
        FOR DELETE
        USING (current_setting('app.actor_scope', true) = 'platform');
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON audit_events FROM govagent_app")


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON audit_events TO govagent_app")
    policies = [
        "roles_read",
        "roles_write",
        "roles_update",
        "roles_delete",
        "memberships_isolation",
        "membership_roles_isolation",
        "audit_events_isolation",
        "tenants_select",
        "tenants_insert",
        "tenants_update",
        "tenants_delete",
        "plans_select",
        "plans_write",
        "plans_update",
        "plans_delete",
        "global_policies_select",
        "global_policies_insert",
        "global_policies_update",
        "global_policies_delete",
    ]
    tables_for_named = {
        "roles_read": "roles",
        "roles_write": "roles",
        "roles_update": "roles",
        "roles_delete": "roles",
        "memberships_isolation": "tenant_memberships",
        "membership_roles_isolation": "membership_roles",
        "audit_events_isolation": "audit_events",
        "tenants_select": "tenants",
        "tenants_insert": "tenants",
        "tenants_update": "tenants",
        "tenants_delete": "tenants",
        "plans_select": "plans",
        "plans_write": "plans",
        "plans_update": "plans",
        "plans_delete": "plans",
        "global_policies_select": "global_policies",
        "global_policies_insert": "global_policies",
        "global_policies_update": "global_policies",
        "global_policies_delete": "global_policies",
    }
    for name in policies:
        op.execute(f"DROP POLICY IF EXISTS {name} ON {tables_for_named[name]}")
    for table in _PAYLOAD_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    for table in _TENANT_TABLES + _CATALOG_RLS:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
