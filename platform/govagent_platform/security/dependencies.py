"""FastAPI dependencies: database session, cookie actor, and permission checks."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from govagent_platform.config import SettingsError, get_settings
from govagent_platform.db import begin_authenticate, begin_platform, begin_tenant, get_session_factory
from govagent_platform.domain.models import (
    MembershipRole,
    PlatformRoleBinding,
    Role,
    RolePermission,
    Tenant,
    TenantMembership,
)
from govagent_platform.security.context import Actor
from govagent_platform.security.sessions import COOKIE_NAME, SessionError, cookie_identity, unsign_session


def get_db() -> Iterator[Session]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _permissions_for_roles(session: Session, role_ids: list[UUID]) -> frozenset[str]:
    if not role_ids:
        return frozenset()
    rows = session.scalars(
        select(RolePermission.permission).where(RolePermission.role_id.in_(role_ids))
    ).all()
    return frozenset(rows)


def load_actor(session: Session, identity_id: UUID, scope: str, tenant_id: UUID | None) -> Actor:
    begin_authenticate(session)
    if scope == "platform":
        role_ids = list(
            session.scalars(
                select(PlatformRoleBinding.role_id).where(PlatformRoleBinding.identity_id == identity_id)
            ).all()
        )
        if not role_ids:
            raise HTTPException(status_code=401, detail="Authentication required")
        begin_platform(session)
        return Actor(
            identity_id=identity_id,
            scope="platform",
            tenant_id=None,
            permissions=_permissions_for_roles(session, role_ids),
        )

    if scope != "tenant" or tenant_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    membership = session.get(TenantMembership, (tenant_id, identity_id))
    tenant = session.get(Tenant, tenant_id)
    if membership is None or membership.status != "active" or tenant is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if tenant.status != "active":
        raise HTTPException(status_code=403, detail="Tenant is suspended")
    role_ids = list(
        session.scalars(
            select(MembershipRole.role_id).where(
                MembershipRole.tenant_id == tenant_id,
                MembershipRole.identity_id == identity_id,
            )
        ).all()
    )
    begin_tenant(session, tenant_id, tenant.schema_name)
    return Actor(
        identity_id=identity_id,
        scope="tenant",
        tenant_id=tenant_id,
        permissions=_permissions_for_roles(session, role_ids),
    )


def current_actor(request: Request, session: Session = Depends(get_db)) -> Actor:
    try:
        settings = get_settings()
    except SettingsError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = unsign_session(token, settings.session_secret)
        identity_id, scope, tenant_id = cookie_identity(payload)
    except (SessionError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Authentication required") from exc
    return load_actor(session, identity_id, scope, tenant_id)


def require(permission: str):
    def dependency(actor: Actor = Depends(current_actor)) -> Actor:
        if not actor.has(permission):
            raise HTTPException(status_code=403, detail="Forbidden")
        return actor

    return dependency


def role_codes_for_identity(session: Session, identity_id: UUID) -> list[str]:
    """Used by login to decide platform versus tenant scope. Caller sets the GUC."""

    platform_codes = session.scalars(
        select(Role.code)
        .join(PlatformRoleBinding, PlatformRoleBinding.role_id == Role.id)
        .where(PlatformRoleBinding.identity_id == identity_id, Role.scope == "platform")
    ).all()
    return list(platform_codes)
