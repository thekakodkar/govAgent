"""Opt-in live tests. Cloud providers skip without env keys; MCP runs a local official-SDK server."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from govagent.extensions.mcp import GovernedMCPGateway
from govagent.guards import GovernanceViolation
from govagent.hitl import HITLManager
from govagent.llm.anthropic_client import AnthropicClient
from govagent.llm.base import LLMRequest
from govagent.llm.openai_client import AzureOpenAIClient, OpenAIClient
from govagent.policy import Policy
from govagent.telemetry import TelemetryManager

pytestmark = pytest.mark.live

_SERVER = Path(__file__).resolve().parent / "live_mcp_server.py"


def _has(*names: str) -> bool:
    return all(bool(os.environ.get(name, "").strip()) for name in names)


class AutoApprove:
    async def notify(self, request):
        return True


def _policy() -> Policy:
    return Policy(
        {
            "metadata": {"agent_name": "live-test"},
            "registry_alignment": {
                "allowed_tools": ["lookup"],
                "high_risk_tools": [],
            },
            "fiscal_governance": {"global_limits": {"daily_budget_usd": 25.0, "transaction_ceiling": 20.0}},
            "alignment": {"mission_statement": "Answer lookup requests safely.", "prohibited_strategies": []},
        }
    )


@pytest.mark.asyncio
@pytest.mark.skipif(not _has("OPENAI_API_KEY"), reason="OPENAI_API_KEY is not set")
async def test_live_openai_client_generate():
    pytest.importorskip("openai")
    client = OpenAIClient({"api_key": os.environ["OPENAI_API_KEY"], "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini")})
    response = await client.generate(LLMRequest(prompt="Reply with the single word pong.", max_tokens=16, temperature=0.0))
    assert response.model_name
    assert response.text or response.tool_calls
    assert "total_tokens" in response.raw_usage or "prompt_tokens" in response.raw_usage


@pytest.mark.asyncio
@pytest.mark.skipif(
    not (_has("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT") and (os.environ.get("AZURE_OPENAI_DEPLOYMENT") or os.environ.get("AZURE_OPENAI_MODEL"))),
    reason="AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, and AZURE_OPENAI_DEPLOYMENT (or AZURE_OPENAI_MODEL) are not set",
)
async def test_live_azure_openai_client_generate():
    pytest.importorskip("openai")
    model = os.environ.get("AZURE_OPENAI_DEPLOYMENT") or os.environ.get("AZURE_OPENAI_MODEL")
    client = AzureOpenAIClient(
        {
            "api_key": os.environ["AZURE_OPENAI_API_KEY"],
            "azure_endpoint": os.environ["AZURE_OPENAI_ENDPOINT"],
            "api_version": os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            "model": model,
            "deployment": model,
        }
    )
    response = await client.generate(LLMRequest(prompt="Reply with the single word pong.", max_tokens=16, temperature=0.0))
    assert response.model_name
    assert response.text or response.tool_calls
    assert "total_tokens" in response.raw_usage or "prompt_tokens" in response.raw_usage


@pytest.mark.asyncio
@pytest.mark.skipif(not _has("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY is not set")
async def test_live_anthropic_client_generate():
    pytest.importorskip("anthropic")
    client = AnthropicClient(
        {
            "api_key": os.environ["ANTHROPIC_API_KEY"],
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
        }
    )
    response = await client.generate(LLMRequest(prompt="Reply with the single word pong.", max_tokens=16, temperature=0.0))
    assert response.model_name
    assert response.text or response.tool_calls
    assert "total_tokens" in response.raw_usage or "prompt_tokens" in response.raw_usage


@pytest.mark.asyncio
async def test_live_governed_mcp_gateway_against_official_stdio_server():
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=[str(_SERVER)])
    gateway = GovernedMCPGateway(
        policy=_policy(),
        telemetry=TelemetryManager(persist_jsonl=False),
        hitl_manager=HITLManager(adapter=AutoApprove()),
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await gateway.call_tool("lookup", {"query": "Q4 invoices"}, session=session)
        text = str(result)
        if hasattr(result, "content"):
            text = " ".join(getattr(block, "text", str(block)) for block in result.content)
        assert "Q4 invoices" in text or "records matching" in text
        with pytest.raises(GovernanceViolation, match="allow-list"):
            await gateway.call_tool("shell", {"cmd": "ls"}, session=session)
