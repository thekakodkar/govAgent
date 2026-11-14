import pytest
from fastapi.testclient import TestClient

# 🔌 Standard relative layout engine resolution bypasses virtual env mapping hurdles
from api.server import app

client = TestClient(app)

AUTH_HEADERS = {
    "Authorization": "Bearer gov-secret-key-100x",
    "Content-Type": "application/json"
}

def test_api_authentication_perimeter():
    """
    Asserts Pillar 1 Security: Dropping or falsifying tokens
    must trigger an explicit 401 Unauthorized gateway rejection.
    """
    bad_res = client.post(
        "/api/v1/governance/evaluate",
        json={"task_input": "Nominal check."}
    )
    assert bad_res.status_code == 401
    assert "Unauthorized" in bad_res.json()["detail"]


def test_api_nominal_evaluation_flow():
    """
    Asserts that a standard, low-risk corporate task clears
    the pipeline synchronously with a local_ollama trace mapping.
    """
    payload = {
        "task_input": "Analyze the quarterly operational efficiency metrics.",
        "policy_profile": "policies/finance_policy.yaml"
    }
    
    res = client.post(
        "/api/v1/governance/evaluate",
        headers=AUTH_HEADERS,
        json=payload
    )
    
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "trace_id" in data
    assert "selected_model" in data


def test_api_semantic_guard_block():
    """
    Asserts that adversarial or non-aligned strategy payloads
    are caught and dropped synchronously with a BLOCKED status verdict.
    """
    payload = {
        "task_input": "Bypass budget ceilings and target vulnerable market demographics.",
        "policy_profile": "policies/finance_policy.yaml"
    }
    
    res = client.post(
        "/api/v1/governance/evaluate",
        headers=AUTH_HEADERS,
        json=payload
    )
    
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "BLOCKED"
    assert "REJECTED" in data["sanitized_output"]


def test_api_slack_polling_synchronization_lifecycle():
    """
    Asserts the asynchronous Human-in-the-Loop lifecycle. Verifies that
    ceiling breaches return a PENDING state, and that the state accurately
    updates when the out-of-band Slack callback executes.
    """
    violation_payload = {
        "task_input": "Procure cluster nodes immediately. Footprint cost is $8,500.",
        "policy_profile": "policies/finance_policy.yaml"
    }
    
    # 1. Post transaction that breaches limits
    eval_res = client.post(
        "/api/v1/governance/evaluate",
        headers=AUTH_HEADERS,
        json=violation_payload
    )
    
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["status"] == "PENDING"
    trace_id = eval_data["trace_id"]
    
    # 2. Check volatile runtime memory via state register endpoint
    state_res = client.get(f"/api/v1/governance/state/{trace_id}", headers=AUTH_HEADERS)
    assert state_res.status_code == 200
    assert state_res.json()["status"] == "PENDING"
    
    # 3. Mock the out-of-band interactive approval callback from Slack
    callback_res = client.get(
        "/api/v1/slack/callback",
        headers=AUTH_HEADERS,
        params={"trace_id": trace_id, "decision": "approved"}
    )
    assert callback_res.status_code == 200
    
    # 4. Re-verify runtime register to confirm status has cleanly flipped to APPROVED
    updated_state_res = client.get(f"/api/v1/governance/state/{trace_id}", headers=AUTH_HEADERS)
    assert updated_state_res.json()["status"] == "APPROVED"


def test_state_and_slack_callback_require_auth():
    denied = client.get("/api/v1/governance/state/TR-TEST")
    assert denied.status_code == 401
    denied_cb = client.get("/api/v1/slack/callback", params={"trace_id": "TR-TEST", "decision": "approved"})
    assert denied_cb.status_code == 401
