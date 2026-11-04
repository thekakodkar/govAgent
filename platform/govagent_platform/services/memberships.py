"""Tenant identity, membership, and role grants."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from govagent_platform.domain.models import Identity, MembershipRole, Role, RolePermission, TenantMembership
from govagent_platform.security.context import Actor
from govagent_platform.security.passwords import hash_password
from govagent_platform.services.audit import write_audit


class MembershipServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def create_identity(
    session: Session,
    actor: Actor,
    *,
    email: str,
    display_name: str,
    password: str,
) -> Identity:
    if actor.tenant_id is None:
        raise MembershipServiceError(403, "Tenant scope is required")
    normalized = email.strip().lower()
    if "@" not in normalized:
        raise MembershipServiceError(422, "Email is invalid")
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        raise MembershipServiceError(422, str(exc)) from exc
    identity = Identity(
        email=normalized,
        display_name=display_name.strip(),
        password_hash=password_hash,
        status="active",
    )
    try:
        with session.begin_nested():
            session.add(identity)
            session.flush()
    except IntegrityError as exc:
        raise MembershipServiceError(409, "Email is already registered") from exc
    write_audit(
        session,
        actor=actor,
        action="identity.create",
        target_type="identity",
        target_id=str(identity.id),
        after={"email": identity.email, "display_name": identity.display_name},
        tenant_id=actor.tenant_id,
    )
    return identity


def create_membership(
    session: Session,
    actor: Actor,
    *,
    identity_id: UUID,
) -> TenantMembership:
    if actor.tenant_id is None:
        raise MembershipServiceError(403, "Tenant scope is required")
    identity = session.get(Identity, identity_id)
    if identity is None:
        raise MembershipServiceError(404, "Identity not found")
    membership = TenantMembership(
        tenant_id=actor.tenant_id,
        identity_id=identity.id,
        status="active",
    )
    try:
        with session.begin_nested():
            session.add(membership)
            session.flush()
    except IntegrityError as exc:
        raise MembershipServiceError(409, "Membership already exists") from exc
    write_audit(
        session,
        actor=actor,
        action="membership.create",
        target_type="membership",
        target_id=str(identity.id),
        after={"identity_id": str(identity.id), "status": membership.status},
        tenant_id=actor.tenant_id,
    )
    return membership


def grant_role(
    session: Session,
    actor: Actor,
    *,
    identity_id: UUID,
    role_code: str,
) -> dict:
    if actor.tenant_id is None:
        raise MembershipServiceError(403, "Tenant scope is required")
    membership = session.get(TenantMembership, (actor.tenant_id, identity_id))
    if membership is None or membership.status != "active":
        raise MembershipServiceError(404, "Active membership not found")
    role = session.scalar(
        select(Role).where(Role.scope == "tenant", Role.code == role_code, Role.tenant_id.is_(None))
    )
    if role is None:
        raise MembershipServiceError(404, "Tenant role not found")
    try:
        with session.begin_nested():
            session.add(
                MembershipRole(
                    tenant_id=actor.tenant_id,
                    identity_id=identity_id,
                    role_id=role.id,
                )
            )
            session.flush()
    except IntegrityError as exc:
        raise MembershipServiceError(409, "Role is already granted") from exc
    permissions = list(
        session.scalars(
            select(RolePermission.permission).where(RolePermission.role_id == role.id)
        ).all()
    )
    write_audit(
        session,
        actor=actor,
        action="membership.role_grant",
        target_type="membership",
        target_id=str(identity_id),
        after={"role_code": role.code, "permissions": permissions},
        tenant_id=actor.tenant_id,
    )
    return {
        "identity_id": str(identity_id),
        "role_code": role.code,
        "permissions": permissions,
    }
