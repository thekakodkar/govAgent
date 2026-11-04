"""Router construction. The scripted client is the default so evaluate does not need a network model."""

from __future__ import annotations

import json
import os

from govagent.llm.base import BaseLLMClient, LLMRequest, LLMResponse
from govagent.llm.router import PolicyBasedRouter, RouterConfig, RoutingMode

_MARKER = "[[govagent-script]]"
_END = "[[/govagent-script]]"


class ScriptedLLMClient(BaseLLMClient):
    """Returns one scripted tool call, then a completion, so the loop stays short."""

    def __init__(self, config: dict | None = None):
        super().__init__(config or {})
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        payload: dict = {}
        if _MARKER in request.prompt and _END in request.prompt:
            raw = request.prompt.split(_MARKER, 1)[1].split(_END, 1)[0]
            payload = json.loads(raw)
        if self.calls == 1 and payload.get("tool"):
            return LLMResponse(
                text=str(payload.get("thought") or "proceed"),
                tool_calls=[{"name": payload["tool"], "args": payload.get("args") or {}}],
                raw_usage={"total_tokens": int(payload.get("tokens") or 10)},
                model_name="scripted",
            )
        return LLMResponse(
            text="complete",
            tool_calls=[],
            raw_usage={"total_tokens": 1},
            model_name="scripted",
        )


def build_router(policy) -> PolicyBasedRouter:
    provider = os.environ.get("PLATFORM_LLM_PROVIDER", "scripted").strip() or "scripted"
    if provider == "ollama":
        from govagent.llm.ollama import OllamaClient

        name = getattr(policy, "default_provider", None) or "local_ollama"
        client = OllamaClient(
            {
                "base_url": os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
                "model": os.environ.get("OLLAMA_MODEL", "llama3"),
            }
        )
    else:
        name = "scripted"
        client = ScriptedLLMClient({})
    raw_mode = getattr(policy, "routing_mode", "LOCAL_ONLY")
    try:
        routing_mode = RoutingMode(raw_mode)
    except ValueError:
        routing_mode = RoutingMode.LOCAL_ONLY
    return PolicyBasedRouter(
        clients={name: client},
        config=RouterConfig(routing_mode=routing_mode, default_provider=name),
    )
