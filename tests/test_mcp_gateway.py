from __future__ import annotations

from types import SimpleNamespace

import pytest

from govagent.extensions.mcp import GovernedMCPGateway
from govagent.guards import GovernanceViolation
from govagent.hitl import HITLManager
from govagent.policy import Policy
from govagent.telemetry import TelemetryManager


def _policy(**kwargs) -> Policy:
    data = {
        "metadata": {"agent_name": "mcp-test"},
        "registry_alignment": {
            "allowed_tools": ["lookup", "pay"],
            "high_risk_tools": ["pay"],
        },
        "fiscal_governance": {
            "global_limits": {
                "daily_budget_usd": 100.0,
                "transaction_ceiling": 50.0,
            }
        },
        "alignment": {"mission_statement": "Help with governed tools.", "prohibited_strategies": []},
    }
    data.update(kwargs)
    return Policy(data)


class AutoApprove:
    async def notify(self, request):
        return True


class AutoDeny:
    async def notify(self, request):
        return False


@pytest.mark.asyncio
async def test_gateway_allows_local_callable_and_redacts(monkeypatch):
    seen = {}

    def lookup(query: str) -> str:
        seen["query"] = query
        return f"ok:{query}"

    gateway = GovernedMCPGateway(policy=_policy(), telemetry=TelemetryManager(persist_jsonl=False))
    result = await gateway.call_tool("lookup", {"query": "status"}, fn=lookup)
    assert result.startswith("ok:")
    assert "query" in seen


@pytest.mark.asyncio
async def test_gateway_rejects_tools_off_allow_list():
    gateway = GovernedMCPGateway(policy=_policy(), telemetry=TelemetryManager(persist_jsonl=False))
    with pytest.raises(GovernanceViolation, match="allow-list"):
        await gateway.call_tool("shell", {"cmd": "ls"}, fn=lambda **k: "nope")


@pytest.mark.asyncio
async def test_gateway_fiscal_and_hitl_and_session():
    policy = _policy()
    gateway = GovernedMCPGateway(
        policy=policy,
        telemetry=TelemetryManager(persist_jsonl=False),
        hitl_manager=HITLManager(adapter=AutoApprove()),
    )

    def pay(amount: float) -> str:
        return f"paid:{amount}"

    result = await gateway.call_tool("pay", {"amount": 10.0}, fn=pay)
    assert result == "paid:10.0"

    denied = GovernedMCPGateway(
        policy=policy,
        telemetry=TelemetryManager(persist_jsonl=False),
        hitl_manager=HITLManager(adapter=AutoDeny()),
    )
    with pytest.raises(GovernanceViolation, match="denied"):
        await denied.call_tool("pay", {"amount": 10.0}, fn=pay)

    async def remote_call(name, arguments):
        return SimpleNamespace(name=name, content=arguments)

    session = SimpleNamespace(call_tool=remote_call)
    allowed = GovernedMCPGateway(policy=policy, telemetry=TelemetryManager(persist_jsonl=False))
    payload = await allowed.call_tool("lookup", {"query": "q"}, session=session)
    assert payload.name == "lookup"

    with pytest.raises(GovernanceViolation, match="No MCP session"):
        await allowed.call_tool("lookup", {"query": "q"})


@pytest.mark.asyncio
async def test_wrap_tool_and_async_callable():
    gateway = GovernedMCPGateway(policy=_policy(), telemetry=TelemetryManager(persist_jsonl=False))

    async def lookup(query: str) -> str:
        return query.upper()

    wrapped = gateway.wrap_tool("lookup", lookup)
    assert await wrapped(query="ab") == "AB"
