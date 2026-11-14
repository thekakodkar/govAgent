"""Optional Anthropic client (extra: anthropic)."""

from __future__ import annotations

from typing import Any

from govagent.llm.base import BaseLLMClient, LLMRequest, LLMResponse
from govagent.pricing import PricingEngine


class AnthropicClient(BaseLLMClient):
    """Messages API client with tool-calling and usage mapping."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.pricing = PricingEngine()

    def _sdk(self) -> Any:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Install govagent[anthropic] to use AnthropicClient.") from exc
        return AsyncAnthropic(api_key=self.config.get("api_key"))

    async def generate(self, request: LLMRequest) -> LLMResponse:
        model = self.config.get("model", "claude-3-5-sonnet-latest")
        client = self.config.get("client") or self._sdk()
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens or 1024,
            "temperature": request.temperature,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system_instruction:
            kwargs["system"] = request.system_instruction
        if request.tools:
            kwargs["tools"] = request.tools
        payload = await client.messages.create(**kwargs)
        text = _anthropic_text(payload)
        tool_calls = _anthropic_tools(payload)
        usage = getattr(payload, "usage", None)
        if isinstance(payload, dict):
            usage = payload.get("usage") or {}
            prompt_tokens = int(usage.get("input_tokens") or 0)
            completion_tokens = int(usage.get("output_tokens") or 0)
        else:
            prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        total = prompt_tokens + completion_tokens
        cost = self.pricing.calculate_cost(model, total) if total else 0.0
        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            model_name=model,
            raw_usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total,
                "estimated_cost_usd": cost,
            },
        )


def _anthropic_text(payload: Any) -> str:
    blocks = payload.get("content") if isinstance(payload, dict) else getattr(payload, "content", None)
    if not blocks:
        return ""
    parts = []
    for block in blocks:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text") or "")
        else:
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", "") or "")
    return "".join(parts)


def _anthropic_tools(payload: Any) -> list[dict[str, Any]]:
    blocks = payload.get("content") if isinstance(payload, dict) else getattr(payload, "content", None)
    calls = []
    for block in blocks or []:
        typ = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if typ != "tool_use":
            continue
        if isinstance(block, dict):
            name = block.get("name")
            args = block.get("input") or {}
        else:
            name = getattr(block, "name", None)
            args = getattr(block, "input", {}) or {}
        if name:
            calls.append({"name": name, "args": args})
    return calls
