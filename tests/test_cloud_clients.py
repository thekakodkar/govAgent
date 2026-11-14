from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from govagent.llm.anthropic_client import AnthropicClient
from govagent.llm.base import LLMRequest
from govagent.llm.openai_client import AzureOpenAIClient, OpenAIClient


def _openai_payload(*, content="hello", tool=True):
    tool_calls = []
    if tool:
        tool_calls = [
            SimpleNamespace(
                function=SimpleNamespace(name="lookup", arguments='{"query": "alpha"}'),
            ),
            {"function": {"name": "broken", "arguments": "not-json"}},
        ]
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


@pytest.mark.asyncio
async def test_openai_client_maps_tools_and_cost():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_openai_payload())
    wrapper = OpenAIClient({"model": "gpt-4o", "client": client})
    response = await wrapper.generate(
        LLMRequest(
            prompt="hi",
            system_instruction="sys",
            tools=[{"type": "function", "function": {"name": "lookup"}}],
            max_tokens=32,
        )
    )
    assert response.text == "hello"
    assert response.model_name == "gpt-4o"
    assert response.tool_calls[0] == {"name": "lookup", "args": {"query": "alpha"}}
    assert response.tool_calls[1]["args"] == {"raw": "not-json"}
    assert response.raw_usage["prompt_tokens"] == 10
    assert response.raw_usage["total_tokens"] == 15
    assert response.raw_usage["estimated_cost_usd"] > 0
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["messages"][0] == {"role": "system", "content": "sys"}
    assert kwargs["tools"][0]["function"]["name"] == "lookup"


@pytest.mark.asyncio
async def test_azure_openai_client_uses_injected_client():
    payload = {
        "choices": [{"message": {"content": "azure-hi", "tool_calls": []}}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3},
    }
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=payload)
    wrapper = AzureOpenAIClient({"model": "gpt-4o", "client": client, "azure_endpoint": "https://example.openai.azure.com"})
    response = await wrapper.generate(LLMRequest(prompt="hi", tools=[{"type": "function"}]))
    assert response.text == "azure-hi"
    assert response.raw_usage["total_tokens"] == 5


@pytest.mark.asyncio
async def test_anthropic_client_maps_text_tools_and_usage():
    payload = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="claude"),
            SimpleNamespace(type="tool_use", name="lookup", input={"query": "beta"}),
        ],
        usage=SimpleNamespace(input_tokens=8, output_tokens=4),
    )
    sdk = MagicMock()
    sdk.messages.create = AsyncMock(return_value=payload)
    wrapper = AnthropicClient({"model": "claude-3-5-sonnet-latest", "client": sdk})
    response = await wrapper.generate(
        LLMRequest(prompt="hi", system_instruction="sys", tools=[{"name": "lookup", "input_schema": {}}])
    )
    assert response.text == "claude"
    assert response.tool_calls == [{"name": "lookup", "args": {"query": "beta"}}]
    assert response.raw_usage["prompt_tokens"] == 8
    assert response.raw_usage["total_tokens"] == 12
    assert response.raw_usage["estimated_cost_usd"] >= 0
    kwargs = sdk.messages.create.await_args.kwargs
    assert kwargs["system"] == "sys"


@pytest.mark.asyncio
async def test_anthropic_dict_payload_without_tools():
    payload = {"content": [{"type": "text", "text": "only"}], "usage": {"input_tokens": 1, "output_tokens": 1}}
    sdk = MagicMock()
    sdk.messages.create = AsyncMock(return_value=payload)
    response = await AnthropicClient({"client": sdk}).generate(LLMRequest(prompt="hi"))
    assert response.text == "only"
    assert response.tool_calls == []
