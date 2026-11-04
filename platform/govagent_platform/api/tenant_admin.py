"""Tenant routes under /tenant/v1. The tenant comes from the session cookie."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from govagent_platform.authz.permissions import (
    TENANT_AUDIT_READ,
    TENANT_POLICIES_WRITE,
    TENANT_ROLES_WRITE,
    TENANT_USERS_WRITE,
)
from govagent_platform.domain.models import AuditEvent
from govagent_platform.security.context import Actor
from govagent_platform.security.dependencies import get_db, require
from govagent_platform.services.memberships import (
    MembershipServiceError,
    create_identity,
    create_membership,
    grant_role,
)
from govagent_platform.services.policies import (
    PolicyServiceError,
    activate_tenant_policy,
    draft_tenant_policy,
    list_tenant_policies,
    policy_payload,
)

router = APIRouter(prefix="/tenant/v1", tags=["tenant-admin"])


class IdentityBody(BaseModel):
    email: str
    display_name: str
    password: str


class MembershipBody(BaseModel):
    identity_id: UUID


class RoleGrantBody(BaseModel):
    role_code: str = Field(min_length=1, max_length=64)


class TenantPolicyBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    document: dict


def _membership_error(exc: MembershipServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _policy_error(exc: PolicyServiceError) -> HTTPException:
    if exc.reasons:
        return HTTPException(
            status_code=exc.status_code,
            detail={"detail": exc.detail, "reasons": exc.reasons},
        )
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/identities", status_code=201)
def post_identity(
    body: IdentityBody,
    actor: Actor = Depends(require(TENANT_USERS_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        identity = create_identity(
            session,
            actor,
            email=body.email,
            display_name=body.display_name,
            password=body.password,
        )
    except MembershipServiceError as exc:
        raise _membership_error(exc) from exc
    return {"id": str(identity.id), "email": identity.email, "display_name": identity.display_name}


@router.post("/memberships", status_code=201)
def post_membership(
    body: MembershipBody,
    actor: Actor = Depends(require(TENANT_USERS_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        membership = create_membership(session, actor, identity_id=body.identity_id)
    except MembershipServiceError as exc:
        raise _membership_error(exc) from exc
    return {
        "tenant_id": str(membership.tenant_id),
        "identity_id": str(membership.identity_id),
        "status": membership.status,
    }


@router.post("/memberships/{identity_id}/roles", status_code=201)
def post_role(
    identity_id: UUID,
    body: RoleGrantBody,
    actor: Actor = Depends(require(TENANT_ROLES_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        return grant_role(session, actor, identity_id=identity_id, role_code=body.role_code)
    except MembershipServiceError as exc:
        raise _membership_error(exc) from exc


@router.post("/policies", status_code=201)
def post_policy(
    body: TenantPolicyBody,
    actor: Actor = Depends(require(TENANT_POLICIES_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        policy = draft_tenant_policy(session, actor, name=body.name, document=body.document)
    except PolicyServiceError as exc:
        raise _policy_error(exc) from exc
    return policy_payload(policy)


@router.post("/policies/{policy_id}/activate")
def post_activate(
    policy_id: UUID,
    actor: Actor = Depends(require(TENANT_POLICIES_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        policy = activate_tenant_policy(session, actor, policy_id)
    except PolicyServiceError as exc:
        raise _policy_error(exc) from exc
    return policy_payload(policy)


@router.get("/policies")
def get_policies(
    actor: Actor = Depends(require(TENANT_POLICIES_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        rows = list_tenant_policies(session, actor)
    except PolicyServiceError as exc:
        raise _policy_error(exc) from exc
    return [policy_payload(row) for row in rows]


@router.get("/audit-events")
def get_audit(
    actor: Actor = Depends(require(TENANT_AUDIT_READ)),
    session: Session = Depends(get_db),
):
    if actor.tenant_id is None:
        raise HTTPException(status_code=403, detail="Forbidden")
    rows = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == actor.tenant_id)
        .order_by(AuditEvent.created_at)
    ).all()
    return [
        {
            "id": str(row.id),
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "actor_scope": row.actor_scope,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
