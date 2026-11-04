"""SCIM users stored as identities and tenant memberships.

Group writes are not implemented. Deactivate revokes the membership in the
caller's tenant and does not delete the identity.
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from govagent_platform.domain.models import Identity, TenantMembership
from govagent_platform.security.context import Actor
from govagent_platform.services.audit import write_audit
from govagent_platform.services.errors import ServiceError

_USERNAME = re.compile(r'^userName eq "([^"]+)"$')


def list_users(session: Session, actor: Actor, *, query_filter: str | None) -> dict:
    _require_tenant(actor)
    email = None
    if query_filter:
        matched = _USERNAME.fullmatch(query_filter.strip())
        if not matched:
            raise ServiceError(400, "Only userName eq filters are supported")
        email = matched.group(1).strip().lower()
    statement = (
        select(Identity, TenantMembership)
        .join(TenantMembership, TenantMembership.identity_id == Identity.id)
        .where(TenantMembership.tenant_id == actor.tenant_id)
    )
    if email:
        statement = statement.where(Identity.email == email)
    resources = [_user(identity, membership) for identity, membership in session.execute(statement).all()]
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(resources),
        "Resources": resources,
    }


def create_user(session: Session, actor: Actor, body: dict) -> dict:
    _require_tenant(actor)
    email = str(body.get("userName") or "").strip().lower()
    if "@" not in email:
        raise ServiceError(422, "userName must be an email")
    display = str(body.get("displayName") or email).strip()
    identity = session.scalar(select(Identity).where(Identity.email == email))
    if identity is None:
        identity = Identity(
            email=email,
            display_name=display,
            password_hash=None,
            external_subject=(body.get("externalId") or None),
            status="active",
        )
        try:
            with session.begin_nested():
                session.add(identity)
                session.flush()
        except IntegrityError as exc:
            raise ServiceError(409, "Email is already registered") from exc
    elif body.get("externalId") and not identity.external_subject:
        identity.external_subject = str(body["externalId"])
        session.flush()
    existing = session.get(TenantMembership, (actor.tenant_id, identity.id))
    if existing is not None and existing.status == "active":
        raise ServiceError(409, "User is already a member of this tenant")
    if existing is None:
        existing = TenantMembership(tenant_id=actor.tenant_id, identity_id=identity.id, status="active")
        session.add(existing)
    else:
        existing.status = "active"
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="scim.user.create",
        target_type="identity",
        target_id=str(identity.id),
        after={"email": identity.email, "membership": existing.status},
        tenant_id=actor.tenant_id,
    )
    return _user(identity, existing)


def get_user(session: Session, actor: Actor, user_id: UUID) -> dict:
    _require_tenant(actor)
    identity = session.get(Identity, user_id)
    membership = session.get(TenantMembership, (actor.tenant_id, user_id))
    if identity is None or membership is None:
        raise ServiceError(404, "User not found")
    return _user(identity, membership)


def replace_user(session: Session, actor: Actor, user_id: UUID, body: dict) -> dict:
    _require_tenant(actor)
    identity = session.get(Identity, user_id)
    membership = session.get(TenantMembership, (actor.tenant_id, user_id))
    if identity is None or membership is None:
        raise ServiceError(404, "User not found")
    if "displayName" in body and str(body["displayName"]).strip():
        identity.display_name = str(body["displayName"]).strip()
    if "active" in body:
        membership.status = "active" if body["active"] else "revoked"
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="scim.user.replace",
        target_type="identity",
        target_id=str(identity.id),
        after={"membership": membership.status, "display_name": identity.display_name},
        tenant_id=actor.tenant_id,
    )
    return _user(identity, membership)


def list_groups() -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": 0,
        "Resources": [],
    }


def _require_tenant(actor: Actor) -> None:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")


def _user(identity: Identity, membership: TenantMembership) -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": str(identity.id),
        "userName": identity.email,
        "displayName": identity.display_name,
        "externalId": identity.external_subject,
        "active": membership.status == "active",
    }
