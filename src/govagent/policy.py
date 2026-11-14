from __future__ import annotations

import logging
from typing import Any

import yaml

from govagent.registry import registry

logger = logging.getLogger("govagent.policy")

_DEFAULT_JUDICIARY = {
    "channel": "slack",
    "confidence_threshold": 0.9,
    "timeout_seconds": 300,
}


class Policy:
    """
    The Legislative Engine: Translates YAML-based SOPs into
    parameterized governance constraints for cascading guards.

    Tool allow-lists are projected from ``registry_alignment`` and from a
    top-level ``tools:`` list. Entries in ``tools:`` win for the same name.
    Judiciary settings come from top-level ``judiciary`` or, if that key is
    absent, from ``oversight.judiciary``.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.metadata = config.get("metadata", {})
        self.agent_name = self.metadata.get("agent_name", "UnknownAgent")

        self.tool_rules = _project_tool_rules(config)
        self.high_risk_tools = _project_high_risk_tools(config, self.tool_rules)

        self.infra_settings = config.get("infrastructure", {})
        self.routing_mode = self.infra_settings.get("routing_mode", "LOCAL_ONLY")
        self.default_provider = self.infra_settings.get("default_provider", "local_ollama")
        self.routing_rules = self.infra_settings.get("rules", [])

        self.global_limits = _project_global_limits(config)
        alignment = config.get("alignment")
        self.alignment = alignment if isinstance(alignment, dict) else {}

        oversight = config.get("oversight")
        self.oversight: dict[str, Any] = oversight if isinstance(oversight, dict) else {}
        self.judiciary_settings = _project_judiciary(config, self.oversight)

        self.restricted_domains = config.get("governance", {}).get("restricted_domains", [])
        self.confidence_threshold = self.judiciary_settings.get("confidence_threshold", 0.9)

        self.validate_registry()

    @property
    def allowed_tools(self) -> list[str]:
        return list(self.tool_rules.keys())

    def get_tool_config(self, tool_name: str) -> dict[str, Any]:
        """Returns the specific policy constraints for a given tool."""
        return self.tool_rules.get(tool_name, {})

    @classmethod
    def from_yaml(cls, path: str) -> Policy:
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls(config)

    def validate_registry(self) -> None:
        """Risk-downgrade audit against already-registered tools.

        Allow-list membership is enforced at execute time so a process-wide
        registry can hold tools used by other policies. ``registry.validate_against_policy``
        remains available for callers that want the stricter load-time check.
        """
        print(f"📋 Compliance Audit: Aligning code with '{self.agent_name}' policy...")
        risk_hierarchy = {"low": 1, "medium": 2, "high": 3}
        for tool_name, metadata in registry.tools.items():
            if tool_name not in self.tool_rules:
                continue

            yaml_risk = self.tool_rules[tool_name].get("risk_level", "low")
            code_risk = metadata.get("risk_level", "low")

            if risk_hierarchy.get(str(code_risk).lower(), 0) < risk_hierarchy.get(str(yaml_risk).lower(), 0):
                raise PermissionError(
                    f"🛑 GOVERNANCE VIOLATION: Risk downgrade detected for '{tool_name}'."
                )
        print("✅ Governance Alignment: Registry and Policy are synchronized.")

    def is_high_risk(self, tool_name: str) -> bool:
        """Determines if an action requires Judiciary (Human) intervention."""
        if tool_name in self.high_risk_tools:
            return True
        rule = self.get_tool_config(tool_name)
        return bool(rule.get("require_human_approval") or str(rule.get("risk_level", "")).lower() == "high")


def _project_tool_rules(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    alignment = config.get("registry_alignment")
    if isinstance(alignment, dict):
        for name in alignment.get("allowed_tools") or []:
            if name:
                rules[str(name)] = {"name": str(name), "risk_level": "low"}
        for name in alignment.get("high_risk_tools") or []:
            if not name:
                continue
            key = str(name)
            entry = dict(rules.get(key, {"name": key}))
            entry["risk_level"] = "high"
            entry["require_human_approval"] = True
            rules[key] = entry

    for tool in config.get("tools") or []:
        if isinstance(tool, dict) and tool.get("name"):
            rules[str(tool["name"])] = dict(tool)
        elif isinstance(tool, str) and tool:
            rules[tool] = {"name": tool}
    return rules


def _project_high_risk_tools(config: dict[str, Any], tool_rules: dict[str, dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    alignment = config.get("registry_alignment")
    if isinstance(alignment, dict):
        for name in alignment.get("high_risk_tools") or []:
            if name:
                names.add(str(name))
    for name, rule in tool_rules.items():
        if rule.get("require_human_approval") or str(rule.get("risk_level", "")).lower() == "high":
            names.add(name)
    # A top-level tools: entry that explicitly lowers risk wins for that name.
    for tool in config.get("tools") or []:
        if isinstance(tool, dict) and tool.get("name"):
            lowered = (
                not tool.get("require_human_approval")
                and str(tool.get("risk_level", "low")).lower() != "high"
                and "risk_level" in tool
            )
            if lowered and not tool.get("require_human_approval"):
                names.discard(str(tool["name"]))
    return names


def _project_judiciary(config: dict[str, Any], oversight: dict[str, Any]) -> dict[str, Any]:
    settings = dict(_DEFAULT_JUDICIARY)
    nested = oversight.get("judiciary") if isinstance(oversight.get("judiciary"), dict) else {}
    if nested:
        settings.update(nested)
    top = config.get("judiciary")
    if isinstance(top, dict):
        settings.update(top)
    return settings


def _project_global_limits(config: dict[str, Any]) -> dict[str, Any]:
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
