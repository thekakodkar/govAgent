"""Tenant evaluate path. The loop is ExecutiveAgent.execute from govagent 3.0.3."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from govagent.agent import ExecutiveAgent
from govagent.guards import GovernanceViolation
from govagent.hitl.manager import HITLManager
from govagent.pricing import PricingEngine
from govagent.registry import registry as public_registry
from govagent.registry.schemas import FinancialTransactionIntent, ToolManifest

from govagent_platform.runtime.hitl_adapter import ReplayVoteAdapter
from govagent_platform.runtime.ledger import assert_spend_allowed
from govagent_platform.runtime.tool_map import authorize

_REGISTRY_LOCK = threading.Lock()


class RunResult:
    def __init__(self, trace_id: str, status: str, output: str, approval_request_id: str | None):
        self.trace_id = trace_id
        self.status = status
        self.output = output
        self.approval_request_id = approval_request_id


class TenantExecutiveAgent(ExecutiveAgent):
    def __init__(
        self,
        persona: str,
        policy,
        router,
        *,
        tool_map: dict[str, Any],
        exporter,
        all_time: float,
        today: float,
        on_pending: Callable[..., str],
        telemetry=None,
        hitl_manager: HITLManager | None = None,
    ):
        hitl = hitl_manager or HITLManager(adapter=ReplayVoteAdapter([]))
        super().__init__(persona, policy, router, telemetry, hitl)
        self.tool_map = tool_map
        self.exporter = exporter
        self.all_time = all_time
        self.today = today
        self.on_pending = on_pending
        self.pricing = PricingEngine()
        self.pending_id: str | None = None
        self._bound_names: list[str] = []
        self._saved_entries: dict[str, Any] = {}
        self.telemetry.add_exporter(exporter)

    async def perform_action(self, action: str, params: dict) -> str:
        if not action or action == "complete":
            return "Task complete."
        return f"AUTHORIZED:{action}"

    async def evaluate(self, guards, intent=None, value=0.0):
        """Fiscal, semantic, and tenant-tool checks. Schema results come from execute()."""

        action = (intent or {}).get("action")
        params = (intent or {}).get("params") or {}
        decision = authorize(self.tool_map, action, params)
        if not decision.ok:
            raise GovernanceViolation(decision.reason or "tool_not_legislated")
        thought = (intent or {}).get("thought") or ""
        if self.semantic_guard.evaluate_alignment(thought) == 0.0:
            raise GovernanceViolation("semantic_breach")
        if "fiscal" in (guards or []):
            tokens, model = _latest_usage(self.router)
            step_cost = self.pricing.calculate_cost(model, tokens)
            self.exporter.incremental_steps.append(step_cost)
            self.exporter.model_name = model
            self.exporter.tokens = tokens
            assert_spend_allowed(self.guard, step_cost, self.all_time, self.today)
        if decision.high_risk:
            amount = _amount(params)
            required_score, risk_tier = await _probe_tier(self.persona, amount)
            trace_id = self.telemetry.current_session.trace_id
            self.pending_id = self.on_pending(
                trace_id=trace_id,
                amount=amount,
                required_score=required_score,
                risk_tier=risk_tier,
                tool_name=action,
                params=params,
            )
            self.exporter.approval_request_id = self.pending_id
            raise GovernanceViolation("approval_required")
        return True

    async def _finalize(self, status: str, output: Any, tokens: int, impact: float = 0.0, model_node: str = "None Assigned"):
        if self.pending_id and "approval_required" in str(output):
            status = "pending"
            output = "approval_required"
        if self.telemetry.current_session is not None:
            guards = ["privacy"]
            if status in {"success", "pending", "blocked"}:
                guards.extend(["semantic", "fiscal"])
            if self.pending_id:
                guards.append("judiciary")
            self.telemetry.current_session.guards_evaluated = guards
        self.exporter.tokens = tokens or self.exporter.tokens
        return await super()._finalize(status, output, tokens, impact, model_node)

    async def execute(self, task: str) -> RunResult:
        """Run govagent 3.0.3 execute(). Schema failures stay blocked inside that method."""

        self._bind_registry()
        try:
            snapshot = await super().execute(task)
        except PermissionError as exc:
            return self._denied(str(exc))
        finally:
            self._unbind_registry()
        return RunResult(
            trace_id=snapshot.trace_id,
            status=snapshot.status,
            output="" if snapshot.output is None else str(snapshot.output),
            approval_request_id=self.pending_id,
        )

    def _denied(self, reason: str) -> RunResult:
        return RunResult("", "denied", reason, None)

    def _bind_registry(self) -> None:
        _REGISTRY_LOCK.acquire()
        self._saved_entries = {}
        self._bound_names = []
        for name, row in self.tool_map.items():
            if name in public_registry.tools:
                self._saved_entries[name] = public_registry.tools[name]
            public_registry.tools[name] = _registry_entry(row)
            self._bound_names.append(name)

    def _unbind_registry(self) -> None:
        try:
            for name in self._bound_names:
                if name in self._saved_entries:
                    public_registry.tools[name] = self._saved_entries[name]
                else:
                    public_registry.tools.pop(name, None)
            self._bound_names = []
            self._saved_entries = {}
        finally:
            _REGISTRY_LOCK.release()


def _registry_entry(row: Any) -> dict[str, Any]:
    schema = None
    param_schema = row.param_schema if isinstance(getattr(row, "param_schema", None), dict) else {}
    if param_schema.get("model") == "FinancialTransactionIntent":
        schema = FinancialTransactionIntent
    risk = getattr(row, "risk_level", None) or "low"
    manifest = ToolManifest(
        name=row.name,
        description=getattr(row, "description", None) or row.name,
        risk_level=risk,
        oci_repository=getattr(row, "oci_repository", None),
        artifact_digest=getattr(row, "artifact_digest", None),
    )
    return {
        "func": _noop,
        "manifest": manifest,
        "schema": schema,
        "risk_level": risk,
        "cost_usd": 0.0,
    }


def _noop(*args, **kwargs):
    return None


def _latest_usage(router) -> tuple[int, str]:
    tokens = 0
    model = "scripted"
    for client in getattr(router, "clients", {}).values():
        tokens = int(getattr(client, "last_tokens", 0) or 0)
        model = str(getattr(client, "last_model", None) or getattr(client, "model_name", None) or "scripted")
    return tokens, model


def _amount(params: dict) -> float:
    raw = params.get("amount", 0) if isinstance(params, dict) else 0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


async def _probe_tier(persona: str, amount: float) -> tuple[float, str]:
    manager = HITLManager(adapter=ReplayVoteAdapter([]))
    await manager.secure_approval(
        agent_id=persona,
        reason="tier probe",
        context={"params": {"amount": amount}},
        triggered_by="judiciary",
        config={},
    )
    recorded = manager.history[-1]
    return float(recorded.required_score), recorded.risk_tier
