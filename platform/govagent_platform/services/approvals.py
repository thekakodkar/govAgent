"""Durable votes. The score and the tier come from HITLManager.secure_approval."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from govagent_platform.domain.models import (
    ApprovalRequest,
    ApprovalSignature,
    TenantHitlAssignment,
    TenantMembership,
)
from govagent_platform.runtime.hitl_adapter import ReplayVoteAdapter
from govagent_platform.security.context import Actor
from govagent_platform.services.audit import write_audit
from govagent_platform.services.errors import ServiceError


def _weights() -> dict[str, float]:
    from govagent.hitl.manager import HITLManager

    return dict(HITLManager(adapter=ReplayVoteAdapter([])).voter_weights)


def assign_hitl_role(session: Session, actor: Actor, identity_id: UUID, hitl_role: str) -> TenantHitlAssignment:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    if hitl_role not in _weights():
        raise ServiceError(422, "hitl_role is not one of the library voter weights")
    membership = session.get(TenantMembership, (actor.tenant_id, identity_id))
    if membership is None or membership.status != "active":
        raise ServiceError(404, "Active membership not found")
    row = session.get(TenantHitlAssignment, (actor.tenant_id, identity_id))
    if row is None:
        row = TenantHitlAssignment(
            tenant_id=actor.tenant_id,
            identity_id=identity_id,
            hitl_role=hitl_role,
        )
        session.add(row)
    else:
        row.hitl_role = hitl_role
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="hitl.assign",
        target_type="hitl_assignment",
        target_id=str(identity_id),
        after={"hitl_role": hitl_role},
        tenant_id=actor.tenant_id,
    )
    return row


async def cast_vote(session: Session, actor: Actor, request_id: UUID, decision: str) -> ApprovalRequest:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    if decision not in {"APPROVED", "REJECTED"}:
        raise ServiceError(422, "decision must be APPROVED or REJECTED")
    request = session.get(ApprovalRequest, request_id)
    if request is None or request.tenant_id != actor.tenant_id:
        raise ServiceError(404, "Approval request not found")
    if request.status != "pending":
        raise ServiceError(409, "Approval request is already resolved")
    assignment = session.get(TenantHitlAssignment, (actor.tenant_id, actor.identity_id))
    if assignment is None:
        raise ServiceError(403, "No HITL role is assigned to this identity")
    existing = session.scalar(
        select(ApprovalSignature).where(
            ApprovalSignature.request_id == request.id,
            ApprovalSignature.identity_id == actor.identity_id,
        )
    )
    if existing is not None:
        raise ServiceError(409, "This identity has already voted")
    weight = _weights()[assignment.hitl_role]
    session.add(
        ApprovalSignature(
            tenant_id=actor.tenant_id,
            request_id=request.id,
            identity_id=actor.identity_id,
            role_code=assignment.hitl_role,
            weight=Decimal(str(weight)),
            decision=decision,
        )
    )
    session.flush()
    signatures = list(
        session.scalars(
            select(ApprovalSignature).where(ApprovalSignature.request_id == request.id)
        ).all()
    )
    votes = [{"voter_role": item.role_code, "decision": item.decision} for item in signatures]
    from govagent.hitl.manager import HITLManager

    manager = HITLManager(adapter=ReplayVoteAdapter(votes))
    approved = await manager.secure_approval(
        agent_id=str(request.agent_id),
        reason="tenant vote",
        context=request.context or {"params": {"amount": 0}},
        triggered_by="judiciary",
        config={},
    )
    veto = any(item["decision"] == "REJECTED" for item in votes)
    if veto:
        request.status = "rejected"
        request.resolved_at = datetime.now(timezone.utc)
    elif approved:
        request.status = "approved"
        request.resolved_at = datetime.now(timezone.utc)
    else:
        request.status = "pending"
    if manager.history:
        request.required_score = Decimal(str(manager.history[-1].required_score))
        request.risk_tier = manager.history[-1].risk_tier
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="approval.vote",
        target_type="approval_request",
        target_id=str(request.id),
        after={"decision": decision, "status": request.status, "hitl_role": assignment.hitl_role},
        tenant_id=actor.tenant_id,
    )
    return request


def approval_payload(session: Session, actor: Actor, request_id: UUID) -> dict:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    request = session.get(ApprovalRequest, request_id)
    if request is None or request.tenant_id != actor.tenant_id:
        raise ServiceError(404, "Approval request not found")
    signatures = list(
        session.scalars(
            select(ApprovalSignature)
            .where(ApprovalSignature.request_id == request.id)
            .order_by(ApprovalSignature.created_at)
        ).all()
    )
    return {
        "id": str(request.id),
        "status": request.status,
        "risk_tier": request.risk_tier,
        "required_score": float(request.required_score),
        "signatures": [
            {
                "identity_id": str(item.identity_id),
                "role": item.role_code,
                "weight": float(item.weight),
                "decision": item.decision,
            }
            for item in signatures
        ],
    }
