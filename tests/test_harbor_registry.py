# tests/test_harbor_registry.py
import httpx
import pytest
from govagent.registry.harbor_verifier import HarborVerifier
from govagent.registry.manager import GlobalRegistry, tool
from govagent.guards.circuit_breaker import GovernanceViolation

def test_registry_legislation_blocks_unauthorized_tool():
    """Asserts that the framework instantly drops execution on completely unlegislated capabilities."""
    registry = GlobalRegistry()
    registry.tools.clear() # Reset singleton state space
    
    with pytest.raises(GovernanceViolation) as excinfo:
        registry.verify_and_resolve_tool("unregistered_arbitrary_shell_script")
        
    assert "REGISTRY EXCEPTION" in str(excinfo.value)

def test_registry_legislation_intercepts_malicious_cve_container():
    """Asserts that tools hosted inside contaminated images trigger a strict global circuit breaker drop."""
    registry = GlobalRegistry()
    registry.tools.clear()

    @tool(
        name="database_wipe",
        oci_repository="bizzteq/malicious-db-utils",
        artifact_digest="sha256:corrupted-hash"
    )
    def payload_tool():
        return "Executing..."
        
    with pytest.raises(GovernanceViolation) as excinfo:
        registry.verify_and_resolve_tool("database_wipe")
        
    assert "HARBOR REGISTRY BLOCK" in str(excinfo.value)
    print("✅ Harbor Realigned Supply Chain circuit breaker verified successfully.")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_mock_token_does_not_use_the_production_bypass():
    report = HarborVerifier(robot_token="mock-token").verify_tool_artifact("example/tool", "sha256:abc")
    assert report["verified"] is True
    assert report["reason"] == "COSIGN_SIGNATURE_VALIDATED"
    assert "PRODUCTION_BYPASS" not in report["reason"]
    assert "Offline mock-token stub" in report["details"]


def test_live_harbor_fails_closed_when_unreachable():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    verifier = HarborVerifier(
        registry_url="https://harbor.example",
        robot_token="real-secret",
        client=_client(handler),
    )
    report = verifier.verify_tool_artifact("payments/api", "sha256:abc")
    assert report["verified"] is False
    assert report["reason"] == "HARBOR_UNREACHABLE"


def test_live_harbor_rejects_a_critical_scan_and_accepts_a_signed_clean_image():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        assert request.url.path.startswith("/api/v2.0/projects/payments/repositories/")
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={
                    "scan_overview": {
                        "vuln": {"severity": "Critical", "scan_status": "Success", "summary": {"critical": 1}}
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "scan_overview": {"vuln": {"severity": "None", "scan_status": "Success", "summary": {"critical": 0, "high": 0}}},
                "accessories": [{"type": "signature.cosign"}],
            },
        )

    verifier = HarborVerifier(
        registry_url="https://harbor.example",
        robot_token="real-secret",
        client=_client(handler),
    )
    blocked = verifier.verify_tool_artifact("payments/api", "sha256:bad")
    assert blocked["verified"] is False
    assert blocked["reason"] == "CRITICAL_VULNERABILITY_FOUND"
    allowed = verifier.verify_tool_artifact("payments/api", "sha256:good")
    assert allowed["verified"] is True
    assert allowed["reason"] == "COSIGN_SIGNATURE_VALIDATED"


def test_live_harbor_rejects_http_errors():
    verifier = HarborVerifier(
        registry_url="https://harbor.example",
        robot_token="real-secret",
        client=_client(lambda request: httpx.Response(503, text="down")),
    )
    report = verifier.verify_tool_artifact("payments/api", "sha256:abc")
    assert report["verified"] is False
    assert report["reason"] == "HARBOR_REJECTED"