"""Tenant evaluate path.

The loop matches govagent 3.0.3 ``ExecutiveAgent.execute``. Schema checks go
through ``validate_tenant_intent``, which calls the library method with the
per-request tool map. The process-global registry is not modified.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from govagent.agent import ExecutiveAgent
from govagent.context import reset_current_agent, set_current_agent
from govagent.guards import GovernanceViolation
from govagent.hitl.manager import HITLManager
from govagent.llm.base import LLMRequest
from govagent.pricing import PricingEngine

from govagent_platform.runtime.hitl_adapter import ReplayVoteAdapter
from govagent_platform.runtime.ledger import assert_spend_allowed
from govagent_platform.runtime.tool_map import authorize
from govagent_platform.runtime.validation import validate_tenant_intent


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
        month_spend: float = 0.0,
        monthly_ceiling: float | None = None,
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
        self.month_spend = month_spend
        self.monthly_ceiling = monthly_ceiling
        self.pricing = PricingEngine()
        self.pending_id: str | None = None
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
            projected_month = self.month_spend + step_cost
            if self.monthly_ceiling is not None and projected_month > self.monthly_ceiling:
                raise GovernanceViolation(
                    "MONTHLY TCO REJECT: Projected month spend "
                    f"${projected_month:.2f} exceeds the plan ceiling of ${self.monthly_ceiling:.2f}."
                )
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
        """3.0.3 loop. The schema call receives this request's tool map."""

        token = set_current_agent(self)
        sanitized_task = self.guard.privacy.redact_task(task)
        self.telemetry.start_trace(self.persona, sanitized_task)
        current_step, total_tokens = 0, 0
        last_active_model = "None Assigned"
        try:
            while current_step < 10:
                request_payload = LLMRequest(
                    prompt=sanitized_task,
                    system_instruction=f"You are a {self.persona}. Corporate Policy Boundaries apply.",
                    temperature=0.0,
                )
                context_metadata = {
                    "routing_mode": getattr(self.policy, "routing_mode", "LOCAL_ONLY"),
                    "default_provider": getattr(self.policy, "default_provider", "local_ollama"),
                    "agent_risk_profile": self.policy.metadata.get("risk_profile", "standard"),
                    "contains_pii": getattr(self.guard.privacy, "last_execution_had_pii", False),
                    "current_step": current_step,
                }
                if self.router is None:
                    snapshot = await self._finalize(
                        "success",
                        "Task complete (Test Sandbox Mode).",
                        total_tokens,
                        model_node="mock_sandbox",
                    )
                    return _result(snapshot, self.pending_id)

                response = await self.router.route_and_generate(request_payload, context_metadata)
                if hasattr(response, "selected_model"):
                    last_active_model = response.selected_model
                elif "local_ollama" in context_metadata["default_provider"]:
                    last_active_model = "local_ollama"

                tokens_used = response.raw_usage.get("total_tokens", 0)
                cost_incurred = response.raw_usage.get("estimated_cost_usd", 0.0)
                total_tokens += tokens_used

                if response.tool_calls:
                    tool_call = response.tool_calls[0]
                    intent = {
                        "thought": response.text[:250] + "...",
                        "action": tool_call.get("name"),
                        "params": tool_call.get("args", {}),
                        "full_audit_log": response.text,
                    }
                else:
                    intent = {
                        "thought": response.text[:250] + "...",
                        "action": "complete" if "complete" in response.text.lower() else None,
                        "params": {},
                        "full_audit_log": response.text,
                    }

                if not intent.get("action") or intent["action"] == "complete":
                    snapshot = await self._finalize(
                        "success", "Task complete.", total_tokens, model_node=last_active_model
                    )
                    return _result(snapshot, self.pending_id)

                try:
                    validation = validate_tenant_intent(
                        self.tool_map,
                        intent.get("action"),
                        intent.get("params", {}),
                    )
                except (ValidationError, ValueError, TypeError) as schema_error:
                    snapshot = await self._finalize(
                        "blocked",
                        f"Schema Violation: {schema_error}",
                        total_tokens,
                        model_node=last_active_model,
                    )
                    return _result(snapshot, self.pending_id)
                if isinstance(validation, dict):
                    if not validation.get("valid", False):
                        snapshot = await self._finalize(
                            "blocked",
                            f"Schema Violation: {validation.get('error')}",
                            total_tokens,
                            model_node=last_active_model,
                        )
                        return _result(snapshot, self.pending_id)
                elif validation is not True:
                    snapshot = await self._finalize(
                        "blocked",
                        "Schema Violation",
                        total_tokens,
                        model_node=last_active_model,
                    )
                    return _result(snapshot, self.pending_id)

                await self.evaluate(guards=["fiscal", "judiciary"], intent=intent, value=cost_incurred)
                self.telemetry.current_session.estimated_cost_usd += cost_incurred
                result = await self.perform_action(intent.get("action"), intent.get("params", {}))
                self.telemetry.log_step(intent.get("thought", ""), intent.get("action"), str(result))
                if intent.get("action") == "execute_financial_transaction":
                    snapshot = await self._finalize(
                        "success",
                        result,
                        total_tokens,
                        impact=intent["params"].get("amount", 0.0),
                        model_node=last_active_model,
                    )
                    return _result(snapshot, self.pending_id)
                current_step += 1

            snapshot = await self._finalize(
                "timeout", "Max steps reached.", total_tokens, model_node=last_active_model
            )
            return _result(snapshot, self.pending_id)
        except GovernanceViolation as gv:
            snapshot = await self._finalize("blocked", str(gv), total_tokens, model_node=last_active_model)
            return _result(snapshot, self.pending_id)
        except PermissionError as exc:
            return RunResult("", "denied", str(exc), None)
        except Exception as exc:
            snapshot = await self._finalize("error", str(exc), total_tokens, model_node=last_active_model)
            return _result(snapshot, self.pending_id)
        finally:
            reset_current_agent(token)


def _result(snapshot, pending_id: str | None) -> RunResult:
    return RunResult(
        trace_id=snapshot.trace_id,
        status=snapshot.status,
        output="" if snapshot.output is None else str(snapshot.output),
        approval_request_id=pending_id,
    )


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
