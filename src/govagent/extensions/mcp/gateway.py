"""Govern MCP tool calls with the same rails as ExecutiveAgent.

The official ``mcp`` Python SDK is an optional extra (``govagent[mcp]``).
This gateway does not require the SDK when you pass a local callable.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

from govagent.guards import CircuitBreaker, GovernanceViolation, SemanticGuard
from govagent.guards.privacy import PrivacyGuard
from govagent.hitl import HITLManager
from govagent.policy import Policy
from govagent.telemetry import TelemetryManager

logger = logging.getLogger("govagent.extensions.mcp")


class GovernedMCPGateway:
    """Apply policy allow-list, privacy, semantic, fiscal, HITL, and audit rails to a tool call."""

    def __init__(
        self,
        policy: Policy,
        *,
        telemetry: TelemetryManager | None = None,
        hitl_manager: HITLManager | None = None,
        semantic_guard: SemanticGuard | None = None,
        privacy_guard: PrivacyGuard | None = None,
    ):
        self.policy = policy
        alignment = getattr(policy, "alignment", {}) or {}
        self.semantic_guard = semantic_guard or SemanticGuard(
            mission=alignment.get("mission_statement", ""),
            prohibited=alignment.get("prohibited_strategies", []),
            threshold=alignment.get("min_similarity_score", 0.85),
        )
        self.breaker = CircuitBreaker(policy, self.semantic_guard)
        self.privacy = privacy_guard or self.breaker.privacy
        self.telemetry = telemetry or TelemetryManager()
        self.hitl = hitl_manager or HITLManager()

    def _redact_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        redacted: dict[str, Any] = {}
        for key, value in arguments.items():
            if isinstance(value, str):
                redacted[key] = self.privacy.redact_task(value)
            else:
                redacted[key] = value
        return redacted

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        session: Any = None,
        fn: Callable[..., Any] | None = None,
    ) -> Any:
        """Govern and then invoke an MCP session tool or a local callable."""
        arguments = dict(arguments or {})
        if not self.telemetry.current_session:
            self.telemetry.start_trace("mcp-gateway", f"call_tool:{name}")
        self.telemetry.record_guard("privacy")

        allowed = self.policy.allowed_tools
        if allowed and name not in allowed:
            raise GovernanceViolation(
                f"UNAUTHORIZED TOOL: '{name}' is not on the policy allow-list {allowed}."
            )

        redacted = self._redact_arguments(arguments)
        combined = " ".join(str(v) for v in redacted.values())
        self.breaker.check_semantic_alignment(combined)
        self.telemetry.record_guard("semantic")

        await self.breaker.evaluate(tool_name=name, args=redacted, thought=combined)
        self.telemetry.record_guard("fiscal")

        if self.policy.is_high_risk(name):
            approved = await self.hitl.secure_approval(
                agent_id="mcp-gateway",
                reason=f"MCP tool '{name}' requires judiciary approval",
                context={"action": name, "params": redacted},
                triggered_by="mcp",
                config=self.policy.judiciary_settings,
            )
            self.telemetry.record_guard("judiciary")
            if not approved:
                raise GovernanceViolation(f"Human Judiciary denied request for {name}")

        if session is not None and hasattr(session, "call_tool"):
            result = session.call_tool(name, redacted)
            if inspect.isawaitable(result):
                result = await result
        elif fn is not None:
            result = fn(**redacted) if redacted else fn()
            if inspect.isawaitable(result):
                result = await result
        else:
            raise GovernanceViolation("No MCP session or local callable was provided.")

        self.telemetry.log_step(combined, name, str(result))
        await self.telemetry.finalize(status="success")
        return result

    def wrap_tool(self, name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Return an async wrapper that runs ``fn`` through ``call_tool``."""

        async def _wrapped(**kwargs: Any) -> Any:
            return await self.call_tool(name, kwargs, fn=fn)

        return _wrapped
