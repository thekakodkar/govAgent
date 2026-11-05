"""SCIM users and groups on identities, memberships, and tenant roles.

A group is a tenant role. System roles stay shared and cannot be deleted.
Deactivate revokes the membership in the caller's tenant and does not delete
the identity.
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from govagent_platform.domain.models import Identity, MembershipRole, Role, TenantMembership
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


def list_groups(session: Session, actor: Actor, *, query_filter: str | None) -> dict:
    _require_tenant(actor)
    display = None
    if query_filter:
        matched = re.fullmatch(r'displayName eq "([^"]+)"', query_filter.strip())
        if not matched:
            raise ServiceError(400, "Only displayName eq filters are supported")
        display = matched.group(1)
    roles = list(
        session.scalars(
            select(Role).where(
                Role.scope == "tenant",
                (Role.tenant_id.is_(None)) | (Role.tenant_id == actor.tenant_id),
            )
        ).all()
    )
    resources = []
    for role in roles:
        if role.tenant_id is not None and role.tenant_id != actor.tenant_id:
            continue
        label = role.display_name or role.code
        if display is not None and label != display and role.code != display:
            continue
        resources.append(_group(session, actor, role))
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(resources),
        "Resources": resources,
    }


def create_group(session: Session, actor: Actor, body: dict) -> dict:
    _require_tenant(actor)
    display = str(body.get("displayName") or "").strip()
    code = _role_code(display)
    role = Role(
        scope="tenant",
        tenant_id=actor.tenant_id,
        code=code,
        is_system=False,
        display_name=display,
        external_id=body.get("externalId") or None,
    )
    try:
        with session.begin_nested():
            session.add(role)
            session.flush()
    except IntegrityError as exc:
        raise ServiceError(409, "A group with that name already exists") from exc
    _replace_members(session, actor, role, _member_ids(body.get("members")))
    write_audit(
        session,
        actor=actor,
        action="scim.group.create",
        target_type="role",
        target_id=str(role.id),
        after={"code": role.code, "display_name": role.display_name},
        tenant_id=actor.tenant_id,
    )
    return _group(session, actor, role)


def get_group(session: Session, actor: Actor, group_id: UUID) -> dict:
    role = _visible_role(session, actor, group_id)
    return _group(session, actor, role)


def replace_group(session: Session, actor: Actor, group_id: UUID, body: dict) -> dict:
    role = _visible_role(session, actor, group_id)
    _reject_system_metadata_edit(role, body)
    if not role.is_system:
        if body.get("displayName"):
            role.display_name = str(body["displayName"]).strip()
        if "externalId" in body:
            role.external_id = body.get("externalId") or None
    if "members" in body:
        _replace_members(session, actor, role, _member_ids(body.get("members")))
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="scim.group.replace",
        target_type="role",
        target_id=str(role.id),
        after={"code": role.code},
        tenant_id=actor.tenant_id,
    )
    return _group(session, actor, role)


def patch_group(session: Session, actor: Actor, group_id: UUID, operations: list) -> dict:
    role = _visible_role(session, actor, group_id)
    for operation in operations or []:
        if not isinstance(operation, dict):
            raise ServiceError(400, "SCIM patch operation must be an object")
        op = str(operation.get("op") or "").lower()
        path = str(operation.get("path") or "")
        if op == "add" and path == "members":
            _add_members(session, actor, role, _member_ids(operation.get("value")))
        elif op == "remove" and path.startswith("members"):
            _remove_members(session, actor, role, _remove_ids(path, operation.get("value")))
        else:
            raise ServiceError(400, "Only member add and remove patches are supported")
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="scim.group.patch",
        target_type="role",
        target_id=str(role.id),
        after={"code": role.code},
        tenant_id=actor.tenant_id,
    )
    return _group(session, actor, role)


def delete_group(session: Session, actor: Actor, group_id: UUID) -> None:
    role = _visible_role(session, actor, group_id)
    if role.is_system or role.tenant_id is None:
        raise ServiceError(403, "System roles cannot be deleted")
    if role.tenant_id != actor.tenant_id:
        raise ServiceError(404, "Group not found")
    rows = session.scalars(
        select(MembershipRole).where(
            MembershipRole.tenant_id == actor.tenant_id,
            MembershipRole.role_id == role.id,
        )
    ).all()
    for row in rows:
        session.delete(row)
    session.delete(role)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="scim.group.delete",
        target_type="role",
        target_id=str(group_id),
        after={"code": role.code},
        tenant_id=actor.tenant_id,
    )


def _require_tenant(actor: Actor) -> None:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")


def _visible_role(session: Session, actor: Actor, group_id: UUID) -> Role:
    _require_tenant(actor)
    role = session.get(Role, group_id)
    if role is None or role.scope != "tenant":
        raise ServiceError(404, "Group not found")
    if role.tenant_id is not None and role.tenant_id != actor.tenant_id:
        raise ServiceError(404, "Group not found")
    return role


def _reject_system_metadata_edit(role: Role, body: dict) -> None:
    if not role.is_system and role.tenant_id is not None:
        return
    if body.get("displayName") and body["displayName"] != (role.display_name or role.code):
        raise ServiceError(403, "System roles cannot be renamed")
    if "externalId" in body and (body.get("externalId") or None) != role.external_id:
        raise ServiceError(403, "System roles cannot be renamed")


def _role_code(display: str) -> str:
    code = re.sub(r"[^a-z0-9]+", "-", display.strip().lower()).strip("-")
    if not code:
        raise ServiceError(422, "displayName is required")
    return code[:64]


def _member_ids(value) -> list[UUID]:
    if value is None:
        return []
    rows = value if isinstance(value, list) else [value]
    found: list[UUID] = []
    for row in rows:
        raw = row.get("value") if isinstance(row, dict) else row
        try:
            found.append(UUID(str(raw)))
        except (TypeError, ValueError) as exc:
            raise ServiceError(400, "Group member value must be a user id") from exc
    return found


def _remove_ids(path: str, value) -> list[UUID]:
    matched = re.search(r'value eq "([^"]+)"', path)
    if matched:
        return _member_ids([{"value": matched.group(1)}])
    return _member_ids(value)


def _require_member(session: Session, actor: Actor, identity_id: UUID) -> None:
    membership = session.get(TenantMembership, (actor.tenant_id, identity_id))
    if membership is None or membership.status != "active":
        raise ServiceError(400, "Member is not an active user in this tenant")


def _replace_members(session: Session, actor: Actor, role: Role, member_ids: list[UUID]) -> None:
    current = list(
        session.scalars(
            select(MembershipRole).where(
                MembershipRole.tenant_id == actor.tenant_id,
                MembershipRole.role_id == role.id,
            )
        ).all()
    )
    wanted = set(member_ids)
    for row in current:
        if row.identity_id not in wanted:
            session.delete(row)
    have = {row.identity_id for row in current}
    for identity_id in wanted - have:
        _require_member(session, actor, identity_id)
        session.add(
            MembershipRole(tenant_id=actor.tenant_id, identity_id=identity_id, role_id=role.id)
        )
    session.flush()


def _add_members(session: Session, actor: Actor, role: Role, member_ids: list[UUID]) -> None:
    for identity_id in member_ids:
        _require_member(session, actor, identity_id)
        existing = session.get(MembershipRole, (actor.tenant_id, identity_id, role.id))
        if existing is None:
            session.add(
                MembershipRole(tenant_id=actor.tenant_id, identity_id=identity_id, role_id=role.id)
            )
    session.flush()


def _remove_members(session: Session, actor: Actor, role: Role, member_ids: list[UUID]) -> None:
    for identity_id in member_ids:
        row = session.get(MembershipRole, (actor.tenant_id, identity_id, role.id))
        if row is not None:
            session.delete(row)
    session.flush()


def _group(session: Session, actor: Actor, role: Role) -> dict:
    members = session.execute(
        select(Identity)
        .join(MembershipRole, MembershipRole.identity_id == Identity.id)
        .where(
            MembershipRole.tenant_id == actor.tenant_id,
            MembershipRole.role_id == role.id,
        )
    ).scalars().all()
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
        "id": str(role.id),
        "displayName": role.display_name or role.code,
        "externalId": role.external_id,
        "members": [{"value": str(identity.id), "display": identity.email} for identity in members],
    }


def _user(identity: Identity, membership: TenantMembership) -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": str(identity.id),
        "userName": identity.email,
        "displayName": identity.display_name,
        "externalId": identity.external_subject,
        "active": membership.status == "active",
    }
