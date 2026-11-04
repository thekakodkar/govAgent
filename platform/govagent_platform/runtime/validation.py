"""Validate a tool call against one request's tenant map.

``GlobalRegistry`` is a process singleton. This module never writes
``registry.tools``. It calls the library method with a private object that
only has the tools loaded for this request.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Callable

from govagent.registry.manager import GlobalRegistry
from govagent.registry.schemas import FinancialTransactionIntent, ToolManifest

overlap_hook: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar(
    "govagent_platform_overlap_hook",
    default=None,
)


class _RequestTools:
    def __init__(self, tools: dict[str, Any]):
        self.tools = tools


def registry_entry(row: Any) -> dict[str, Any]:
    schema = None
    param_schema = row.param_schema if isinstance(getattr(row, "param_schema", None), dict) else {}
    if param_schema.get("model") == "FinancialTransactionIntent":
        schema = FinancialTransactionIntent
    risk = getattr(row, "risk_level", None) or "low"
    manifest = ToolManifest(
        name=row.name,
        description=getattr(row, "description", None) or row.name,
        risk_level=risk,
        oci_repository=getattr(row, "oci_repository", None),
        artifact_digest=getattr(row, "artifact_digest", None),
    )
    return {
        "func": _noop,
        "manifest": manifest,
        "schema": schema,
        "risk_level": risk,
        "cost_usd": 0.0,
    }


def validate_tenant_intent(tool_map: dict[str, Any], tool_name: str | None, arguments: dict | None):
    """Library schema check for this request's tools. The singleton is not updated."""

    hook = overlap_hook.get()
    if hook is not None:
        hook(tool_map)
    local = _RequestTools({name: registry_entry(row) for name, row in tool_map.items()})
    return GlobalRegistry.validate_intent_schema(local, tool_name, arguments or {})


def _noop(*args, **kwargs):
    return None
