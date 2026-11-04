"""Global floor and tenant policy documents.

Activation retires the previous active row and inserts no in-place edit of an
active document. The floor check lives in ``policy_floor`` and calls
``govagent.policy.Policy`` without changing that class.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from govagent_platform.domain.models import GlobalPolicy, TenantPolicy
from govagent_platform.security.context import Actor
from govagent_platform.services.audit import write_audit
from govagent_platform.services.policy_floor import (
    FloorViolation,
    PolicyDocumentRejected,
    assert_tenant_tightens,
    ensure_library_accepts,
)


class PolicyServiceError(Exception):
    def __init__(self, status_code: int, detail: str, reasons: list[str] | None = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.reasons = reasons or []


def checksum_document(document: dict[str, Any]) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _public_document(document: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(document, default=str))


def draft_global_policy(session: Session, actor: Actor, document: dict[str, Any]) -> GlobalPolicy:
    try:
        ensure_library_accepts(document)
    except PolicyDocumentRejected as exc:
        raise PolicyServiceError(422, exc.message) from exc
    current = session.scalar(select(GlobalPolicy.version).order_by(GlobalPolicy.version.desc()).limit(1))
    policy = GlobalPolicy(
        version=(current or 0) + 1,
        document=_public_document(document),
        checksum=checksum_document(document),
        status="draft",
        created_by=actor.identity_id,
    )
    session.add(policy)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="global_policy.draft",
        target_type="global_policy",
        target_id=str(policy.id),
        after={"version": policy.version, "checksum": policy.checksum, "status": policy.status},
        tenant_id=None,
    )
    return policy


def activate_global_policy(session: Session, actor: Actor, policy_id: UUID) -> GlobalPolicy:
    policy = session.get(GlobalPolicy, policy_id)
    if policy is None:
        raise PolicyServiceError(404, "Global policy not found")
    if policy.status == "active":
        return policy
    if policy.status != "draft":
        raise PolicyServiceError(409, "Only a draft global policy can be activated")
    previous = session.scalars(select(GlobalPolicy).where(GlobalPolicy.status == "active")).all()
    for row in previous:
        row.status = "retired"
    policy.status = "active"
    policy.activated_at = datetime.now(timezone.utc)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="global_policy.activate",
        target_type="global_policy",
        target_id=str(policy.id),
        after={"version": policy.version, "status": policy.status},
        tenant_id=None,
    )
    return policy


def active_floor(session: Session) -> GlobalPolicy:
    policy = session.scalar(select(GlobalPolicy).where(GlobalPolicy.status == "active"))
    if policy is None:
        raise PolicyServiceError(409, "No active global policy floor")
    return policy


def draft_tenant_policy(
    session: Session,
    actor: Actor,
    *,
    name: str,
    document: dict[str, Any],
) -> TenantPolicy:
    if actor.tenant_id is None:
        raise PolicyServiceError(403, "Tenant scope is required")
    try:
        ensure_library_accepts(document)
    except PolicyDocumentRejected as exc:
        raise PolicyServiceError(422, exc.message) from exc
    policy = TenantPolicy(
        tenant_id=actor.tenant_id,
        name=name.strip(),
        document=_public_document(document),
        floor_version=None,
        checksum=checksum_document(document),
        status="draft",
        created_by=actor.identity_id,
    )
    session.add(policy)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="tenant_policy.draft",
        target_type="tenant_policy",
        target_id=str(policy.id),
        after={"name": policy.name, "checksum": policy.checksum, "status": policy.status},
        tenant_id=actor.tenant_id,
    )
    return policy


def activate_tenant_policy(session: Session, actor: Actor, policy_id: UUID) -> TenantPolicy:
    if actor.tenant_id is None:
        raise PolicyServiceError(403, "Tenant scope is required")
    policy = session.get(TenantPolicy, policy_id)
    if policy is None or policy.tenant_id != actor.tenant_id:
        raise PolicyServiceError(404, "Tenant policy not found")
    if policy.status == "retired":
        raise PolicyServiceError(409, "A retired tenant policy cannot be activated")
    try:
        ensure_library_accepts(policy.document)
    except PolicyDocumentRejected as exc:
        raise PolicyServiceError(422, exc.message) from exc
    floor = active_floor(session)
    try:
        assert_tenant_tightens(floor.document, policy.document)
    except FloorViolation as exc:
        raise PolicyServiceError(409, "Policy exceeds the global floor", exc.reasons) from exc

    session.execute(
        update(TenantPolicy)
        .where(TenantPolicy.tenant_id == actor.tenant_id, TenantPolicy.status == "active", TenantPolicy.id != policy.id)
        .values(status="retired")
    )
    policy.status = "active"
    policy.floor_version = floor.version
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="tenant_policy.activate",
        target_type="tenant_policy",
        target_id=str(policy.id),
        after={
            "name": policy.name,
            "status": policy.status,
            "floor_version": policy.floor_version,
            "checksum": policy.checksum,
        },
        tenant_id=actor.tenant_id,
    )
    return policy


def list_tenant_policies(session: Session, actor: Actor) -> list[TenantPolicy]:
    if actor.tenant_id is None:
        raise PolicyServiceError(403, "Tenant scope is required")
    return list(
        session.scalars(
            select(TenantPolicy)
            .where(TenantPolicy.tenant_id == actor.tenant_id)
            .order_by(TenantPolicy.created_at)
        ).all()
    )


def policy_payload(policy: TenantPolicy) -> dict[str, Any]:
    return {
        "id": str(policy.id),
        "name": policy.name,
        "status": policy.status,
        "floor_version": policy.floor_version,
        "checksum": policy.checksum,
        "document": policy.document,
    }
