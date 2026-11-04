"""Append-only audit inserts. This is not a telemetry exporter."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from govagent_platform.domain.models import AuditEvent
from govagent_platform.security.context import Actor


def write_audit(
    session: Session,
    *,
    actor: Actor,
    action: str,
    target_type: str,
    target_id: str | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    tenant_id: UUID | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        actor_scope=actor.scope,
        actor_id=actor.identity_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
        request_id=request_id,
    )
    session.add(event)
    session.flush()
    return event
