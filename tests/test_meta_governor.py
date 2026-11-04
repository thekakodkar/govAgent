import json
import pytest
from govagent.governance.meta import MetaGovernor

@pytest.fixture
def mock_audit_ledger(tmp_path):
    """
    v0.6.0 Isolated Test Fixture.
    Generates a localized, thread-safe path to test MetaGovernor ledger-scraping capabilities.
    """
    return tmp_path / "audit_buffer.jsonl"

def test_meta_governor_under_tolerance(mock_audit_ledger):
    """Verifies that the system ignores low-frequency isolated friction events."""
    governor = MetaGovernor(log_path=str(mock_audit_ledger), friction_threshold=3)
    
    # Write only two rejections (under our systemic threshold of 3)
    with open(mock_audit_ledger, "w") as f:
        f.write(json.dumps({"status": "BLOCKED: RECURSIVE_TCO_REJECT", "metrics": {"recursive_tco_usd": 100.0, "requested_amount": 120.0}}) + "\n")
        f.write(json.dumps({"status": "BLOCKED: RECURSIVE_TCO_REJECT", "metrics": {"recursive_tco_usd": 100.0, "requested_amount": 130.0}}) + "\n")
        
    analysis = governor.analyze_friction()
    assert analysis["status"] == "OPTIMAL"
    assert "within tolerance" in analysis["reason"]

def test_meta_governor_triggers_amendment(mock_audit_ledger):
    """Verifies that persistent blocks generate a calculated policy adjustment proposal."""
    governor = MetaGovernor(log_path=str(mock_audit_ledger), friction_threshold=3)
    
    # Simulate three repetitive blocks (Threshold met)
    mock_entry = {
        "status": "BLOCKED: RECURSIVE_TCO_REJECT", 
        "policy_id": "finance_policy.yaml", 
        "metrics": {"recursive_tco_usd": 100.0, "requested_amount": 150.0}
    }
    with open(mock_audit_ledger, "w") as f:
        for _ in range(3):
            f.write(json.dumps(mock_entry) + "\n")
            
    analysis = governor.analyze_friction()
    
    assert analysis["type"] == "POLICY_AMENDMENT_PROPOSAL"
    assert analysis["target_policy"] == "finance_policy.yaml"
    # Smart calculation verification: 150.0 average overrun * 1.1 safety margin = 165.00
    assert analysis["proposed_limit"] == 165.00
    assert analysis["timestamp"].endswith("Z")
    assert "+00:00" not in analysis["timestamp"]