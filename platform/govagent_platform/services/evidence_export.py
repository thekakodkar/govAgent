"""Per-tenant evidence and CFO views built from stored rows.

Library classes are used as they shipped. They are not modified and they are
not re-exported from ``govagent.governance``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from govagent.governance.cfo_analytics import CFOAnalyticsEngine
from govagent.governance.evidence import (
    Article9RiskMitigation,
    Article12TraceRecord,
    Article14OversightRecord,
    ComplianceDossier,
)

from govagent_platform.domain.models import ExecutionSnapshotRow, FiscalLedgerEntry
from govagent_platform.security.context import Actor
from govagent_platform.services.errors import ServiceError


class _SnapshotView:
    def __init__(self, row: ExecutionSnapshotRow, spend: float, tokens: int):
        self.status = (row.status or "").upper()
        self.recursive_tco_usd = spend
        self.total_tokens = tokens
        self.cost_center = "CC-GENAI-DEFAULT"
        self.gl_account = "GL-640100-SOFTWARE"
        self.requested_exposure_usd = spend if self.status in {"BLOCKED", "PENDING"} else 0.0


def _rows(session: Session) -> list[ExecutionSnapshotRow]:
    return list(
        session.scalars(select(ExecutionSnapshotRow).order_by(ExecutionSnapshotRow.created_at)).all()
    )


def _spend_by_trace(session: Session) -> dict[str, tuple[float, int]]:
    totals: dict[str, tuple[float, int]] = {}
    rows = session.execute(
        select(FiscalLedgerEntry.trace_id, FiscalLedgerEntry.amount_usd, FiscalLedgerEntry.tokens)
    ).all()
    for trace_id, amount, tokens in rows:
        spend, count = totals.get(trace_id, (0.0, 0))
        totals[trace_id] = (spend + float(amount or 0), count + int(tokens or 0))
    return totals


def compliance_dossier(session: Session, actor: Actor) -> dict:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    art9 = Article9RiskMitigation()
    art12: list[Article12TraceRecord] = []
    art14: list[Article14OversightRecord] = []
    for row in _rows(session):
        verdict = (row.status or "UNKNOWN").upper()
        if verdict in {"BLOCKED", "VETOED"}:
            art9.total_interceptions += 1
            reason = str(row.status or "").upper()
            if "PRIVACY" in reason or "PII" in reason:
                art9.privacy_redactions += 1
        metrics = row.metrics or {}
        library = metrics.get("library") if isinstance(metrics, dict) else {}
        model = "undefined"
        if isinstance(library, dict):
            model = str(library.get("selected_model") or metrics.get("model") or "undefined")
        art12.append(
            Article12TraceRecord(
                trace_id=row.trace_id,
                parent_trace_id=row.parent_trace_id,
                timestamp=row.created_at.isoformat(),
                model=model,
                cost_usd=float((library or {}).get("recursive_tco_usd") or 0.0)
                if isinstance(library, dict)
                else 0.0,
                state_verdict=verdict,
            )
        )
    dossier = ComplianceDossier(
        export_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc).isoformat(),
        system_anchor="govagent-platform",
        eu_ai_act_article_9=art9,
        eu_ai_act_article_12=art12,
        eu_ai_act_article_14=art14,
    )
    dossier.seal()
    return dossier.model_dump()


def financial_overview(session: Session, actor: Actor) -> dict:
    if actor.tenant_id is None:
        raise ServiceError(403, "Tenant scope is required")
    spend = _spend_by_trace(session)
    engine = CFOAnalyticsEngine()
    for row in _rows(session):
        amount, tokens = spend.get(row.trace_id, (0.0, 0))
        engine.record_execution(_SnapshotView(row, amount, tokens))
    report = engine.analyze()
    payload = report.model_dump()
    payload["allocations_by_center"] = {
        key: value if isinstance(value, dict) else value.model_dump()
        for key, value in payload.get("allocations_by_center", {}).items()
    }
    return payload
