"""Tenant agent records. The persona is stored here and passed to ExecutiveAgent."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from govagent_platform.domain.models import Agent, TenantPolicy
from govagent_platform.security.context import Actor
from govagent_platform.services.audit import write_audit
from govagent_platform.services.errors import ServiceError


def create_agent(session: Session, actor: Actor, *, name: str, persona: str, policy_id: UUID) -> Agent:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    policy = session.get(TenantPolicy, policy_id)
    if policy is None or policy.tenant_id != actor.tenant_id or policy.status != "active":
        raise ServiceError(404, "Active tenant policy not found")
    row = Agent(
        tenant_id=actor.tenant_id,
        name=name.strip(),
        persona=persona.strip(),
        policy_id=policy.id,
        status="active",
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError as exc:
        raise ServiceError(409, "Agent name already exists") from exc
    write_audit(
        session,
        actor=actor,
        action="agent.create",
        target_type="agent",
        target_id=str(row.id),
        after={"name": row.name, "persona": row.persona, "policy_id": str(row.policy_id)},
        tenant_id=actor.tenant_id,
    )
    return row


def list_agents(session: Session, actor: Actor) -> list[Agent]:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    return list(session.scalars(select(Agent).order_by(Agent.created_at)).all())


def agent_payload(row: Agent) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "persona": row.persona,
        "policy_id": str(row.policy_id),
        "status": row.status,
    }
