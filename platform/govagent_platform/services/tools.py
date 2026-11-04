"""Tenant tool manifests. Registration does not touch the process-global registry."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from govagent_platform.domain.models import ToolManifestRow
from govagent_platform.security.context import Actor
from govagent_platform.services.audit import write_audit
from govagent_platform.services.errors import ServiceError

_RISK = {"low", "medium", "high"}


def create_tool(
    session: Session,
    actor: Actor,
    *,
    name: str,
    description: str,
    risk_level: str,
    requires_approval: bool,
    param_schema: dict[str, Any] | None,
    oci_repository: str | None,
    artifact_digest: str | None,
) -> ToolManifestRow:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    level = risk_level.strip().lower()
    if level not in _RISK:
        raise ServiceError(422, "risk_level must be low, medium, or high")
    row = ToolManifestRow(
        tenant_id=actor.tenant_id,
        name=name.strip(),
        description=description or "",
        risk_level=level,
        requires_approval=requires_approval,
        param_schema=param_schema,
        oci_repository=oci_repository,
        artifact_digest=artifact_digest,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError as exc:
        raise ServiceError(409, "Tool name already exists") from exc
    write_audit(
        session,
        actor=actor,
        action="tool.create",
        target_type="tool",
        target_id=str(row.id),
        after={"name": row.name, "risk_level": row.risk_level},
        tenant_id=actor.tenant_id,
    )
    return row


def list_tools(session: Session, actor: Actor) -> list[ToolManifestRow]:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    return list(session.scalars(select(ToolManifestRow).order_by(ToolManifestRow.created_at)).all())


def tool_payload(row: ToolManifestRow) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "risk_level": row.risk_level,
        "requires_approval": row.requires_approval,
        "param_schema": row.param_schema,
        "oci_repository": row.oci_repository,
        "artifact_digest": row.artifact_digest,
    }
