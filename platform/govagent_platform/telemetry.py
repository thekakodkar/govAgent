"""Request spans for the platform API.

The library is not instrumented. Span attributes are identifiers only.
Task text is never placed on a span.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from opentelemetry import context, trace


_provider = None


def configure_provider(provider) -> None:
    """Tests install an in-memory provider. Production leaves this unset."""

    global _provider
    _provider = provider


def tracer():
    if _provider is not None:
        return _provider.get_tracer("govagent_platform")
    return trace.get_tracer("govagent_platform")


@contextmanager
def platform_span(name: str) -> Iterator:
    """Root span. A non-recording parent must not drop the request span."""

    active = tracer()
    parent = trace.set_span_in_context(trace.INVALID_SPAN)
    span = active.start_span(name, context=parent)
    token = context.attach(trace.set_span_in_context(span))
    try:
        yield span
    finally:
        context.detach(token)
        span.end()


def annotate(span, *, tenant_id: str | None, trace_id: str | None, status: str | None) -> None:
    if not getattr(span, "is_recording", lambda: False)():
        return
    span.set_attribute("tenant_id", tenant_id or "")
    span.set_attribute("trace_id", trace_id or "")
    span.set_attribute("govagent.status", status or "")
