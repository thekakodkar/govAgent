"""HITL role assignments and the tenant.hitl.vote permission.

Revision ID: 20261105_0004
Revises: 20261104_0003
"""

from __future__ import annotations

from alembic import op

revision = "20261105_0004"
down_revision = "20261104_0003"
branch_labels = None
depends_on = None

TENANT_ADMIN_ROLE_ID = "22222222-2222-4222-8222-222222222222"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE tenant_hitl_assignments (
            tenant_id uuid NOT NULL,
            identity_id uuid NOT NULL,
            hitl_role varchar(32) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, identity_id),
            CONSTRAINT fk_hitl_assignments_membership
                FOREIGN KEY (tenant_id, identity_id)
                REFERENCES tenant_memberships (tenant_id, identity_id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_hitl_assignments_role CHECK (
                hitl_role IN ('C-Suite', 'Director', 'Auditor', 'Lead', 'Clerk')
            )
        )
        """
    )
    op.execute("ALTER TABLE tenant_hitl_assignments OWNER TO govagent_owner")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_hitl_assignments TO govagent_app"
    )
    op.execute("ALTER TABLE tenant_hitl_assignments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_hitl_assignments FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY hitl_assignments_isolation ON tenant_hitl_assignments
        FOR ALL
        USING (
            current_setting('app.actor_scope', true) IN ('platform', 'authenticate')
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        WITH CHECK (
            current_setting('app.actor_scope', true) = 'platform'
            OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
        )
        """
    )
    op.execute(
        f"""
        INSERT INTO role_permissions (role_id, permission)
        VALUES ('{TENANT_ADMIN_ROLE_ID}', 'tenant.hitl.vote')
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM role_permissions WHERE role_id = '{TENANT_ADMIN_ROLE_ID}' "
        "AND permission = 'tenant.hitl.vote'"
    )
    op.execute("DROP POLICY IF EXISTS hitl_assignments_isolation ON tenant_hitl_assignments")
    op.execute("ALTER TABLE tenant_hitl_assignments NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_hitl_assignments DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS tenant_hitl_assignments")
