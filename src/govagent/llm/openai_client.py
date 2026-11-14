"""Optional OpenAI and Azure OpenAI clients (extra: openai)."""

from __future__ import annotations

from typing import Any

from govagent.llm.base import BaseLLMClient, LLMRequest, LLMResponse
from govagent.llm.openai_compat import usage_and_calls
from govagent.pricing import PricingEngine


class OpenAIClient(BaseLLMClient):
    """Chat Completions client with tool-calling and usage mapping."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.pricing = PricingEngine()

    def _sdk(self) -> Any:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Install govagent[openai] to use OpenAIClient.") from exc
        return AsyncOpenAI(
            api_key=self.config.get("api_key"),
            base_url=self.config.get("base_url"),
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        model = self.config.get("model", "gpt-4o")
        client = self.config.get("client") or self._sdk()
        messages: list[dict[str, Any]] = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})
        messages.append({"role": "user", "content": request.prompt})
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.tools:
            kwargs["tools"] = request.tools
        payload = await client.chat.completions.create(**kwargs)
        return usage_and_calls(payload, model, self.pricing)


class AzureOpenAIClient(BaseLLMClient):
    """Azure OpenAI Chat Completions client (same extra as OpenAI)."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.pricing = PricingEngine()

    def _sdk(self) -> Any:
        try:
            from openai import AsyncAzureOpenAI
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Install govagent[openai] to use AzureOpenAIClient.") from exc
        endpoint = self.config.get("azure_endpoint") or self.config.get("base_url") or ""
        return AsyncAzureOpenAI(
            api_key=self.config.get("api_key"),
            azure_endpoint=str(endpoint),
            api_version=self.config.get("api_version", "2024-10-21"),
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        model = self.config.get("model") or self.config.get("deployment", "gpt-4o")
        client = self.config.get("client") or self._sdk()
        messages: list[dict[str, Any]] = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})
        messages.append({"role": "user", "content": request.prompt})
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.tools:
            kwargs["tools"] = request.tools
        payload = await client.chat.completions.create(**kwargs)
        return usage_and_calls(payload, model, self.pricing)
