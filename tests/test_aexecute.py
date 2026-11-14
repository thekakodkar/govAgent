from __future__ import annotations

import asyncio

import pytest

from govagent.agent import ExecutiveAgent
from govagent.hitl import HITLManager
from govagent.llm.base import LLMResponse
from govagent.policy import Policy
from govagent.registry import registry, tool
from govagent.telemetry import TelemetryManager


class AutoApprove:
    async def notify(self, request):
        return True


class Router:
    async def route_and_generate(self, request, context):
        return LLMResponse(
            text="Task complete.",
            tool_calls=[],
            raw_usage={"total_tokens": 3, "estimated_cost_usd": 0.0},
            model_name="scripted",
        )


@pytest.fixture
def echo_tool():
    @tool(name="echo_status")
    def _echo(msg: str) -> str:
        return f"echo:{msg}"

    yield
    registry.tools.pop("echo_status", None)


def _agent():
    policy = Policy(
        {
            "metadata": {"agent_name": "Director"},
            "registry_alignment": {"allowed_tools": ["echo_status"]},
            "fiscal_governance": {"global_limits": {"daily_budget_usd": 50.0, "transaction_ceiling": 20.0}},
        }
    )
    return ExecutiveAgent(
        persona="Director",
        policy=policy,
        router=Router(),
        hitl_manager=HITLManager(adapter=AutoApprove()),
        telemetry=TelemetryManager(persist_jsonl=False),
    )


@pytest.mark.asyncio
async def test_aexecute_and_awaitable_execute(echo_tool):
    agent = _agent()
    via_aexecute = await agent.aexecute("Say hi")
    assert via_aexecute.status == "success"
    via_execute = await agent.execute("Say hi again")
    assert via_execute.status == "success"
    assert via_execute.output


def test_sync_caller_can_drive_aexecute(echo_tool):
    agent = _agent()
    snapshot = asyncio.run(agent.aexecute("Say hi from sync"))
    assert snapshot.output
