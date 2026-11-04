# src/govagent/registry/manager.py
import functools
import logging
from typing import Dict, Callable, Any, List
from govagent.registry.schemas import FinancialTransactionIntent, ToolManifest
from govagent.registry.harbor_verifier import HarborVerifier
from govagent.guards.circuit_breaker import GovernanceViolation

logger = logging.getLogger("govagent.registry.manager")

def verify_tool_record(tools: Dict[str, Any], harbor: HarborVerifier, tool_name: str) -> Callable:
    """Harbor gate shared by the public registry facade and this singleton."""
    if tool_name not in tools:
        raise GovernanceViolation(f"REGISTRY EXCEPTION: Tool '{tool_name}' is not authorized.")

    tool_data = tools[tool_name]
    manifest = tool_data["manifest"]
    if manifest.oci_repository and manifest.artifact_digest:
        scan_report = harbor.verify_tool_artifact(
            repository=manifest.oci_repository,
            artifact_digest=manifest.artifact_digest,
        )
        if not scan_report["verified"]:
            raise GovernanceViolation(
                f"HARBOR REGISTRY BLOCK: Tool failed image validation. Details: {scan_report['details']}"
            )

    logger.info(f"✅ Supply Chain Approved: Tool '{tool_name}' cleared for execution.")
    return tool_data["func"]


class GlobalRegistry:
    """Harbor registry used by the public facade in ``govagent.registry``.

    ``from govagent.registry.manager import GlobalRegistry, tool`` remains supported.
    New callers should use ``from govagent import tool, registry``.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalRegistry, cls).__new__(cls)
            cls._instance.tools = {}
            cls._instance.harbor = HarborVerifier()
        return cls._instance

    def register_tool(self, func: Callable, manifest: ToolManifest, schema: Any = None, risk_level: str = None):
        """Legislates a function into the sovereign manifest."""
        self.tools[manifest.name] = {
            "func": func,
            "manifest": manifest,
            "schema": schema,
            "risk_level": risk_level if risk_level is not None else getattr(manifest, "risk_level", "low"),
            "cost_usd": getattr(manifest, "cost_usd", 0.0),
        }

    def verify_and_resolve_tool(self, tool_name: str) -> Callable:
        """STAGE 5: Intercepts tools to run out-of-band Harbor OCI container verification."""
        return verify_tool_record(self.tools, self.harbor, tool_name)

    def validate_against_policy(self, allowed_tools: List[str]) -> bool:
        """Reject tools that are registered but absent from a non-empty allow list."""
        for tool_name in self.tools.keys():
            if allowed_tools and tool_name not in allowed_tools:
                raise PermissionError(
                    f"🛑 UNAUTHORIZED TOOL DETECTED: '{tool_name}' violates policy boundary."
                )
        return True

    def validate_intent_schema(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Return a dict result. Invalid amounts and schemas raise."""
        if arguments is None:
            arguments = {}
        entry = self.tools.get(tool_name)
        schema_cls = None
        if entry and entry.get("schema"):
            schema_cls = entry["schema"]
        elif tool_name == "execute_financial_transaction":
            schema_cls = FinancialTransactionIntent

        if schema_cls is not None:
            schema_cls.model_validate(arguments)
        elif isinstance(arguments, dict) and "amount" in arguments:
            try:
                float(arguments["amount"])
            except (ValueError, TypeError):
                raise ValueError("Institutional Integrity Failure: 'amount' must be numeric.")

        if entry is None:
            return {"valid": False, "error": "Tool not legislated"}
        return {"valid": True, "status": "AUTHORIZED"}

def tool(name: str = None, description: str = None, risk_level: str = "low", oci_repository: str = None, artifact_digest: str = None, schema: Any = None):
    """Sovereign Decorator: Intercepts and registers institutional actions with OCI scopes."""
    def decorator(func):
        registry_instance = GlobalRegistry()
        tool_name = name or func.__name__
        manifest = ToolManifest(
            name=tool_name,
            description=description or func.__doc__ or "No description provided",
            risk_level=risk_level,
            oci_repository=oci_repository,
            artifact_digest=artifact_digest,
        )
        registry_instance.register_tool(func, manifest, schema=schema, risk_level=risk_level)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator