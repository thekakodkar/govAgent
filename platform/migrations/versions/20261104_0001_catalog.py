"""Catalog tables, roles, and grants.

Revision ID: 20261104_0001
Revises:
Create Date: 2026-11-04
"""

from __future__ import annotations

import os

from alembic import op

revision = "20261104_0001"
down_revision = None
branch_labels = None
depends_on = None


def _exec_sql(sql: str) -> None:
    for statement in sql.split(";"):
        stmt = statement.strip()
        if stmt:
            op.execute(stmt)


def _password(env_name: str, default: str) -> str:
    raw = os.environ.get(env_name, default)
    if not raw or any(ch in raw for ch in " '\n\r\t\\"):
        raise RuntimeError(f"{env_name} must be a non-empty password without quotes or whitespace")
    return raw


def upgrade() -> None:
    owner_password = _password("PLATFORM_OWNER_PASSWORD", "govagent_owner_local")
    app_password = _password("PLATFORM_APP_PASSWORD", "govagent_app_local")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'govagent_owner') THEN
                CREATE ROLE govagent_owner
                    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'govagent_app') THEN
                CREATE ROLE govagent_app
                    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
            END IF;
        END
        $$
        """
    )
    op.execute(f"ALTER ROLE govagent_owner WITH LOGIN PASSWORD '{owner_password}'")
    op.execute(f"ALTER ROLE govagent_app WITH LOGIN PASSWORD '{app_password}'")
    op.execute("ALTER ROLE govagent_owner NOBYPASSRLS NOSUPERUSER")
    op.execute("ALTER ROLE govagent_app NOBYPASSRLS NOSUPERUSER NOINHERIT")
    op.execute(
        """
        DO $$
        DECLARE
            dbname text := current_database();
        BEGIN
            EXECUTE format(
                'GRANT CONNECT ON DATABASE %I TO govagent_owner, govagent_app',
                dbname
            );
        END
        $$
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO govagent_owner, govagent_app")

    _exec_sql(
        """
        CREATE TABLE plans (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            code varchar(64) NOT NULL UNIQUE,
            name varchar(200) NOT NULL,
            max_agents integer NOT NULL,
            monthly_tco_ceiling_usd numeric(18, 6) NOT NULL,
            retention_days integer NOT NULL,
            features jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE tenants (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            slug varchar(64) NOT NULL UNIQUE,
            display_name varchar(200) NOT NULL,
            status varchar(32) NOT NULL DEFAULT 'active',
            plan_id uuid NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
            isolation_tier varchar(32) NOT NULL DEFAULT 'shared',
            region varchar(64),
            created_at timestamptz NOT NULL DEFAULT now(),
            suspended_at timestamptz,
            CONSTRAINT ck_tenants_status CHECK (status IN ('active', 'suspended')),
            CONSTRAINT ck_tenants_isolation_tier CHECK (
                isolation_tier IN ('shared', 'dedicated_schema', 'dedicated_db')
            )
        );

        CREATE TABLE identities (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email varchar(320) NOT NULL UNIQUE,
            display_name varchar(200) NOT NULL,
            password_hash text,
            external_subject varchar(320),
            status varchar(32) NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_identities_status CHECK (status IN ('active', 'disabled'))
        );

        CREATE TABLE roles (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            scope varchar(16) NOT NULL,
            tenant_id uuid REFERENCES tenants(id) ON DELETE RESTRICT,
            code varchar(64) NOT NULL,
            is_system boolean NOT NULL DEFAULT false,
            CONSTRAINT ck_roles_scope CHECK (scope IN ('platform', 'tenant'))
        );
        CREATE UNIQUE INDEX uq_roles_scope_tenant_code
            ON roles (scope, tenant_id, code) NULLS NOT DISTINCT;

        CREATE TABLE role_permissions (
            role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission varchar(128) NOT NULL,
            PRIMARY KEY (role_id, permission)
        );

        CREATE TABLE platform_role_bindings (
            identity_id uuid NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
            role_id uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (identity_id, role_id)
        );

        CREATE TABLE tenant_memberships (
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            identity_id uuid NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
            status varchar(32) NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, identity_id),
            CONSTRAINT ck_tenant_memberships_status CHECK (status IN ('invited', 'active', 'revoked'))
        );

        CREATE TABLE membership_roles (
            tenant_id uuid NOT NULL,
            identity_id uuid NOT NULL,
            role_id uuid NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, identity_id, role_id),
            CONSTRAINT fk_membership_roles_membership
                FOREIGN KEY (tenant_id, identity_id)
                REFERENCES tenant_memberships (tenant_id, identity_id)
                ON DELETE RESTRICT
        );

        CREATE TABLE global_policies (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            version integer NOT NULL UNIQUE,
            document jsonb NOT NULL,
            checksum varchar(64) NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'draft',
            activated_at timestamptz,
            created_by uuid NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
            CONSTRAINT ck_global_policies_status CHECK (status IN ('draft', 'active', 'retired'))
        );

        CREATE TABLE tenant_policies (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            name varchar(200) NOT NULL,
            document jsonb NOT NULL,
            floor_version integer,
            checksum varchar(64) NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'draft',
            created_by uuid NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_tenant_policies_status CHECK (status IN ('draft', 'active', 'retired'))
        );
        CREATE UNIQUE INDEX uq_tenant_policies_one_active
            ON tenant_policies (tenant_id) WHERE status = 'active';

        CREATE TABLE agents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            name varchar(200) NOT NULL,
            persona varchar(200) NOT NULL,
            policy_id uuid NOT NULL REFERENCES tenant_policies(id) ON DELETE RESTRICT,
            status varchar(32) NOT NULL DEFAULT 'active',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_agents_tenant_name UNIQUE (tenant_id, name)
        );

        CREATE TABLE tool_manifests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            name varchar(200) NOT NULL,
            description text NOT NULL DEFAULT '',
            risk_level varchar(32) NOT NULL DEFAULT 'low',
            requires_approval boolean NOT NULL DEFAULT false,
            param_schema jsonb,
            oci_repository varchar(500),
            artifact_digest varchar(200),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_tool_manifests_tenant_name UNIQUE (tenant_id, name)
        );

        CREATE TABLE approval_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            agent_id uuid NOT NULL REFERENCES agents(id) ON DELETE RESTRICT,
            trace_id varchar(128) NOT NULL,
            risk_tier varchar(64) NOT NULL,
            required_score numeric(8, 2) NOT NULL,
            status varchar(32) NOT NULL,
            context jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            resolved_at timestamptz
        );

        CREATE TABLE approval_signatures (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            request_id uuid NOT NULL REFERENCES approval_requests(id) ON DELETE RESTRICT,
            identity_id uuid NOT NULL REFERENCES identities(id) ON DELETE RESTRICT,
            role_code varchar(64) NOT NULL,
            weight numeric(8, 2) NOT NULL,
            decision varchar(32) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_approval_signatures_request_identity UNIQUE (request_id, identity_id)
        );

        CREATE TABLE execution_snapshots (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            trace_id varchar(128) NOT NULL,
            parent_trace_id varchar(128),
            agent_id uuid,
            status varchar(64) NOT NULL,
            task_input text,
            metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
            guards_evaluated jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_execution_snapshots_tenant_created
            ON execution_snapshots (tenant_id, created_at);

        CREATE TABLE fiscal_ledger_entries (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            trace_id varchar(128) NOT NULL,
            amount_usd numeric(18, 6) NOT NULL,
            model varchar(200),
            tokens integer,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_fiscal_ledger_entries_tenant_created
            ON fiscal_ledger_entries (tenant_id, created_at);

        CREATE TABLE telemetry_sinks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            sink_type varchar(64) NOT NULL,
            locator text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE cost_centers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
            code varchar(64) NOT NULL,
            gl_account varchar(64) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_cost_centers_tenant_code UNIQUE (tenant_id, code)
        );

        CREATE TABLE audit_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid REFERENCES tenants(id) ON DELETE RESTRICT,
            actor_scope varchar(32) NOT NULL,
            actor_id uuid REFERENCES identities(id) ON DELETE RESTRICT,
            action varchar(128) NOT NULL,
            target_type varchar(64) NOT NULL,
            target_id varchar(64),
            before jsonb,
            after jsonb,
            request_id varchar(64),
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_audit_events_tenant_created ON audit_events (tenant_id, created_at);

        CREATE TABLE secret_refs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid REFERENCES tenants(id) ON DELETE RESTRICT,
            purpose varchar(128) NOT NULL,
            locator text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )

    tables = [
        "plans",
        "tenants",
        "identities",
        "roles",
        "role_permissions",
        "platform_role_bindings",
        "tenant_memberships",
        "membership_roles",
        "global_policies",
        "tenant_policies",
        "agents",
        "tool_manifests",
        "approval_requests",
        "approval_signatures",
        "execution_snapshots",
        "fiscal_ledger_entries",
        "telemetry_sinks",
        "cost_centers",
        "audit_events",
        "secret_refs",
    ]
    for table in tables:
        op.execute(f"ALTER TABLE {table} OWNER TO govagent_owner")

    dml_tables = [
        "tenants",
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
    ]
    for table in dml_tables:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO govagent_app")

    op.execute("GRANT SELECT, INSERT, UPDATE ON plans TO govagent_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON global_policies TO govagent_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON identities TO govagent_app")
    op.execute("GRANT SELECT, INSERT ON platform_role_bindings TO govagent_app")
    op.execute("GRANT SELECT ON role_permissions TO govagent_app")
    op.execute("GRANT SELECT, INSERT ON audit_events TO govagent_app")


def downgrade() -> None:
    for table in [
        "secret_refs",
        "audit_events",
        "cost_centers",
        "telemetry_sinks",
        "fiscal_ledger_entries",
        "execution_snapshots",
        "approval_signatures",
        "approval_requests",
        "tool_manifests",
        "agents",
        "tenant_policies",
        "global_policies",
        "membership_roles",
        "tenant_memberships",
        "platform_role_bindings",
        "role_permissions",
        "roles",
        "identities",
        "tenants",
        "plans",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP OWNED BY govagent_app")
    op.execute("DROP OWNED BY govagent_owner")
    op.execute("DROP ROLE IF EXISTS govagent_app")
    op.execute("DROP ROLE IF EXISTS govagent_owner")
