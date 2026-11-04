"""Public registry facade.

``from govagent import tool, registry`` is the 3.0.2 object: one singleton with
Harbor verification and dict results from ``validate_intent_schema``. Schema
checks are additive. ``govagent.registry.manager`` remains the Harbor
implementation and is not a second public singleton.
"""

from .manager import GlobalRegistry, tool
from .schemas import ExecutionSnapshot, FinancialTransactionIntent, ToolManifest

# Same singleton 3.0.2 constructed here.
registry = GlobalRegistry()

__all__ = [
    "registry",
    "tool",
    "GlobalRegistry",
    "ExecutionSnapshot",
    "ToolManifest",
    "FinancialTransactionIntent",
]
