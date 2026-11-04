"""Evaluate one tenant agent and persist the trace through the library exporter."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from govagent_platform.domain.models import Agent, ApprovalRequest, ExecutionSnapshotRow, TenantPolicy, ToolManifestRow
from govagent_platform.runtime.agent import TenantExecutiveAgent
from govagent_platform.runtime.exporter import TenantDatabaseExporter
from govagent_platform.runtime.ledger import opening_balances
from govagent_platform.runtime.llm import build_router
from govagent_platform.runtime.policy_binding import PolicyDocumentRejected, hydrate_policy
from govagent_platform.runtime.tool_map import load_tool_map
from govagent_platform.security.context import Actor
from govagent_platform.services.audit import write_audit
from govagent_platform.services.errors import ServiceError


async def evaluate_agent(session: Session, actor: Actor, agent_id: UUID, task: str) -> dict:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    if not task or not task.strip():
        raise ServiceError(422, "task is required")
    agent_row = session.get(Agent, agent_id)
    if agent_row is None or agent_row.tenant_id != actor.tenant_id or agent_row.status != "active":
        raise ServiceError(404, "Agent not found")
    policy_row = session.get(TenantPolicy, agent_row.policy_id)
    if policy_row is None or policy_row.status != "active":
        raise ServiceError(409, "Agent policy is not active")
    try:
        policy = hydrate_policy(policy_row.document)
    except PolicyDocumentRejected as exc:
        raise ServiceError(422, exc.message) from exc
    except PermissionError as exc:
        write_audit(
            session,
            actor=actor,
            action="runtime.evaluate",
            target_type="agent",
            target_id=str(agent_row.id),
            after={"status": "denied", "reason": str(exc)},
            tenant_id=actor.tenant_id,
        )
        return {
            "trace_id": None,
            "status": "denied",
            "output": str(exc),
            "approval_request_id": None,
        }

    tools = load_tool_map(list(session.scalars(select(ToolManifestRow)).all()))
    all_time, today = opening_balances(session)
    exporter = TenantDatabaseExporter(session, actor.tenant_id, agent_row.id)

    def on_pending(*, trace_id: str, amount: float, required_score: float, risk_tier: str, tool_name: str, params: dict) -> str:
        row = ApprovalRequest(
            tenant_id=actor.tenant_id,
            agent_id=agent_row.id,
            trace_id=trace_id,
            risk_tier=risk_tier,
            required_score=Decimal(str(required_score)),
            status="pending",
            context={"params": {"amount": amount}, "tool": tool_name, "args": params},
        )
        session.add(row)
        session.flush()
        return str(row.id)

    runner = TenantExecutiveAgent(
        agent_row.persona,
        policy,
        build_router(policy),
        tool_map=tools,
        exporter=exporter,
        all_time=all_time,
        today=today,
        on_pending=on_pending,
    )
    result = await runner.execute(task)
    write_audit(
        session,
        actor=actor,
        action="runtime.evaluate",
        target_type="execution",
        target_id=result.trace_id,
        after={"status": result.status, "agent_id": str(agent_row.id)},
        tenant_id=actor.tenant_id,
    )
    return {
        "trace_id": result.trace_id,
        "status": result.status,
        "output": result.output,
        "approval_request_id": result.approval_request_id,
    }


def execution_payload(session: Session, actor: Actor, trace_id: str) -> dict:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    row = session.scalar(select(ExecutionSnapshotRow).where(ExecutionSnapshotRow.trace_id == trace_id))
    if row is None:
        raise ServiceError(404, "Execution not found")
    return {
        "trace_id": row.trace_id,
        "status": row.status,
        "metrics": row.metrics,
        "guards_evaluated": row.guards_evaluated,
    }
