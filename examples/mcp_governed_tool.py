"""Govern a local (or official MCP session) tool call with GovAgent policy rails.

Install the optional SDK extra with ``pip install 'govagent[mcp]'`` if you want
to pass a real ``mcp.ClientSession``. The gateway itself does not require the SDK
when you provide a local callable.

This example is a demonstration, not a certification.
"""

from __future__ import annotations

import asyncio

from govagent.extensions.mcp import GovernedMCPGateway
from govagent.hitl import HITLManager
from govagent.policy import Policy
from govagent.telemetry import TelemetryManager


class AutoApprove:
    async def notify(self, request):
        return True


def lookup(query: str) -> str:
    return f"records matching {query}"


async def main() -> None:
    policy = Policy(
        {
            "metadata": {"agent_name": "mcp-demo"},
            "registry_alignment": {
                "allowed_tools": ["lookup"],
                "high_risk_tools": [],
            },
            "fiscal_governance": {"global_limits": {"daily_budget_usd": 25.0}},
            "alignment": {"mission_statement": "Answer lookup requests safely."},
        }
    )
    gateway = GovernedMCPGateway(
        policy=policy,
        telemetry=TelemetryManager(persist_jsonl=False),
        hitl_manager=HITLManager(adapter=AutoApprove()),
    )
    print(await gateway.call_tool("lookup", {"query": "Q4 invoices"}, fn=lookup))


if __name__ == "__main__":
    asyncio.run(main())
