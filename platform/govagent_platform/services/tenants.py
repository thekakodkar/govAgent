"""Platform-operator tenant and plan services."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from govagent_platform.domain.models import Plan, Tenant
from govagent_platform.security.context import Actor
from govagent_platform.services.audit import write_audit

_SLUG = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


class TenantServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _plan(session: Session, plan_id: UUID) -> Plan:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise TenantServiceError(404, "Plan not found")
    return plan


def _community_plan(session: Session) -> Plan:
    plan = session.scalar(select(Plan).where(Plan.code == "community"))
    if plan is None:
        raise TenantServiceError(409, "Default community plan is not seeded")
    return plan


def metadata(session: Session, tenant: Tenant) -> dict[str, Any]:
    plan = session.get(Plan, tenant.plan_id)
    return {
        "id": str(tenant.id),
        "slug": tenant.slug,
        "display_name": tenant.display_name,
        "status": tenant.status,
        "plan": None
        if plan is None
        else {"id": str(plan.id), "code": plan.code, "name": plan.name},
        "region": tenant.region,
        "isolation_tier": tenant.isolation_tier,
        "schema_name": tenant.schema_name,
    }


def create_plan(
    session: Session,
    actor: Actor,
    *,
    code: str,
    name: str,
    max_agents: int,
    monthly_tco_ceiling_usd: Decimal,
    retention_days: int,
    features: dict[str, Any] | None = None,
) -> Plan:
    if max_agents < 1 or retention_days < 1:
        raise TenantServiceError(422, "Plan limits must be positive")
    plan = Plan(
        code=code.strip(),
        name=name.strip(),
        max_agents=max_agents,
        monthly_tco_ceiling_usd=monthly_tco_ceiling_usd,
        retention_days=retention_days,
        features=features or {},
    )
    try:
        with session.begin_nested():
            session.add(plan)
            session.flush()
    except IntegrityError as exc:
        raise TenantServiceError(409, "Plan code already exists") from exc
    write_audit(
        session,
        actor=actor,
        action="plan.create",
        target_type="plan",
        target_id=str(plan.id),
        after={"code": plan.code, "name": plan.name, "max_agents": plan.max_agents},
        tenant_id=None,
    )
    return plan


def create_tenant(
    session: Session,
    actor: Actor,
    *,
    slug: str,
    display_name: str,
    region: str | None = None,
    plan_id: UUID | None = None,
) -> Tenant:
    if not _SLUG.match(slug):
        raise TenantServiceError(422, "Slug must be lowercase letters, digits, and hyphens")
    plan = _plan(session, plan_id) if plan_id else _community_plan(session)
    tenant = Tenant(
        slug=slug,
        display_name=display_name.strip(),
        status="active",
        plan_id=plan.id,
        isolation_tier="shared",
        region=region,
    )
    try:
        with session.begin_nested():
            session.add(tenant)
            session.flush()
    except IntegrityError as exc:
        raise TenantServiceError(409, "Tenant slug already exists") from exc
    write_audit(
        session,
        actor=actor,
        action="tenant.create",
        target_type="tenant",
        target_id=str(tenant.id),
        after={
            "slug": tenant.slug,
            "status": tenant.status,
            "plan_code": plan.code,
            "isolation_tier": tenant.isolation_tier,
            "region": tenant.region,
        },
        tenant_id=None,
    )
    return tenant


def suspend_tenant(session: Session, actor: Actor, tenant_id: UUID) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantServiceError(404, "Tenant not found")
    if tenant.status == "suspended":
        raise TenantServiceError(409, "Tenant is already suspended")
    before = {"status": tenant.status}
    tenant.status = "suspended"
    tenant.suspended_at = datetime.now(timezone.utc)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="tenant.suspend",
        target_type="tenant",
        target_id=str(tenant.id),
        before=before,
        after={"status": tenant.status},
        tenant_id=None,
    )
    return tenant


def assign_plan(session: Session, actor: Actor, tenant_id: UUID, plan_id: UUID) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantServiceError(404, "Tenant not found")
    plan = _plan(session, plan_id)
    before = {"plan_id": str(tenant.plan_id)}
    tenant.plan_id = plan.id
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="tenant.plan_assign",
        target_type="tenant",
        target_id=str(tenant.id),
        before=before,
        after={"plan_id": str(plan.id), "plan_code": plan.code},
        tenant_id=None,
    )
    return tenant


def list_tenants(session: Session) -> list[Tenant]:
    return list(session.scalars(select(Tenant).order_by(Tenant.created_at)).all())


def get_tenant(session: Session, tenant_id: UUID) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantServiceError(404, "Tenant not found")
    return tenant
