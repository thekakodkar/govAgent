from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from govagent.guards.circuit_breaker import GovernanceViolation

logger = logging.getLogger("govagent.extensions.ibm.bob_mcp_proxy")


class BobMCPProxyGateway:
    """
    Model Context Protocol Interceptor Plane for IBM Bob workflows.
    Wraps tool invocation scopes to enforce real-time data privacy and semantic alignment.
    """

    def __init__(self, semantic_guard: Any = None, privacy_guard: Any = None, hitl_manager: Any = None):
        self.semantic_guard = semantic_guard
        self.privacy_guard = privacy_guard
        self.hitl_manager = hitl_manager

    def govern_mcp_tool(self, tool_name: str, core_function: Callable[..., Any]) -> Callable[..., Any]:
        """Decorates an IBM Bob MCP tool function with a managed governance proxy wrapper."""

        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.info("🏢 IBM Bob MCP Proxy: Intercepting execution for tool '%s'...", tool_name)

            combined_input = " ".join([str(v) for v in kwargs.values()] + [str(a) for a in args])

            if self.privacy_guard:
                redact = getattr(self.privacy_guard, "redact_task", None) or getattr(
                    self.privacy_guard, "anonymize", None
                )
                if callable(redact):
                    combined_input = redact(combined_input)
                else:
                    logger.warning("⚠️ Privacy guard missing expected 'redact_task' or 'anonymize' signature.")

            if self.semantic_guard:
                alignment_score = self.semantic_guard.evaluate_alignment(combined_input)
                if alignment_score == 0.0:
                    logger.error(
                        "🛑 IBM Bob MCP Proxy: Semantic alignment breach detected for tool '%s'.",
                        tool_name,
                    )
                    raise GovernanceViolation(
                        f"IBM BOB MCP PROXY REJECT: Tool invocation for '{tool_name}' "
                        "violated corporate policy alignment thresholds."
                    )

            if asyncio.iscoroutinefunction(core_function):
                return await core_function(*args, **kwargs)
            return await asyncio.to_thread(core_function, *args, **kwargs)

        return async_wrapper
