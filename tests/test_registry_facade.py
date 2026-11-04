"""Public registry keeps the 3.0.2 Harbor path and dict results."""

import importlib

import govagent
import pytest
from govagent.guards import GovernanceViolation
from govagent.registry import registry, tool
from govagent.registry.schemas import FinancialTransactionIntent


def test_public_imports_are_the_facade_singleton():
    registry_module = importlib.import_module("govagent.registry")
    assert govagent.registry is registry
    assert registry is registry_module.registry
    assert id(govagent.registry) == id(registry_module.registry)
    assert hasattr(registry, "verify_and_resolve_tool")


def test_harbor_path_is_on_the_public_registry():
    @tool(
        name="facade_malicious_tool",
        oci_repository="bizzteq/malicious-db-utils",
        artifact_digest="sha256:corrupted",
    )
    def _payload():
        return "nope"

    try:
        with pytest.raises(GovernanceViolation) as excinfo:
            registry.verify_and_resolve_tool("facade_malicious_tool")
        assert "HARBOR REGISTRY BLOCK" in str(excinfo.value)
    finally:
        registry.tools.pop("facade_malicious_tool", None)


def test_schema_keyword_still_rejects_bad_amounts():
    @tool(name="facade_typed_payment", schema=FinancialTransactionIntent)
    def _payment(amount: float):
        return amount

    try:
        with pytest.raises(Exception):
            registry.validate_intent_schema("facade_typed_payment", {"amount": "invalid_amt"})
        ok = registry.validate_intent_schema("facade_typed_payment", {"amount": 12})
        assert ok == {"valid": True, "status": "AUTHORIZED"}
        assert registry.tools["facade_typed_payment"]["risk_level"] == "low"
        assert registry.tools["facade_typed_payment"]["manifest"].name == "facade_typed_payment"
    finally:
        registry.tools.pop("facade_typed_payment", None)
