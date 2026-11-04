"""Operator routes under /platform/v1. Tenant id is never taken from an anonymous client."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from govagent_platform.authz.permissions import (
    PLATFORM_PLANS_WRITE,
    PLATFORM_POLICIES_WRITE,
    PLATFORM_TENANTS_READ,
    PLATFORM_TENANTS_WRITE,
)
from govagent_platform.config import SettingsError, get_settings
from govagent_platform.db import begin_authenticate
from govagent_platform.domain.models import Identity, Tenant, TenantMembership
from govagent_platform.security.context import Actor
from govagent_platform.security.dependencies import get_db, require, role_codes_for_identity
from govagent_platform.security.passwords import verify_password
from govagent_platform.security.sessions import COOKIE_NAME, sign_session
from govagent_platform.services.policies import (
    PolicyServiceError,
    activate_global_policy,
    draft_global_policy,
)
from govagent_platform.services.errors import ServiceError
from govagent_platform.services.isolation import IsolationRejected, promote
from govagent_platform.services.oidc import finish_oidc, start_oidc
from govagent_platform.services.retention import purge_expired
from govagent_platform.services.tenants import (
    TenantServiceError,
    assign_plan,
    create_plan,
    create_tenant,
    get_tenant,
    list_tenants,
    metadata,
    suspend_tenant,
)

router = APIRouter(prefix="/platform/v1", tags=["platform-admin"])


class LoginBody(BaseModel):
    email: str
    password: str


class OidcCallbackBody(BaseModel):
    state: str
    subject: str


class TenantCreateBody(BaseModel):
    slug: str
    display_name: str
    region: str | None = None
    plan_id: UUID | None = None
    isolation_tier: str | None = None


class PlanCreateBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    max_agents: int
    monthly_tco_ceiling_usd: Decimal
    retention_days: int
    features: dict = Field(default_factory=dict)


class PlanAssignBody(BaseModel):
    plan_id: UUID


class IsolationBody(BaseModel):
    isolation_tier: str


class GlobalPolicyBody(BaseModel):
    document: dict


def _service_error(exc: TenantServiceError | PolicyServiceError) -> HTTPException:
    detail: dict | str
    reasons = getattr(exc, "reasons", None)
    if reasons:
        detail = {"detail": exc.detail, "reasons": reasons}
    else:
        detail = exc.detail
    return HTTPException(status_code=exc.status_code, detail=detail)


@router.post("/session")
def login(body: LoginBody, response: Response, session: Session = Depends(get_db)):
    try:
        settings = get_settings()
    except SettingsError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    begin_authenticate(session)
    identity = session.scalar(select(Identity).where(Identity.email == body.email.strip().lower()))
    if identity is None or identity.status != "active":
        raise HTTPException(status_code=401, detail="Authentication required")
    if not verify_password(body.password, identity.password_hash):
        raise HTTPException(status_code=401, detail="Authentication required")

    platform_codes = role_codes_for_identity(session, identity.id)
    if platform_codes:
        scope = "platform"
        tenant_id = None
    else:
        memberships = list(
            session.scalars(
                select(TenantMembership).where(
                    TenantMembership.identity_id == identity.id,
                    TenantMembership.status == "active",
                )
            ).all()
        )
        usable: list[TenantMembership] = []
        for membership in memberships:
            tenant = session.get(Tenant, membership.tenant_id)
            if tenant is not None and tenant.status == "active":
                usable.append(membership)
        if not usable:
            raise HTTPException(status_code=401, detail="Authentication required")
        if len(usable) > 1:
            raise HTTPException(
                status_code=409,
                detail="Identity belongs to multiple tenants; Phase 1 login accepts one membership",
            )
        scope = "tenant"
        tenant_id = str(usable[0].tenant_id)

    token = sign_session(
        {
            "identity_id": str(identity.id),
            "scope": scope,
            "tenant_id": tenant_id,
        },
        settings.session_secret,
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        path="/",
    )
    return {"scope": scope, "tenant_id": tenant_id}


@router.get("/session/oidc/start")
def oidc_start(issuer: str, session: Session = Depends(get_db)):
    begin_authenticate(session)
    try:
        return start_oidc(session, issuer)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/session/oidc/callback")
def oidc_callback(body: OidcCallbackBody, response: Response, session: Session = Depends(get_db)):
    try:
        settings = get_settings()
    except SettingsError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    begin_authenticate(session)
    try:
        logged_in = finish_oidc(session, state=body.state, subject=body.subject)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    token = sign_session(
        {
            "identity_id": logged_in["identity_id"],
            "scope": logged_in["scope"],
            "tenant_id": logged_in["tenant_id"],
        },
        settings.session_secret,
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        path="/",
    )
    return {"scope": logged_in["scope"], "tenant_id": logged_in["tenant_id"]}


@router.delete("/session", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return None


@router.post("/tenants", status_code=201)
def post_tenant(
    body: TenantCreateBody,
    actor: Actor = Depends(require(PLATFORM_TENANTS_WRITE)),
    session: Session = Depends(get_db),
):
    if body.isolation_tier not in (None, "", "shared"):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "isolation_tier_not_available",
                "detail": "Only the shared isolation tier can be created",
            },
        )
    try:
        tenant = create_tenant(
            session,
            actor,
            slug=body.slug,
            display_name=body.display_name,
            region=body.region,
            plan_id=body.plan_id,
        )
    except TenantServiceError as exc:
        raise _service_error(exc) from exc
    return metadata(session, tenant)


@router.post("/tenants/{tenant_id}/suspend")
def post_suspend(
    tenant_id: UUID,
    actor: Actor = Depends(require(PLATFORM_TENANTS_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        tenant = suspend_tenant(session, actor, tenant_id)
    except TenantServiceError as exc:
        raise _service_error(exc) from exc
    return metadata(session, tenant)


@router.get("/tenants")
def get_tenants(
    actor: Actor = Depends(require(PLATFORM_TENANTS_READ)),
    session: Session = Depends(get_db),
):
    return [metadata(session, tenant) for tenant in list_tenants(session)]


@router.get("/tenants/{tenant_id}")
def get_one_tenant(
    tenant_id: UUID,
    actor: Actor = Depends(require(PLATFORM_TENANTS_READ)),
    session: Session = Depends(get_db),
):
    try:
        tenant = get_tenant(session, tenant_id)
    except TenantServiceError as exc:
        raise _service_error(exc) from exc
    return metadata(session, tenant)


@router.post("/tenants/{tenant_id}/isolation")
def post_isolation(
    tenant_id: UUID,
    body: IsolationBody,
    actor: Actor = Depends(require(PLATFORM_TENANTS_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        tenant = promote(session, actor, tenant_id, body.isolation_tier)
    except IsolationRejected as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "detail": exc.detail},
        ) from exc
    except (TenantServiceError, ServiceError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return metadata(session, tenant)


@router.post("/retention/purge")
def post_purge(
    actor: Actor = Depends(require(PLATFORM_TENANTS_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        return purge_expired(session, actor)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/plans", status_code=201)
def post_plan(
    body: PlanCreateBody,
    actor: Actor = Depends(require(PLATFORM_PLANS_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        plan = create_plan(
            session,
            actor,
            code=body.code,
            name=body.name,
            max_agents=body.max_agents,
            monthly_tco_ceiling_usd=body.monthly_tco_ceiling_usd,
            retention_days=body.retention_days,
            features=body.features,
        )
    except TenantServiceError as exc:
        raise _service_error(exc) from exc
    return {
        "id": str(plan.id),
        "code": plan.code,
        "name": plan.name,
        "max_agents": plan.max_agents,
        "monthly_tco_ceiling_usd": str(plan.monthly_tco_ceiling_usd),
        "retention_days": plan.retention_days,
    }


@router.put("/tenants/{tenant_id}/plan")
def put_plan(
    tenant_id: UUID,
    body: PlanAssignBody,
    actor: Actor = Depends(require(PLATFORM_PLANS_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        tenant = assign_plan(session, actor, tenant_id, body.plan_id)
    except TenantServiceError as exc:
        raise _service_error(exc) from exc
    return metadata(session, tenant)


@router.post("/global-policies", status_code=201)
def post_global_policy(
    body: GlobalPolicyBody,
    actor: Actor = Depends(require(PLATFORM_POLICIES_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        policy = draft_global_policy(session, actor, body.document)
    except PolicyServiceError as exc:
        raise _service_error(exc) from exc
    return {
        "id": str(policy.id),
        "version": policy.version,
        "status": policy.status,
        "checksum": policy.checksum,
    }


@router.post("/global-policies/{policy_id}/activate")
def post_activate_global(
    policy_id: UUID,
    actor: Actor = Depends(require(PLATFORM_POLICIES_WRITE)),
    session: Session = Depends(get_db),
):
    try:
        policy = activate_global_policy(session, actor, policy_id)
    except PolicyServiceError as exc:
        raise _service_error(exc) from exc
    return {"id": str(policy.id), "version": policy.version, "status": policy.status}
