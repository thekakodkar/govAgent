import yaml
from typing import Dict, Any, List, Optional
from govagent.registry import registry

class Policy:
    """
    The Legislative Engine v1.0.0: Translates YAML-based SOPs into 
    parameterized governance constraints for cascading guards.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.metadata = config.get("metadata", {})
        self.agent_name = self.metadata.get("agent_name", "UnknownAgent")
        
        # Mapping YAML tools for O(1) lookup
        self.tool_rules = {t["name"]: t for t in config.get("tools", [])}

        # Extract Core Infrastructure & Routing Configurations dynamically
        self.infra_settings = config.get("infrastructure", {})
        self.routing_mode = self.infra_settings.get("routing_mode", "LOCAL_ONLY")  # Defensively default to secure local
        self.default_provider = self.infra_settings.get("default_provider", "local_ollama")
        self.routing_rules = self.infra_settings.get("rules", [])

        # Global Fiscal & Operational Ceilings.
        # A top-level global_limits key overrides the same key nested under
        # fiscal_governance. Keys that were not set at the top level come from
        # that nested block, so policies/*.yaml enforce their ceilings.
        self.global_limits = _project_global_limits(config)
        alignment = config.get("alignment")
        self.alignment = alignment if isinstance(alignment, dict) else {}
        
        # Judiciary Handshake Settings
        self.judiciary_settings = config.get("judiciary", {
            "channel": "slack",
            "confidence_threshold": 0.9,
            "timeout_seconds": 300
        })

        # Legacy Support & Common Attributes
        self.restricted_domains = config.get("governance", {}).get("restricted_domains", [])
        self.confidence_threshold = self.judiciary_settings.get("confidence_threshold", 0.9)

        # Automated Synchronization Audit
        self.validate_registry()

    @property
    def allowed_tools(self) -> List[str]:
        return list(self.tool_rules.keys())

    def get_tool_config(self, tool_name: str) -> Dict[str, Any]:
        """Returns the specific policy constraints for a given tool."""
        return self.tool_rules.get(tool_name, {})

    @classmethod
    def from_yaml(cls, path: str):
        # Enforce explicit UTF-8 decoding boundaries to secure Windows cross-compatibility
        with open(path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return cls(config)

    def validate_registry(self):
        """Ensures Python code complies with the Executive Policy."""
        print(f"📋 Compliance Audit: Aligning code with '{self.agent_name}' policy...")
        registry.validate_against_policy(self.allowed_tools)

        risk_hierarchy = {"low": 1, "medium": 2, "high": 3}
        for tool_name, metadata in registry.tools.items():
            if tool_name not in self.tool_rules: continue
            
            yaml_risk = self.tool_rules[tool_name].get("risk_level", "low")
            code_risk = metadata.get("risk_level", "low")

            if risk_hierarchy.get(code_risk, 0) < risk_hierarchy.get(yaml_risk, 0):
                raise PermissionError(
                    f"🛑 GOVERNANCE VIOLATION: Risk downgrade detected for '{tool_name}'."
                )
        print("✅ Governance Alignment: Registry and Policy are synchronized.")

    def is_high_risk(self, tool_name: str) -> bool:
        """Determines if an action requires Judiciary (Human) intervention."""
        rule = self.get_tool_config(tool_name)
        if rule.get("require_human_approval") or rule.get("risk_level") == "high":
            return True
        return False


def _project_global_limits(config: Dict[str, Any]) -> Dict[str, Any]:
    defaults = {
        "daily_budget_usd": 10.0,
        "max_per_transaction": 2000.0,
        "max_tokens_per_run": 4000,
    }
    top = config.get("global_limits")
    explicit = top if isinstance(top, dict) else {}
    limits = dict(explicit) if isinstance(top, dict) else dict(defaults)
    fiscal = config.get("fiscal_governance")
    nested = fiscal.get("global_limits") if isinstance(fiscal, dict) else None
    if not isinstance(nested, dict):
        return limits
    for key, value in nested.items():
        target = "recursive_tco_ceiling" if key == "recursive_tco_limit" else key
        if key in explicit or target in explicit:
            continue
        limits[target] = value
    return limits