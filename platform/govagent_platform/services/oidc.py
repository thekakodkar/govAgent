"""OIDC login that reuses identities and memberships.

A provider whose ``client_secret_locator`` starts with ``stub://`` accepts the
subject posted to the callback. Any other locator is refused. This process
does not call a live identity provider.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from govagent_platform.config import get_settings
from govagent_platform.domain.models import Identity, OidcProvider, Tenant, TenantMembership
from govagent_platform.services.errors import ServiceError


def start_oidc(session: Session, issuer: str) -> dict[str, str]:
    provider = session.scalar(select(OidcProvider).where(OidcProvider.issuer == issuer.strip()))
    if provider is None:
        raise ServiceError(404, "OIDC provider not found")
    state = _sign({"provider_id": str(provider.id), "nonce": str(uuid4())})
    url = (
        f"{provider.issuer.rstrip('/')}/authorize"
        f"?client_id={provider.client_id}&state={state}&response_type=code"
    )
    return {"authorization_url": url, "state": state}


def finish_oidc(session: Session, *, state: str, subject: str) -> dict[str, str | None]:
    payload = _unsign(state)
    provider = session.get(OidcProvider, UUID(payload["provider_id"]))
    if provider is None:
        raise ServiceError(401, "Authentication required")
    if not provider.client_secret_locator.startswith("stub://"):
        raise ServiceError(501, "Live OIDC token exchange is not enabled")
    if not subject or not subject.strip():
        raise ServiceError(401, "Authentication required")
    identity = session.scalar(
        select(Identity).where(Identity.external_subject == subject.strip(), Identity.status == "active")
    )
    if identity is None:
        raise ServiceError(401, "Authentication required")
    scope, tenant_id = _scope_for(session, identity)
    return {
        "identity_id": str(identity.id),
        "scope": scope,
        "tenant_id": tenant_id,
    }


def _scope_for(session: Session, identity: Identity) -> tuple[str, str | None]:
    from govagent_platform.security.dependencies import role_codes_for_identity

    if role_codes_for_identity(session, identity.id):
        return "platform", None
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
    if len(usable) != 1:
        raise ServiceError(401, "Authentication required")
    return "tenant", str(usable[0].tenant_id)


def _sign(payload: dict[str, Any]) -> str:
    secret = get_settings().session_secret
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body.decode("ascii") + "." + signature


def _unsign(token: str) -> dict[str, Any]:
    secret = get_settings().session_secret
    if not token or "." not in token:
        raise ServiceError(401, "Authentication required")
    body, signature = token.rsplit(".", 1)
    expected = hmac.new(secret.encode(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ServiceError(401, "Authentication required")
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode("ascii")))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ServiceError(401, "Authentication required") from exc
    if "provider_id" not in payload:
        raise ServiceError(401, "Authentication required")
    return payload
