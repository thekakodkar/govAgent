"""Optional OpenTelemetry GenAI semantic-convention spans.

Uses ``opentelemetry-api`` only. Spans are no-ops unless the process has
configured a TracerProvider (for example via the OpenTelemetry SDK).
"""

from __future__ import annotations

import os
from typing import Any

_TRACER_NAME = "govagent"


def otel_enabled() -> bool:
    flag = os.environ.get("OTEL_SDK_DISABLED", "").strip().lower()
    return flag not in {"1", "true", "yes"}


def _tracer() -> Any | None:
    if not otel_enabled():
        return None
    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover
        return None
    return trace.get_tracer(_TRACER_NAME)


def start_execute_span(
    *,
    agent_id: str,
    model_name: str | None = None,
    trace_id: str | None = None,
) -> Any:
    """Start a GenAI-convention span, or return a no-op context manager."""
    tracer = _tracer()
    if tracer is None:
        return _NullSpan()
    span = tracer.start_span("gen_ai.invoke_agent")
    span.set_attribute("gen_ai.operation.name", "invoke_agent")
    span.set_attribute("gen_ai.provider.name", "govagent")
    span.set_attribute("gen_ai.agent.name", agent_id)
    if model_name:
        span.set_attribute("gen_ai.request.model", model_name)
    if trace_id:
        span.set_attribute("govagent.trace_id", trace_id)
    return span


def end_execute_span(
    span: Any,
    *,
    status: str,
    tokens: int = 0,
    cost_usd: float = 0.0,
    model_name: str | None = None,
) -> None:
    if span is None or isinstance(span, _NullSpan):
        return
    try:
        span.set_attribute("govagent.status", status)
        span.set_attribute("gen_ai.usage.total_tokens", int(tokens))
        span.set_attribute("gen_ai.usage.cost.usd", float(cost_usd))
        if model_name:
            span.set_attribute("gen_ai.response.model", model_name)
        span.end()
    except Exception:  # noqa: BLE001 - telemetry must never break execute
        return


class _NullSpan:
    def set_attribute(self, *args: Any, **kwargs: Any) -> None:
        return None

    def end(self) -> None:
        return None
