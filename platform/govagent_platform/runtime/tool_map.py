"""Per-request tool authorization. Nothing is written to a process-global registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError


@dataclass
class Authorization:
    ok: bool
    reason: str | None = None
    high_risk: bool = False


def load_tool_map(rows: list[Any]) -> dict[str, Any]:
    return {row.name: row for row in rows}


def authorize(tools: dict[str, Any], name: str, params: dict[str, Any] | None) -> Authorization:
    row = tools.get(name)
    if row is None:
        return Authorization(ok=False, reason="tool_not_legislated")
    arguments = params if isinstance(params, dict) else {}
    schema = row.param_schema if isinstance(row.param_schema, dict) else {}
    if schema.get("model") == "FinancialTransactionIntent":
        from govagent.registry.schemas import FinancialTransactionIntent

        try:
            FinancialTransactionIntent.model_validate(arguments)
        except (ValidationError, TypeError, ValueError) as exc:
            return Authorization(ok=False, reason=f"schema_violation: {exc}")
    else:
        required = schema.get("required") or []
        if not isinstance(required, list):
            return Authorization(ok=False, reason="schema_violation: required must be a list")
        missing = [key for key in required if key not in arguments]
        if missing:
            return Authorization(ok=False, reason="schema_violation: missing " + ", ".join(missing))

    if row.oci_repository and row.artifact_digest:
        from govagent.registry.harbor_verifier import HarborVerifier

        report = HarborVerifier().verify_tool_artifact(row.oci_repository, row.artifact_digest)
        if not report.get("verified"):
            return Authorization(ok=False, reason="harbor_blocked")

    high_risk = bool(row.requires_approval) or str(row.risk_level).lower() == "high"
    return Authorization(ok=True, high_risk=high_risk)
