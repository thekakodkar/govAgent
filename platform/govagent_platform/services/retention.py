"""Move expired execution snapshots into an append-only archive.

``audit_events`` and ``fiscal_ledger_entries`` are not deleted or updated.
The archive table grants insert and select only.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from govagent_platform.db import begin_platform
from govagent_platform.security.context import Actor
from govagent_platform.services.audit import write_audit
from govagent_platform.services.errors import ServiceError


def purge_expired(session: Session, actor: Actor) -> dict:
    if actor.scope != "platform":
        raise ServiceError(403, "Platform scope is required")
    begin_platform(session, break_glass=True)
    rows = session.execute(
        text(
            """
            SELECT s.id, s.tenant_id, s.trace_id, s.status, s.metrics, s.created_at
            FROM execution_snapshots s
            JOIN tenants t ON t.id = s.tenant_id
            JOIN plans p ON p.id = t.plan_id
            WHERE s.created_at < now() - make_interval(days => p.retention_days)
            """
        )
    ).mappings().all()
    for row in rows:
        payload = {
            "id": str(row["id"]),
            "tenant_id": str(row["tenant_id"]),
            "trace_id": row["trace_id"],
            "status": row["status"],
            "metrics": row["metrics"],
            "created_at": row["created_at"].isoformat(),
        }
        session.execute(
            text(
                """
                INSERT INTO retention_archives (tenant_id, source_table, source_id, payload)
                VALUES (:tenant_id, 'execution_snapshots', :source_id, CAST(:payload AS jsonb))
                """
            ),
            {
                "tenant_id": row["tenant_id"],
                "source_id": row["id"],
                "payload": json.dumps(payload),
            },
        )
        session.execute(
            text("DELETE FROM execution_snapshots WHERE id = :source_id"),
            {"source_id": row["id"]},
        )
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="retention.purge",
        target_type="retention_archives",
        target_id=None,
        after={"archived_snapshots": len(rows)},
        tenant_id=None,
    )
    return {"archived_snapshots": len(rows)}
