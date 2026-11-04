"""Short governed loop. It subclasses ExecutiveAgent and does not call the stock execute()."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from govagent.agent import ExecutiveAgent
from govagent.context import reset_current_agent, set_current_agent
from govagent.guards import GovernanceViolation
from govagent.hitl.manager import HITLManager
from govagent.llm.base import LLMRequest
from govagent.pricing import PricingEngine

from govagent_platform.runtime.hitl_adapter import ReplayVoteAdapter
from govagent_platform.runtime.ledger import assert_spend_allowed
from govagent_platform.runtime.tool_map import authorize

_STEP_CAP = 3


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
        self.telemetry.add_exporter(exporter)

    async def perform_action(self, action: str, params: dict) -> str:
        if not action or action == "complete":
            return "Task complete."
        return f"AUTHORIZED:{action}"

    async def execute(self, task: str) -> RunResult:
        token = set_current_agent(self)
        total_tokens = 0
        try:
            sanitized = self.guard.privacy.redact_task(task)
            trace_id = self.telemetry.start_trace(self.persona, sanitized)
            self._remember(["privacy"])
            for _step in range(_STEP_CAP):
                response = await self.router.route_and_generate(
                    LLMRequest(
                        prompt=sanitized,
                        system_instruction=f"You are a {self.persona}. Corporate Policy Boundaries apply.",
                        temperature=0.0,
                    ),
                    {
                        "routing_mode": getattr(self.policy, "routing_mode", "LOCAL_ONLY"),
                        "default_provider": getattr(self.policy, "default_provider", "scripted"),
                        "current_step": _step,
                    },
                )
                tokens = int(response.raw_usage.get("total_tokens") or 0)
                if tokens == 0:
                    tokens = int(response.raw_usage.get("prompt_tokens") or 0) + int(
                        response.raw_usage.get("completion_tokens") or 0
                    )
                total_tokens += tokens
                step_cost = self.pricing.calculate_cost(response.model_name, tokens)
                self.exporter.incremental_steps.append(step_cost)
                self.exporter.model_name = response.model_name
                self.exporter.tokens = total_tokens
                if not response.tool_calls:
                    return await self._finish(trace_id, "success", "Task complete.", ["privacy"])
                call = response.tool_calls[0]
                name = call.get("name")
                params = call.get("args") or {}
                decision = authorize(self.tool_map, name, params)
                if not decision.ok:
                    return await self._finish(
                        trace_id,
                        "blocked",
                        decision.reason or "blocked",
                        ["privacy", "registry"],
                    )
                alignment = self.semantic_guard.evaluate_alignment(response.text or "")
                if alignment == 0.0:
                    return await self._finish(
                        trace_id,
                        "blocked",
                        "semantic_breach",
                        ["privacy", "semantic"],
                    )
                assert_spend_allowed(self.guard, step_cost, self.all_time, self.today)
                if decision.high_risk:
                    amount = _amount(params)
                    required_score, risk_tier = await _probe_tier(self.persona, amount)
                    approval_id = self.on_pending(
                        trace_id=trace_id,
                        amount=amount,
                        required_score=required_score,
                        risk_tier=risk_tier,
                        tool_name=name,
                        params=params,
                    )
                    self.exporter.approval_request_id = approval_id
                    result = await self._finish(
                        trace_id,
                        "pending",
                        "approval_required",
                        ["privacy", "semantic", "fiscal", "judiciary"],
                    )
                    result.approval_request_id = approval_id
                    return result
                result_text = await self.perform_action(name, params)
                self.telemetry.log_step(response.text or "", name, result_text)
                return await self._finish(
                    trace_id,
                    "success",
                    result_text,
                    ["privacy", "semantic", "fiscal"],
                )
            return await self._finish(trace_id, "error", "Max steps reached.", ["privacy"])
        except GovernanceViolation as exc:
            trace_id = getattr(getattr(self.telemetry, "current_session", None), "trace_id", "")
            return await self._finish(str(trace_id), "blocked", str(exc), ["privacy", "fiscal"])
        except Exception as exc:
            trace_id = getattr(getattr(self.telemetry, "current_session", None), "trace_id", "")
            return await self._finish(str(trace_id), "error", str(exc), ["privacy"])
        finally:
            reset_current_agent(token)

    def _remember(self, guards: list[str]) -> None:
        if self.telemetry.current_session is not None:
            self.telemetry.current_session.guards_evaluated = list(guards)

    async def _finish(self, trace_id: str, status: str, output: str, guards: list[str]) -> RunResult:
        self._remember(guards)
        if self.telemetry.current_session is not None:
            await self.telemetry.finalize(status=status, tokens=self.exporter.tokens or 0)
        return RunResult(trace_id, status, output, self.exporter.approval_request_id)


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
