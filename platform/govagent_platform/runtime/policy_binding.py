"""Attach the document sections ExecutiveAgent already reads.

``Policy(document)`` keeps its current behavior. The attributes set here exist
only on this instance.
"""

from __future__ import annotations

from typing import Any

from govagent_platform.services.policy_floor import PolicyDocumentRejected, ensure_library_accepts


def hydrate_policy(document: dict[str, Any]):
    ensure_library_accepts(document)
    from govagent.policy import Policy

    policy = Policy(document)
    alignment = document.get("alignment")
    if isinstance(alignment, dict):
        policy.alignment = alignment
    oversight = document.get("oversight")
    if isinstance(oversight, dict):
        policy.oversight = oversight

    limits = {}
    fiscal = document.get("fiscal_governance")
    if isinstance(fiscal, dict) and isinstance(fiscal.get("global_limits"), dict):
        limits = fiscal["global_limits"]
    merged = dict(getattr(policy, "global_limits", {}) or {})
    if "daily_budget_usd" in limits:
        merged["daily_budget_usd"] = float(limits["daily_budget_usd"])
    if "recursive_tco_limit" in limits:
        merged["recursive_tco_ceiling"] = float(limits["recursive_tco_limit"])
    elif "recursive_tco_ceiling" in limits:
        merged["recursive_tco_ceiling"] = float(limits["recursive_tco_ceiling"])
    policy.global_limits = merged
    return policy


__all__ = ["hydrate_policy", "PolicyDocumentRejected"]
