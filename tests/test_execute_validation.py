"""Pin execute() against both the 3.0.2 dict contract and invalid amounts."""

import pytest
from pydantic import ValidationError

from govagent.agent import ExecutiveAgent
from govagent.llm.base import LLMResponse
from govagent.registry import registry, tool


class _ScriptedRouter:
    def __init__(self, amount):
        self.amount = amount

    async def route_and_generate(self, request, context):
        return LLMResponse(
            text="use the financial tool",
            tool_calls=[{"name": "execute_financial_transaction", "args": {"amount": self.amount}}],
            raw_usage={"total_tokens": 4},
            model_name="scripted",
        )


@pytest.fixture
def legislated_payment():
    @tool(name="execute_financial_transaction", risk_level="low")
    def _payment(amount: float):
        return amount

    yield
    registry.tools.pop("execute_financial_transaction", None)


@pytest.mark.asyncio
async def test_invalid_amount_is_blocked_not_error(sovereign_policy):
    agent = ExecutiveAgent(
        persona="Director",
        policy=sovereign_policy,
        router=_ScriptedRouter("invalid_amt"),
    )
    result = await agent.execute("Pay an invoice")
    assert result.status == "blocked"
    assert "Schema Violation" in str(result.output)
    assert result.status != "error"


@pytest.mark.asyncio
async def test_legislated_amount_does_not_fail_on_validation_shape(sovereign_policy, legislated_payment):
    class Router:
        async def route_and_generate(self, request, context):
            return LLMResponse(
                text="use the financial tool",
                tool_calls=[{"name": "execute_financial_transaction", "args": {"amount": 10}}],
                raw_usage={"total_tokens": 4},
                model_name="scripted",
            )

    agent = ExecutiveAgent(persona="Director", policy=sovereign_policy, router=Router())
    result = await agent.execute("Pay an invoice")
    assert result.status != "error"
    assert result.status == "success"


def test_unknown_tool_returns_3_0_2_dict():
    result = registry.validate_intent_schema("not_a_published_tool", {})
    assert isinstance(result, dict)
    assert result["valid"] is False
    assert "error" in result


def test_invalid_financial_amount_still_raises():
    with pytest.raises((ValidationError, ValueError)):
        registry.validate_intent_schema(
            "execute_financial_transaction",
            {"amount": "invalid_amt"},
        )
