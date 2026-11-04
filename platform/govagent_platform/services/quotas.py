"""Plan limits that already exist on ``plans``. Retention is not enforced here."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from govagent_platform.domain.models import Agent, Plan, Tenant
from govagent_platform.services.errors import ServiceError


def plan_for_tenant(session: Session, tenant_id: UUID) -> Plan:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise ServiceError(404, "Tenant not found")
    plan = session.get(Plan, tenant.plan_id)
    if plan is None:
        raise ServiceError(409, "Tenant plan is missing")
    return plan


def assert_agent_capacity(session: Session, tenant_id: UUID) -> None:
    plan = plan_for_tenant(session, tenant_id)
    active = session.scalar(
        select(func.count())
        .select_from(Agent)
        .where(Agent.tenant_id == tenant_id, Agent.status == "active")
    )
    if int(active or 0) >= plan.max_agents:
        raise ServiceError(409, f"Plan allows {plan.max_agents} active agents")


def month_spend_usd(session: Session) -> float:
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spent = session.execute(
        text(
            "SELECT COALESCE(SUM(amount_usd), 0) FROM fiscal_ledger_entries "
            "WHERE created_at >= :start"
        ),
        {"start": start},
    ).scalar_one()
    return float(spent)
