"""Compare a tenant policy document with the active global floor.

The numeric comparison reads ``fiscal_governance.global_limits``, which is the
shape already used by the YAML files. It does not change ``govagent.policy.Policy``.
``Policy(document)`` is called so a document the library cannot construct is rejected.
"""

from __future__ import annotations

from typing import Any

_CEILING_KEYS = (
    "daily_budget_usd",
    "transaction_ceiling",
    "recursive_tco_limit",
    "recursive_tco_ceiling",
    "max_per_transaction",
    "max_spend_usd",
)


class FloorViolation(Exception):
    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class PolicyDocumentRejected(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _limits(document: dict[str, Any]) -> dict[str, Any]:
    fiscal = document.get("fiscal_governance") or {}
    if not isinstance(fiscal, dict):
        return {}
    limits = fiscal.get("global_limits") or {}
    if not isinstance(limits, dict):
        return {}
    return limits


def _guards(document: dict[str, Any]) -> list[str] | None:
    guardrails = document.get("security_guardrails") or {}
    if not isinstance(guardrails, dict) or "required_guards" not in guardrails:
        return None
    guards = guardrails.get("required_guards")
    if guards is None:
        return None
    if not isinstance(guards, list):
        raise FloorViolation(["security_guardrails.required_guards must be a list"])
    return [str(item) for item in guards]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def assert_tenant_tightens(floor_document: dict[str, Any], tenant_document: dict[str, Any]) -> None:
    """Reject a tenant document that grants a higher ceiling or drops a required guard."""

    reasons: list[str] = []
    floor_limits = _limits(floor_document)
    tenant_limits = _limits(tenant_document)
    for key in _CEILING_KEYS:
        if key not in floor_limits or key not in tenant_limits:
            continue
        floor_value = _number(floor_limits[key])
        tenant_value = _number(tenant_limits[key])
        if floor_value is None or tenant_value is None:
            continue
        if tenant_value > floor_value:
            reasons.append(
                f"fiscal_governance.global_limits.{key} {tenant_value} exceeds floor {floor_value}"
            )

    floor_guards = _guards(floor_document) or []
    tenant_guards = _guards(tenant_document)
    if tenant_guards is not None:
        missing = [guard for guard in floor_guards if guard not in tenant_guards]
        if missing:
            reasons.append("tenant policy drops required guards: " + ", ".join(missing))

    if reasons:
        raise FloorViolation(reasons)


def ensure_library_accepts(document: dict[str, Any]) -> None:
    """Construct the existing library Policy. Import happens here, not at package import."""

    from govagent.policy import Policy

    if not isinstance(document, dict):
        raise PolicyDocumentRejected("Policy document must be an object")
    try:
        Policy(document)
    except Exception as exc:
        raise PolicyDocumentRejected(str(exc)) from exc
