"""Promote one tenant into a schema. A dedicated database is not provisioned.

Ledger and audit rows stay in ``public``. The copied table is ``cost_centers``.
Row-level security is forced on the copy. ``govagent_app`` owns that table and
does not bypass RLS.
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from govagent_platform.db import begin_platform, begin_tenant
from govagent_platform.domain.models import IsolationPromotion, Tenant
from govagent_platform.security.context import Actor
from govagent_platform.services.audit import write_audit
from govagent_platform.services.errors import ServiceError

_SCHEMA = re.compile(r"^tenant_[0-9a-f]{32}$")


class IsolationRejected(Exception):
    def __init__(self, status_code: int, code: str, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


def promote(session: Session, actor: Actor, tenant_id: UUID, tier: str) -> Tenant:
    if actor.scope != "platform":
        raise ServiceError(403, "Platform scope is required")
    if tier == "dedicated_db":
        raise IsolationRejected(
            422,
            "dedicated_db_not_available",
            "A dedicated database needs its own connection and is not provisioned",
        )
    if tier != "dedicated_schema":
        raise ServiceError(422, "isolation_tier must be dedicated_schema or dedicated_db")
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise ServiceError(404, "Tenant not found")
    if tenant.isolation_tier == "dedicated_schema" and tenant.schema_name:
        return tenant
    if tenant.isolation_tier != "shared":
        raise ServiceError(409, "Only a shared tenant can be promoted")
    schema = "tenant_" + tenant.id.hex
    if not _SCHEMA.match(schema):
        raise ServiceError(500, "Generated schema name was rejected")
    begin_tenant(session, tenant.id)
    _create_schema(session, schema, tenant.id)
    begin_platform(session)
    previous = tenant.isolation_tier
    tenant.isolation_tier = "dedicated_schema"
    tenant.schema_name = schema
    session.add(
        IsolationPromotion(
            tenant_id=tenant.id,
            from_tier=previous,
            to_tier="dedicated_schema",
            schema_name=schema,
        )
    )
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="tenant.isolation_promote",
        target_type="tenant",
        target_id=str(tenant.id),
        before={"isolation_tier": previous},
        after={"isolation_tier": tenant.isolation_tier, "schema_name": schema},
        tenant_id=None,
    )
    return tenant


def _create_schema(session: Session, schema: str, tenant_id: UUID) -> None:
    session.execute(text(f"CREATE SCHEMA {schema}"))
    session.execute(
        text(
            f"CREATE TABLE {schema}.cost_centers (LIKE public.cost_centers INCLUDING DEFAULTS)"
        )
    )
    session.execute(
        text(
            f"INSERT INTO {schema}.cost_centers SELECT * FROM public.cost_centers "
            "WHERE tenant_id = :tenant_id"
        ),
        {"tenant_id": tenant_id},
    )
    session.execute(
        text("DELETE FROM public.cost_centers WHERE tenant_id = :tenant_id"),
        {"tenant_id": tenant_id},
    )
    session.execute(text(f"ALTER TABLE {schema}.cost_centers ENABLE ROW LEVEL SECURITY"))
    session.execute(text(f"ALTER TABLE {schema}.cost_centers FORCE ROW LEVEL SECURITY"))
    session.execute(
        text(
            f"""
            CREATE POLICY tenant_isolation ON {schema}.cost_centers
            FOR ALL
            USING (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            )
            """
        )
    )
    session.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {schema}.cost_centers TO govagent_app"))
    session.execute(text(f"GRANT USAGE ON SCHEMA {schema} TO govagent_app"))
