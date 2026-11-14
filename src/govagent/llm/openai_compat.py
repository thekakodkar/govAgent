"""Shared usage/tool-call mapping for OpenAI-compatible chat completions."""

from __future__ import annotations

from typing import Any

from govagent.llm.base import LLMResponse
from govagent.pricing import PricingEngine


def usage_and_calls(payload: Any, model_name: str, engine: PricingEngine | None = None) -> LLMResponse:
    engine = engine or PricingEngine()
    message = _message(payload)
    text = _text(message)
    tool_calls = _tool_calls(message)
    prompt_tokens, completion_tokens = _tokens(payload)
    total = prompt_tokens + completion_tokens
    cost = engine.calculate_cost(model_name, total) if total else 0.0
    return LLMResponse(
        text=text,
        tool_calls=tool_calls,
        model_name=model_name,
        raw_usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total,
            "estimated_cost_usd": cost,
        },
    )


def _message(payload: Any) -> Any:
    if isinstance(payload, dict):
        choices = payload.get("choices") or []
        if choices:
            return choices[0].get("message") or {}
        return payload.get("message") or {}
    choices = getattr(payload, "choices", None) or []
    if choices:
        return getattr(choices[0], "message", None)
    return None


def _text(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(getattr(message, "content", None) or "")


def _tool_calls(message: Any) -> list[dict[str, Any]]:
    raw: list[Any] = []
    if isinstance(message, dict):
        raw = message.get("tool_calls") or []
    elif message is not None:
        raw = getattr(message, "tool_calls", None) or []
    parsed: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            function = item.get("function") or {}
            name = function.get("name") or item.get("name")
            arguments = function.get("arguments") or item.get("arguments") or {}
        else:
            function = getattr(item, "function", None)
            name = getattr(function, "name", None) if function is not None else getattr(item, "name", None)
            arguments = getattr(function, "arguments", {}) if function is not None else {}
        if isinstance(arguments, str):
            import json

            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"raw": arguments}
        if name:
            parsed.append({"name": name, "args": arguments or {}})
    return parsed


def _tokens(payload: Any) -> tuple[int, int]:
    usage = payload.get("usage") if isinstance(payload, dict) else getattr(payload, "usage", None)
    if usage is None:
        return 0, 0
    if isinstance(usage, dict):
        return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    return int(getattr(usage, "prompt_tokens", 0) or 0), int(getattr(usage, "completion_tokens", 0) or 0)
