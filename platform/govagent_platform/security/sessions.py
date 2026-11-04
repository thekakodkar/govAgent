"""HMAC-signed HTTP-only session cookies. The token is never placed in a query string."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any
from uuid import UUID

COOKIE_NAME = "govagent_platform_session"


class SessionError(ValueError):
    """The cookie is missing, altered, or not a platform or tenant session."""


def sign_session(payload: dict[str, Any], secret: str) -> str:
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body.decode("ascii") + "." + signature


def unsign_session(token: str, secret: str) -> dict[str, Any]:
    if not token or "." not in token:
        raise SessionError("Authentication required")
    body, signature = token.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise SessionError("Authentication required")
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode("ascii")))
    except (ValueError, json.JSONDecodeError) as exc:
        raise SessionError("Authentication required") from exc
    if payload.get("scope") not in {"platform", "tenant"}:
        raise SessionError("Authentication required")
    if "identity_id" not in payload:
        raise SessionError("Authentication required")
    return payload


def cookie_identity(payload: dict[str, Any]) -> tuple[UUID, str, UUID | None]:
    identity_id = UUID(str(payload["identity_id"]))
    scope = str(payload["scope"])
    raw_tenant = payload.get("tenant_id")
    tenant_id = UUID(str(raw_tenant)) if raw_tenant else None
    return identity_id, scope, tenant_id
