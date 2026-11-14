from __future__ import annotations

import asyncio
import inspect
import logging
import os
from typing import Any

from pydantic import ValidationError

from govagent.context import reset_current_agent, set_current_agent
from govagent.governance.meta import MetaGovernor
from govagent.guards import CircuitBreaker, GovernanceViolation, SemanticGuard
from govagent.hitl import HITLManager, SlackJudiciaryAdapter
from govagent.llm.base import LLMRequest
from govagent.policy import Policy
from govagent.registry import ExecutionSnapshot, registry
from govagent.telemetry import TelemetryManager

logger = logging.getLogger("govagent.agent")

_AMENDMENT_TYPES = {"POLICY_AMENDMENT_PROPOSAL", "POLICY_AMENDMENT_PROPOSALS"}


def _usage_number(raw_usage: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = raw_usage.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_model_name(response: Any, context_metadata: dict[str, Any]) -> str:
    name = getattr(response, "selected_model", None) or getattr(response, "model_name", None)
    if name:
        return str(name)
    provider = str(context_metadata.get("default_provider") or "")
    if "local_ollama" in provider:
        return "local_ollama"
    return "None Assigned"


class ExecutiveAgent:
    def __init__(
        self,
        persona: str,
        policy: Policy,
        router: Any,  # Sovereign Routing Bus injected cleanly
        telemetry: TelemetryManager | None = None,
        hitl_manager: HITLManager | None = None,
    ):
        self.persona = persona
        self.policy = policy
        self.router = router

        align_config = getattr(policy, "alignment", {}) or {}
        self.semantic_guard = SemanticGuard(
            mission=align_config.get("mission_statement", ""),
            prohibited=align_config.get("prohibited_strategies", []),
            threshold=align_config.get("min_similarity_score", 0.85),
        )

        self.guard = CircuitBreaker(policy, self.semantic_guard)
        self.telemetry = telemetry or TelemetryManager()
        self.hitl = hitl_manager or HITLManager()

    @classmethod
    def bootstrap(cls, policy_path: str, router_client: Any, slack_channel: str | None = None) -> ExecutiveAgent:
        """Institutional Factory: Fully pluggable Enterprise Setup."""
        policy = Policy.from_yaml(policy_path)
        adapter = None
        if slack_channel:
            adapter = SlackJudiciaryAdapter(
                bot_token=os.getenv("SLACK_BOT_TOKEN"),
                app_token=os.getenv("SLACK_APP_TOKEN"),
                channel_id=slack_channel,
            )
            adapter.start()

        return cls(
            persona=policy.metadata.get("agent_name", "ExecutiveAgent"),
            policy=policy,
            router=router_client,
            hitl_manager=HITLManager(adapter=adapter),
        )

    async def evaluate(
        self,
        guards: list[str],
        intent: dict[str, Any] | None = None,
        value: float = 0.0,
    ) -> bool:
        """Modular Triage with Federated M-of-N support."""
        if not self.telemetry.current_session:
            self.telemetry.start_trace(self.persona, "Internal Evaluation")
        session = self.telemetry.current_session
        assert session is not None

        if intent and intent.get("thought"):
            await self.guard.evaluate(
                tool_name=intent.get("action") or "unknown",
                args=intent.get("params") or {},
                thought=str(intent["thought"]),
            )
            self.telemetry.record_guard("semantic")

        if "fiscal" in guards:
            current_total = session.estimated_cost_usd + value
            self.guard.check_financial_risk(current_total)
            self.telemetry.record_guard("fiscal")

        if "judiciary" in guards and intent and intent.get("action") != "complete":
            action_name = intent.get("action") or ""
            if self.policy.is_high_risk(action_name):
                judiciary_cfg = getattr(self.policy, "judiciary_settings", None) or {}
                if not judiciary_cfg:
                    judiciary_cfg = getattr(self.policy, "oversight", {}).get("judiciary", {})
                tool_cfg = judiciary_cfg.get("high_risk_protocol", judiciary_cfg) or {}

                approved = await self.hitl.secure_approval(
                    agent_id=self.persona,
                    reason=f"Judiciary Authorization Required: {action_name}",
                    context=intent,
                    triggered_by="judiciary",
                    config=tool_cfg,
                )
                self.telemetry.record_guard("judiciary")
                if not approved:
                    raise GovernanceViolation(f"Human Judiciary denied request for {action_name}")

        return True

    async def execute(self, task: str) -> ExecutionSnapshot:
        """Governed Reasoning Loop driven dynamically by YAML Infrastructure Parameters."""
        token = set_current_agent(self)
        sanitized_task = self.guard.privacy.redact_task(task)
        self.telemetry.start_trace(self.persona, sanitized_task)
        self.telemetry.record_guard("privacy")
        current_step, total_tokens = 0, 0
        last_active_model = "None Assigned"

        try:
            self.guard.check_semantic_alignment(sanitized_task)
            self.telemetry.record_guard("semantic")

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
                    "contains_pii": bool(getattr(self.guard.privacy, "last_execution_had_pii", False)),
                    "current_step": current_step,
                }

                if self.router is None:
                    return await self._finalize(
                        "success",
                        "Task complete (Test Sandbox Mode).",
                        total_tokens,
                        model_node="mock_sandbox",
                    )

                response = await self.router.route_and_generate(request_payload, context_metadata)
                last_active_model = _resolve_model_name(response, context_metadata)

                raw_usage = getattr(response, "raw_usage", {}) or {}
                tokens_used = int(_usage_number(raw_usage, "total_tokens", 0.0))
                cost_incurred = _usage_number(raw_usage, "estimated_cost_usd", 0.0)
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
                    return await self._finalize(
                        "success", "Task complete.", total_tokens, model_node=last_active_model
                    )

                try:
                    validation = registry.validate_intent_schema(
                        str(intent.get("action")),
                        intent.get("params") or {},
                    )
                except (ValidationError, ValueError, TypeError) as schema_error:
                    return await self._finalize(
                        "blocked",
                        f"Schema Violation: {schema_error}",
                        total_tokens,
                        model_node=last_active_model,
                    )
                if isinstance(validation, dict):
                    if not validation.get("valid", False):
                        return await self._finalize(
                            "blocked",
                            f"Schema Violation: {validation.get('error')}",
                            total_tokens,
                            model_node=last_active_model,
                        )
                elif validation is not True:
                    return await self._finalize(
                        "blocked",
                        "Schema Violation",
                        total_tokens,
                        model_node=last_active_model,
                    )

                await self.evaluate(guards=["fiscal", "judiciary"], intent=intent, value=cost_incurred)

                session = self.telemetry.current_session
                if session is not None:
                    session.estimated_cost_usd += cost_incurred
                result = await self.perform_action(str(intent.get("action")), intent.get("params") or {})
                self.telemetry.log_step(str(intent.get("thought") or ""), str(intent.get("action")), str(result))

                if intent.get("action") == "execute_financial_transaction":
                    params = intent.get("params") or {}
                    return await self._finalize(
                        "success",
                        result,
                        total_tokens,
                        impact=params.get("amount", 0.0),
                        model_node=last_active_model,
                    )

                current_step += 1

            return await self._finalize("timeout", "Max steps reached.", total_tokens, model_node=last_active_model)

        except GovernanceViolation as gv:
            return await self._finalize("blocked", str(gv), total_tokens, model_node=last_active_model)
        except Exception as exc:
            logger.exception("ExecutiveAgent.execute ended in error: %s", exc)
            return await self._finalize("error", str(exc), total_tokens, model_node=last_active_model)
        finally:
            reset_current_agent(token)

    async def _finalize(
        self,
        status: str,
        output: Any,
        tokens: int,
        impact: float = 0.0,
        model_node: str = "None Assigned",
    ) -> ExecutionSnapshot:
        """Institutional Finalization: Ensures proper metric mapping."""
        await self.telemetry.finalize(status=status, tokens=tokens)
        session = self.telemetry.current_session
        cost = session.estimated_cost_usd if session is not None else 0.0
        guards = list(session.guards_evaluated) if session is not None else []
        return ExecutionSnapshot(
            trace_id=session.trace_id if session is not None else "untraced",
            status=status,
            output=output,
            metrics={
                "fiscal_impact": impact,
                "total_tokens": tokens,
                "recursive_tco_usd": cost,
                "selected_model": model_node,
            },
            parent_trace_id=session.parent_trace_id if session is not None else None,
            selected_model=model_node,
            recursive_tco_usd=cost,
            guards_evaluated=guards,
            block_reason=str(output) if status == "blocked" else None,
            total_tokens=tokens,
            requested_exposure_usd=impact if isinstance(impact, (int, float)) else 0.0,
        )

    async def perform_action(self, action: str, params: dict[str, Any]) -> str:
        if not action or action == "complete":
            return "Task complete."

        allowed = self.policy.allowed_tools
        if allowed and action not in allowed:
            raise GovernanceViolation(
                f"UNAUTHORIZED TOOL: '{action}' is not on the policy allow-list {allowed}."
            )

        func = registry.verify_and_resolve_tool(action)
        self.telemetry.record_guard("harbor")
        result = func(**params) if params else func()
        if inspect.isawaitable(result) or asyncio.iscoroutine(result):
            result = await result
        return str(result)

    async def post_session_cleanup(self) -> None:
        """Executes institutional governance verification post-transaction lifecycle."""
        governor = MetaGovernor(log_path="logs/audit_trail.jsonl", friction_threshold=3)
        analysis_result = governor.analyze_friction()

        amendment_type = analysis_result.get("type")
        if (amendment_type in _AMENDMENT_TYPES or analysis_result.get("status") != "OPTIMAL") and "proposed_limit" in analysis_result:
            logger.info("ExecutiveAgent: Escalating policy amendment proposal to Federated Slack Courtroom.")

            slack_payload = (
                f"🚨 *GovAgent Governance Alert: Automated Policy Amendment Proposed*\n"
                f"• *Reason:* {analysis_result.get('reason', 'Systemic friction detected')}\n"
                f"• *Target File:* `{analysis_result.get('target_policy', 'policy.yaml')}`\n"
                f"• *Current Limit:* ${analysis_result.get('current_limit', 0.0):.4f}\n"
                f"• *Proposed Ceiling:* *${analysis_result.get('proposed_limit', 0.0):.4f}*\n"
                f"• *Impact:* {analysis_result.get('impact_assessment', 'N/A')}\n"
                f"👉 _Reply with 'APPROVE AMENDMENT' to apply this change to the root policy layer._"
            )

            adapter = getattr(self, "hitl", None) and getattr(self.hitl, "adapter", None)
            send = getattr(adapter, "send_message", None)
            if callable(send):
                await send(text=slack_payload)
