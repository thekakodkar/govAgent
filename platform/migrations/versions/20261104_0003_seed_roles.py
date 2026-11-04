"""Seed system roles, permissions, and the community plan. No tenant and no identity.

Revision ID: 20261104_0003
Revises: 20261104_0002
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import op

PLATFORM_ROOT = Path(__file__).resolve().parents[2]
if str(PLATFORM_ROOT) not in sys.path:
    sys.path.insert(0, str(PLATFORM_ROOT))

from govagent_platform.authz.permissions import (  # noqa: E402
    PLATFORM_PERMISSIONS,
    TENANT_ADMIN_PERMISSIONS,
    TENANT_AUDITOR_PERMISSIONS,
)

revision = "20261104_0003"
down_revision = "20261104_0002"
branch_labels = None
depends_on = None

OPERATOR_ROLE_ID = "11111111-1111-4111-8111-111111111111"
TENANT_ADMIN_ROLE_ID = "22222222-2222-4222-8222-222222222222"
TENANT_AUDITOR_ROLE_ID = "33333333-3333-4333-8333-333333333333"
COMMUNITY_PLAN_ID = "44444444-4444-4444-8444-444444444444"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO roles (id, scope, tenant_id, code, is_system) VALUES
            ('{OPERATOR_ROLE_ID}', 'platform', NULL, 'operator', true),
            ('{TENANT_ADMIN_ROLE_ID}', 'tenant', NULL, 'tenant_admin', true),
            ('{TENANT_AUDITOR_ROLE_ID}', 'tenant', NULL, 'tenant_auditor', true)
        """
    )
    _grant(OPERATOR_ROLE_ID, PLATFORM_PERMISSIONS)
    _grant(TENANT_ADMIN_ROLE_ID, TENANT_ADMIN_PERMISSIONS)
    _grant(TENANT_AUDITOR_ROLE_ID, TENANT_AUDITOR_PERMISSIONS)
    op.execute(
        f"""
        INSERT INTO plans (
            id, code, name, max_agents, monthly_tco_ceiling_usd, retention_days, features
        ) VALUES (
            '{COMMUNITY_PLAN_ID}',
            'community',
            'Community',
            5,
            50,
            30,
            '{{}}'::jsonb
        )
        """
    )


def _grant(role_id: str, permissions: tuple[str, ...]) -> None:
    values = ", ".join(f"('{role_id}', '{permission}')" for permission in permissions)
    op.execute(f"INSERT INTO role_permissions (role_id, permission) VALUES {values}")


def downgrade() -> None:
    op.execute(f"DELETE FROM plans WHERE id = '{COMMUNITY_PLAN_ID}'")
    op.execute(
        "DELETE FROM role_permissions WHERE role_id IN "
        f"('{OPERATOR_ROLE_ID}', '{TENANT_ADMIN_ROLE_ID}', '{TENANT_AUDITOR_ROLE_ID}')"
    )
    op.execute(
        "DELETE FROM roles WHERE id IN "
        f"('{OPERATOR_ROLE_ID}', '{TENANT_ADMIN_ROLE_ID}', '{TENANT_AUDITOR_ROLE_ID}')"
    )
