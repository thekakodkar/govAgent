from __future__ import annotations

import math
from typing import Any

from govagent.context import get_shared_fiscal_metrics

from .privacy import PrivacyGuard
from .semantic import SemanticGuard


class GovernanceViolation(Exception):
    """Institutional Exception raised on policy breach."""


def checked_amount(value: Any) -> float:
    """Return ``value`` as a finite, non-negative float or raise ``GovernanceViolation``.

    ``float("nan")`` compares false against every ceiling, and a negative amount lowers the
    projected total, so both would slip past a ``>`` check. Anything that is not a plain
    number fails closed instead of being treated as zero.
    """

    if isinstance(value, bool):
        raise GovernanceViolation("INVALID AMOUNT: a boolean is not a monetary amount.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise GovernanceViolation("INVALID AMOUNT: the amount is not a number.") from None
    if not math.isfinite(number) or number < 0:
        raise GovernanceViolation("INVALID AMOUNT: the amount must be a finite, non-negative number.")
    return number


class CircuitBreaker:
    """
    The Enforcement Layer of the Control Plane.
    Fiscal, per-transaction, and semantic sovereignty checks.
    """

    def __init__(self, policy: Any, semantic_guard: SemanticGuard | None = None):
        self.policy = policy
        self.semantic_guard = semantic_guard
        self.privacy = PrivacyGuard(policy)

    def _limits(self) -> dict[str, Any]:
        limits = getattr(self.policy, "global_limits", {}) or {}
        if not limits and hasattr(self.policy, "config"):
            limits = self.policy.config.get("global_limits", {}) or {}
        return limits

    def check_financial_risk(self, local_projected_cost: float) -> None:
        """Hardened fiscal gate over aggregate swarm spend plus the local action cost."""
        metrics = get_shared_fiscal_metrics()
        local_projected_cost = checked_amount(local_projected_cost)
        total_projected_cost = metrics["cumulative_spend"] + local_projected_cost

        limits = self._limits()
        tco_limit = limits.get("recursive_tco_ceiling", 150.0)
        daily_limit = limits.get("daily_budget_usd", 100.0)
        effective_limit = min(float(tco_limit), float(daily_limit))

        if total_projected_cost > effective_limit:
            raise GovernanceViolation(
                f"RECURSIVE TCO REJECT: Projected swarm spend ${total_projected_cost:.2f} "
                f"exceeds the institutional limit of ${effective_limit:.2f}."
            )

    def check_transaction_limit(self, amount: float) -> None:
        """Enforce per-transaction ceilings when the policy defines them."""
        amount = checked_amount(amount)
        limits = self._limits()
        caps = [
            limits.get("transaction_ceiling"),
            limits.get("max_per_transaction"),
        ]
        numeric_caps = [float(cap) for cap in caps if cap is not None]
        if not numeric_caps:
            return
        ceiling = min(numeric_caps)
        if float(amount) > ceiling:
            raise GovernanceViolation(
                f"TRANSACTION CEILING REJECT: Requested amount ${float(amount):.2f} "
                f"exceeds the per-transaction limit of ${ceiling:.2f}."
            )

    def check_semantic_alignment(self, thought: str) -> None:
        if not self.semantic_guard or not thought or not str(thought).strip():
            return
        score = self.semantic_guard.evaluate_alignment(thought)
        if score == 0.0:
            raise GovernanceViolation(
                "SEMANTIC ALIGNMENT BREACH: Reasoning or input matched a prohibited strategy."
            )

    async def evaluate(self, tool_name: str, args: dict[str, Any], thought: str = "") -> bool:
        """Three-stage check: semantic alignment, per-transaction cap, then fiscal TCO."""
        self.check_semantic_alignment(thought)
        projected = args.get("amount", 0.0)
        projected_value = 0.0 if projected is None or projected == "" else checked_amount(projected)
        self.check_transaction_limit(projected_value)
        self.check_financial_risk(projected_value)
        return True
