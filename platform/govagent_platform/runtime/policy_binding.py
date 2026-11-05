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
    # 3.1.0 already projects alignment and nested fiscal limits. 3.0.3 does not,
    # so fill only the attributes the constructed instance left unset.
    alignment = document.get("alignment")
    if isinstance(alignment, dict) and not getattr(policy, "alignment", None):
        policy.alignment = alignment
    oversight = document.get("oversight")
    if isinstance(oversight, dict) and not getattr(policy, "oversight", None):
        policy.oversight = oversight
    _fill_limits_for_3_0_3(policy, document)
    return policy


def _fill_limits_for_3_0_3(policy, document: dict[str, Any]) -> None:
    top = document.get("global_limits") if isinstance(document.get("global_limits"), dict) else {}
    fiscal = document.get("fiscal_governance") if isinstance(document.get("fiscal_governance"), dict) else {}
    nested = fiscal.get("global_limits") if isinstance(fiscal.get("global_limits"), dict) else {}
    merged = dict(getattr(policy, "global_limits", {}) or {})
    changed = False
    for key, value in nested.items():
        target = "recursive_tco_ceiling" if key == "recursive_tco_limit" else key
        if key in top or (key == "recursive_tco_limit" and "recursive_tco_ceiling" in top):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        current = merged.get(target)
        try:
            already = current is not None and float(current) == number
        except (TypeError, ValueError):
            already = False
        if not already:
            merged[target] = number
            changed = True
    if changed:
        policy.global_limits = merged


__all__ = ["hydrate_policy", "PolicyDocumentRejected"]
