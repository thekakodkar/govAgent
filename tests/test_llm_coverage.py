from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from govagent.llm.base import LLMRequest, LLMResponse
from govagent.llm.ollama import OllamaClient
from govagent.llm.router import PolicyBasedRouter, RouterConfig, RoutingMode, RoutingRule


class ScriptedClient:
    def __init__(self, name: str):
        self.name = name

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text=f"from:{self.name}", model_name=self.name, raw_usage={"total_tokens": 4})


def test_router_rejects_missing_default_provider():
    with pytest.raises(ValueError, match="default provider"):
        PolicyBasedRouter(
            clients={"local": ScriptedClient("local")},
            config=RouterConfig(routing_mode=RoutingMode.LOCAL_ONLY, default_provider="missing"),
        )


def test_router_local_and_cloud_ignore_rules():
    local = ScriptedClient("local")
    cloud = ScriptedClient("cloud")
    rules = [RoutingRule(condition_key="contains_pii", expected_value=True, target_provider="cloud")]
    local_router = PolicyBasedRouter(
        clients={"local": local, "cloud": cloud},
        config=RouterConfig(routing_mode=RoutingMode.LOCAL_ONLY, default_provider="local", rules=rules),
    )
    cloud_router = PolicyBasedRouter(
        clients={"local": local, "cloud": cloud},
        config=RouterConfig(routing_mode=RoutingMode.CLOUD_ONLY, default_provider="cloud", rules=rules),
    )
    assert local_router.determine_target({"contains_pii": True}) == "local"
    assert cloud_router.determine_target({"contains_pii": True}) == "cloud"


def test_hybrid_router_matches_falls_back_and_defaults():
    router = PolicyBasedRouter(
        clients={"local": ScriptedClient("local"), "cloud": ScriptedClient("cloud")},
        config=RouterConfig(
            routing_mode=RoutingMode.HYBRID,
            default_provider="local",
            rules=[
                RoutingRule(condition_key="contains_pii", expected_value=True, target_provider="cloud"),
                RoutingRule(condition_key="tool_complexity", expected_value="high", target_provider="missing"),
            ],
        ),
    )
    assert router.determine_target({"contains_pii": True}) == "cloud"
    assert router.determine_target({"tool_complexity": "high"}) == "local"
    assert router.determine_target({}) == "local"


@pytest.mark.asyncio
async def test_route_and_generate_uses_selected_client():
    router = PolicyBasedRouter(
        clients={"local": ScriptedClient("local"), "cloud": ScriptedClient("cloud")},
        config=RouterConfig(
            routing_mode=RoutingMode.HYBRID,
            default_provider="local",
            rules=[RoutingRule(condition_key="contains_pii", expected_value=True, target_provider="cloud")],
        ),
    )
    response = await router.route_and_generate(LLMRequest(prompt="hi"), {"contains_pii": True})
    assert response.text == "from:cloud"
    assert response.selected_model == "cloud"


@pytest.mark.asyncio
async def test_ollama_generate_maps_usage_and_system_prompt():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"response": "hello-local", "prompt_eval_count": 11, "eval_count": 7},
        )

    transport = httpx.MockTransport(handler)

    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    client = OllamaClient({"base_url": "http://ollama.test:11434", "model": "llama3"})
    with patch("govagent.llm.ollama.httpx.AsyncClient", side_effect=factory):
        result = await client.generate(
            LLMRequest(prompt="summarise this", system_instruction="be brief", temperature=0.1)
        )
    assert result.text == "hello-local"
    assert result.model_name == "llama3"
    assert result.raw_usage["prompt_tokens"] == 11
    assert result.raw_usage["completion_tokens"] == 7
    assert captured["body"]["system"] == "be brief"
    assert captured["body"]["stream"] is False
    assert "http://ollama.test:11434/api/generate" in captured["url"]


@pytest.mark.asyncio
async def test_ollama_generate_raises_on_error_status():
    transport = httpx.MockTransport(lambda request: httpx.Response(503, text="down"))

    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    client = OllamaClient({"base_url": "http://ollama.test", "model": "llama3"})
    with (
        patch("govagent.llm.ollama.httpx.AsyncClient", side_effect=factory),
        pytest.raises(RuntimeError, match="Ollama local inference failed"),
    ):
        await client.generate(LLMRequest(prompt="hi"))
