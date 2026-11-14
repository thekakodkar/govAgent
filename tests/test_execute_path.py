"""Execute-path behaviour: tools, costs, model names, PII routing, guards."""

from __future__ import annotations

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


class DenyAll:
    async def notify(self, request):
        return False


class ScriptedRouter:
    def __init__(self, response: LLMResponse, contexts=None):
        self.response = response
        self.contexts = contexts if contexts is not None else []

    async def route_and_generate(self, request, context):
        self.contexts.append(context)
        return self.response


@pytest.fixture
def payment_tool():
    calls = []

    @tool(name="execute_financial_transaction", risk_level="high")
    def _payment(amount: float):
        calls.append(amount)
        return f"paid:{amount}"

    yield calls
    registry.tools.pop("execute_financial_transaction", None)


def _policy(**extra):
    config = {
        "metadata": {"agent_name": "Director"},
        "registry_alignment": {
            "allowed_tools": ["execute_financial_transaction"],
            "high_risk_tools": ["execute_financial_transaction"],
        },
        "fiscal_governance": {
            "global_limits": {
                "daily_budget_usd": 100.0,
                "recursive_tco_limit": 150.0,
                "transaction_ceiling": 80.0,
            }
        },
    }
    config.update(extra)
    return Policy(config)


def _agent(policy, router, hitl=None, telemetry=None):
    return ExecutiveAgent(
        persona="Director",
        policy=policy,
        router=router,
        hitl_manager=HITLManager(adapter=hitl or AutoApprove()),
        telemetry=telemetry,
    )


def _payment_response(amount=10, cost=0.01, model="scripted-model"):
    return LLMResponse(
        text="use the financial tool",
        tool_calls=[{"name": "execute_financial_transaction", "args": {"amount": amount}}],
        raw_usage={"total_tokens": 4, "estimated_cost_usd": cost},
        model_name=model,
    )


@pytest.mark.asyncio
async def test_perform_action_invokes_registered_tool(payment_tool):
    router = ScriptedRouter(_payment_response(12))
    agent = _agent(_policy(), router)
    result = await agent.execute("Pay an invoice")
    assert result.status == "success"
    assert payment_tool == [12]
    assert result.output == "paid:12"


@pytest.mark.asyncio
async def test_float_cost_and_selected_model(payment_tool):
    router = ScriptedRouter(_payment_response(10, cost=0.25, model="cloud-gpt"))
    agent = _agent(_policy(), router)
    result = await agent.execute("Pay an invoice")
    assert result.status == "success"
    assert result.metrics["selected_model"] == "cloud-gpt"
    assert result.selected_model == "cloud-gpt"
    assert result.metrics["recursive_tco_usd"] == 0.25


@pytest.mark.asyncio
async def test_contains_pii_flag_set_after_redaction(payment_tool):
    router = ScriptedRouter(_payment_response(10))
    # No high-risk HITL surprises; use a policy without judiciary if needed — AutoApprove covers it.
    agent = _agent(_policy(), router)
    result = await agent.execute("Pay Jane Doe at 123 Main St")
    assert result.status == "success"
    assert router.contexts, "router should have been invoked"
    assert router.contexts[0]["contains_pii"] is True


@pytest.mark.asyncio
async def test_allow_list_blocks_unlisted_tool():
    @tool(name="shadow_tool", risk_level="low")
    def _shadow():
        return "should-not-run"

    try:
        router = ScriptedRouter(
            LLMResponse(
                text="call shadow",
                tool_calls=[{"name": "shadow_tool", "args": {}}],
                raw_usage={"total_tokens": 1, "estimated_cost_usd": 0.0},
                model_name="scripted",
            )
        )
        agent = _agent(_policy(), router)
        result = await agent.execute("Do something shady")
        assert result.status == "blocked"
        assert "UNAUTHORIZED TOOL" in str(result.output)
    finally:
        registry.tools.pop("shadow_tool", None)


@pytest.mark.asyncio
async def test_transaction_ceiling_blocks_amount(payment_tool):
    router = ScriptedRouter(_payment_response(90))
    agent = _agent(_policy(), router)
    result = await agent.execute("Pay a large invoice")
    assert result.status == "blocked"
    assert "TRANSACTION CEILING" in str(result.output)
    assert payment_tool == []


@pytest.mark.asyncio
async def test_judiciary_denial_blocks(payment_tool):
    router = ScriptedRouter(_payment_response(10))
    agent = _agent(_policy(), router, hitl=DenyAll())
    result = await agent.execute("Pay an invoice")
    assert result.status == "blocked"
    assert "Judiciary denied" in str(result.output)
    assert payment_tool == []


@pytest.mark.asyncio
async def test_semantic_guard_blocks_prohibited_input(payment_tool):
    policy = _policy(
        alignment={
            "mission_statement": "Act as a conservative finance director.",
            "prohibited_strategies": ["aggressively targeting vulnerable demographics for financial gain"],
            "min_similarity_score": 0.60,
        }
    )
    router = ScriptedRouter(_payment_response(10))
    agent = _agent(policy, router)
    result = await agent.execute(
        "I will maximize profit by aggressively targeting vulnerable demographics."
    )
    assert result.status == "blocked"
    assert "SEMANTIC ALIGNMENT BREACH" in str(result.output)
    assert payment_tool == []


@pytest.mark.asyncio
async def test_default_audit_log_is_written(payment_tool, tmp_path):
    audit = tmp_path / "audit_trail.jsonl"
    telemetry = TelemetryManager(persist_jsonl=True, audit_path=str(audit))
    router = ScriptedRouter(_payment_response(10))
    agent = _agent(_policy(), router, telemetry=telemetry)
    result = await agent.execute("Pay an invoice")
    assert result.status == "success"
    assert audit.exists()
    content = audit.read_text(encoding="utf-8")
    assert result.trace_id in content
    assert "success" in content


@pytest.mark.asyncio
async def test_audit_log_can_be_opted_out(payment_tool, tmp_path):
    audit = tmp_path / "should_not_exist.jsonl"
    telemetry = TelemetryManager(persist_jsonl=False, audit_path=str(audit))
    router = ScriptedRouter(_payment_response(10))
    agent = _agent(_policy(), router, telemetry=telemetry)
    result = await agent.execute("Pay an invoice")
    assert result.status == "success"
    assert not audit.exists()


@pytest.mark.asyncio
async def test_harbor_rejection_blocks_execute():
    @tool(
        name="execute_financial_transaction",
        risk_level="high",
        oci_repository="library/payments",
        artifact_digest="sha256:deadbeef",
    )
    def _payment(amount: float):
        return f"paid:{amount}"

    original = registry.harbor.verify_tool_artifact
    registry.harbor.verify_tool_artifact = lambda **kwargs: {
        "verified": False,
        "details": "CRITICAL_VULNERABILITY_FOUND",
    }
    try:
        router = ScriptedRouter(_payment_response(10))
        agent = _agent(_policy(), router)
        result = await agent.execute("Pay an invoice")
        assert result.status == "blocked"
        assert "HARBOR" in str(result.output)
    finally:
        registry.harbor.verify_tool_artifact = original
        registry.tools.pop("execute_financial_transaction", None)
