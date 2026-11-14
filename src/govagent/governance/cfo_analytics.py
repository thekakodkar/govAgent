# src/govagent/governance/cfo_analytics.py
import datetime
from typing import Any

from pydantic import BaseModel, Field


class CostCenterAllocation(BaseModel):
    cost_center_id: str
    gl_account: str
    allocated_spend_usd: float = 0.0
    transaction_count: int = 0
    token_usage_total: int = 0


class CFORiskReport(BaseModel):
    total_realized_spend_usd: float = 0.0
    value_at_risk_prevented_usd: float = 0.0
    burn_rate_anomaly_detected: bool = False
    average_cost_per_work_unit: float = 0.0
    allocations_by_center: dict[str, CostCenterAllocation] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class CFOAnalyticsEngine:
    def __init__(self):
        self.snapshots: list[Any] = []
        self.allocations: dict[str, CostCenterAllocation] = {}

    def record_execution(self, snapshot: Any) -> None:
        """Primary ingestion entrypoint for execution snapshots."""
        self.snapshots.append(snapshot)
        self._aggregate_snapshot(snapshot)

    def record_snapshot(self, snapshot: Any) -> None:
        """Alias for backward compatibility."""
        self.record_execution(snapshot)

    def record_transaction(self, snapshot: Any) -> None:
        """Alias for backward compatibility."""
        self.record_execution(snapshot)

    def _aggregate_snapshot(self, snapshot: Any) -> None:
        cost_center = getattr(snapshot, "cost_center", "CC-GENAI-DEFAULT")
        gl_account = getattr(snapshot, "gl_account", "GL-640100-SOFTWARE")
        spend = float(getattr(snapshot, "recursive_tco_usd", 0.0) or 0.0)
        tokens = int(getattr(snapshot, "total_tokens", 0) or 0)

        # Dynamically register Cost Centers derived from policy YAMLs
        if cost_center not in self.allocations:
            self.allocations[cost_center] = CostCenterAllocation(
                cost_center_id=cost_center,
                gl_account=gl_account,
                allocated_spend_usd=0.0,
                transaction_count=0,
                token_usage_total=0
            )

        alloc = self.allocations[cost_center]
        alloc.allocated_spend_usd += spend
        alloc.transaction_count += 1
        alloc.token_usage_total += tokens

    def analyze(self) -> CFORiskReport:
        """Aggregates Value-at-Risk, total spend, and P&L allocations across dynamic centers."""
        total_realized_spend = sum(a.allocated_spend_usd for a in self.allocations.values())
        total_tx = sum(a.transaction_count for a in self.allocations.values())
        avg_unit_cost = (total_realized_spend / total_tx) if total_tx > 0 else 0.00000

        prevented_risk = 0.0
        burn_anomaly = False

        for snap in self.snapshots:
            status = getattr(snap, "status", "")
            exposure = float(getattr(snap, "requested_exposure_usd", 0.0) or 0.0)
            spend = float(getattr(snap, "recursive_tco_usd", 0.0) or 0.0)

            if status in ["BLOCKED", "PENDING"]:
                prevented_risk += exposure

            if spend > 0.50:
                burn_anomaly = True

        return CFORiskReport(
            total_realized_spend_usd=total_realized_spend,
            value_at_risk_prevented_usd=prevented_risk,
            burn_rate_anomaly_detected=burn_anomaly,
            average_cost_per_work_unit=avg_unit_cost,
            allocations_by_center=self.allocations
        )