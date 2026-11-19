"""Regression tests for the November 2026 security review."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from govagent.extensions.mcp import GovernedMCPGateway
from govagent.guards import GovernanceViolation
from govagent.guards.circuit_breaker import CircuitBreaker, checked_amount
from govagent.hitl import HITLManager
from govagent.hitl.manager import ApprovalRequest
from govagent.hitl.slack_adapter import SlackJudiciaryAdapter
from govagent.policy import Policy
from govagent.registry.harbor_verifier import HarborVerifier
from govagent.telemetry import TelemetryManager


def _policy() -> Policy:
    return Policy(
        {
            "metadata": {"agent_name": "hardening"},
            "registry_alignment": {"allowed_tools": ["pay"], "high_risk_tools": []},
            "fiscal_governance": {"global_limits": {"daily_budget_usd": 1000.0, "transaction_ceiling": 50.0}},
            "alignment": {"mission_statement": "m", "prohibited_strategies": []},
        }
    )


# --- fiscal gates must fail closed on malformed amounts -----------------------------------------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, -1e9, "nan", "abc", True, [1]])
def test_checked_amount_rejects_non_finite_negative_and_non_numeric(bad):
    with pytest.raises(GovernanceViolation):
        checked_amount(bad)


def test_checked_amount_accepts_plain_numbers():
    assert checked_amount(12) == 12.0
    assert checked_amount("12.50") == 12.5


@pytest.mark.parametrize("bad", [float("nan"), "NaN", -500, "ten"])
def test_circuit_breaker_blocks_malformed_amounts(bad):
    breaker = CircuitBreaker(_policy())
    with pytest.raises(GovernanceViolation):
        asyncio.run(breaker.evaluate("pay", {"amount": bad}))


def test_circuit_breaker_still_enforces_the_ceiling_and_allows_normal_amounts():
    breaker = CircuitBreaker(_policy())
    assert asyncio.run(breaker.evaluate("pay", {"amount": 10})) is True
    assert asyncio.run(breaker.evaluate("pay", {})) is True
    with pytest.raises(GovernanceViolation):
        asyncio.run(breaker.evaluate("pay", {"amount": 51}))


def test_nan_amount_does_not_lower_the_approval_tier():
    seen = {}

    class Capture:
        async def notify(self, request: ApprovalRequest):
            seen["tier"] = request.risk_tier
            return False

    manager = HITLManager(adapter=Capture())
    asyncio.run(manager.secure_approval("a", "r", {"params": {"amount": float("nan")}}))
    assert seen["tier"] == "TIER_3_CRITICAL"
    asyncio.run(manager.secure_approval("a", "r", {"params": {"amount": "9000"}}))
    assert seen["tier"] == "TIER_3_CRITICAL"
    asyncio.run(manager.secure_approval("a", "r", {"params": {"amount": 10}}))
    assert seen["tier"] == "TIER_1_OPERATIONAL"
    asyncio.run(manager.secure_approval("a", "r", {}))
    assert seen["tier"] == "TIER_1_OPERATIONAL"


# --- Slack approvals: roles come from an allow-list, not from the button ------------------------

def _adapter(**kwargs) -> SlackJudiciaryAdapter:
    adapter = SlackJudiciaryAdapter(bot_token="xoxb-test", app_token="xapp-test", channel_id="C1", **kwargs)
    adapter.client = MagicMock()
    adapter.client.chat_postMessage.return_value = {"ts": "1.2"}
    adapter.socket_client = MagicMock()
    return adapter


def _click(action_id: str, user_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="interactive",
        envelope_id="e",
        payload={"actions": [{"action_id": action_id, "value": "req-1"}], "user": {"id": user_id}},
    )


def _pending(adapter, loop):
    request = ApprovalRequest(
        request_id="req-1", agent_id="a", reason="r", context={"message_ts": "1.2"}, required_score=2.0
    )
    future = loop.create_future()
    adapter.pending_requests["req-1"] = (request, future)
    return request, future


def test_unlisted_user_cannot_approve_when_an_allow_list_is_set():
    loop = asyncio.new_event_loop()
    try:
        adapter = _adapter(allowed_approvers={"UBOSS": "Director"})
        request, future = _pending(adapter, loop)
        adapter.handle_interaction(MagicMock(), _click("approve_Director", "UINTRUDER"))
        adapter.handle_interaction(MagicMock(), _click("reject", "UINTRUDER"))
        assert not request.approvers and not future.done()
    finally:
        loop.close()


def test_listed_user_cannot_sign_above_their_own_role():
    loop = asyncio.new_event_loop()
    try:
        adapter = _adapter(allowed_approvers={"ULEAD": "Lead"})
        request, future = _pending(adapter, loop)
        adapter.handle_interaction(MagicMock(), _click("approve_Director", "ULEAD"))
        assert not request.approvers
        adapter.handle_interaction(MagicMock(), _click("approve_Lead", "ULEAD"))
        assert len(request.approvers) == 1
    finally:
        loop.close()


def test_default_adapter_keeps_the_open_behaviour_for_backward_compatibility():
    loop = asyncio.new_event_loop()
    try:
        adapter = _adapter()
        request, _ = _pending(adapter, loop)
        adapter.handle_interaction(MagicMock(), _click("approve_Lead", "ANYONE"))
        assert len(request.approvers) == 1
    finally:
        loop.close()


# --- Harbor offline stub is refused in production ----------------------------------------------

def test_mock_token_stub_is_refused_in_production(monkeypatch):
    monkeypatch.setenv("GOVAGENT_ENVIRONMENT", "production")
    report = HarborVerifier(robot_token="mock-token").verify_tool_artifact("team/app", "sha256:abc")
    assert report["verified"] is False
    assert report["reason"] == "HARBOR_UNVERIFIED"


def test_mock_token_stub_still_works_outside_production(monkeypatch):
    monkeypatch.delenv("GOVAGENT_ENVIRONMENT", raising=False)
    assert HarborVerifier(robot_token="mock-token").verify_tool_artifact("team/app", "sha256:abc")["verified"] is True


# --- MCP gateway redacts nested arguments ------------------------------------------------------

def test_mcp_gateway_redacts_pii_in_nested_arguments():
    gateway = GovernedMCPGateway(
        _policy(), telemetry=TelemetryManager(persist_jsonl=False, buffer_path="logs/test_buffer.jsonl")
    )
    gateway.privacy = SimpleNamespace(redact_task=lambda text: text.replace("secret@example.com", "<EMAIL>"))
    out = gateway._redact_arguments(
        {"to": "secret@example.com", "meta": {"cc": ["secret@example.com"], "n": 1}, "pair": ("secret@example.com",)}
    )
    assert out == {"to": "<EMAIL>", "meta": {"cc": ["<EMAIL>"], "n": 1}, "pair": ("<EMAIL>",)}


# --- sandbox API -------------------------------------------------------------------------------

@pytest.fixture()
def api_client():
    from api.server import app

    return TestClient(app)


AUTH = {"Authorization": "Bearer gov-secret-key-100x"}


@pytest.mark.parametrize(
    "profile",
    ["/etc/passwd", "../pyproject.toml", "policies/../pyproject.toml", "policies/../../etc/passwd", "pyproject.toml"],
)
def test_policy_profile_cannot_leave_the_policies_directory(api_client, profile):
    response = api_client.post(
        "/api/v1/governance/evaluate", json={"task_input": "hello", "policy_profile": profile}, headers=AUTH
    )
    assert response.status_code == 404


def test_token_is_required_and_wrong_token_is_rejected(api_client):
    body = {"task_input": "hello"}
    assert api_client.post("/api/v1/governance/evaluate", json=body).status_code == 401
    assert api_client.post(
        "/api/v1/governance/evaluate", json=body, headers={"Authorization": "Bearer nope"}
    ).status_code == 401


def test_cors_does_not_reflect_arbitrary_origins_with_credentials(api_client):
    response = api_client.options(
        "/api/v1/governance/policies",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") != "https://evil.example"
    assert response.headers.get("access-control-allow-origin") != "*"
    assert "access-control-allow-credentials" not in response.headers


def test_oversized_task_input_is_rejected(api_client):
    response = api_client.post(
        "/api/v1/governance/evaluate", json={"task_input": "x" * 20_001}, headers=AUTH
    )
    assert response.status_code == 422


def test_live_state_map_is_bounded():
    from api.server import _BoundedStates

    states = _BoundedStates()
    states.MAX_ENTRIES = 3
    for index in range(10):
        states[f"t{index}"] = {}
    assert len(states) == 3 and "t9" in states and "t0" not in states

def test_sandbox_origin_lock_is_off_by_default(api_client):
    assert api_client.get("/api/v1/governance/policies").status_code == 401
    assert api_client.get("/api/v1/governance/policies", headers=AUTH).status_code == 200


def test_sandbox_origin_lock_and_rate_limit(api_client, monkeypatch):
    from api.server import reset_sandbox_gate_state

    reset_sandbox_gate_state()
    monkeypatch.setenv("GOVAGENT_ORIGIN_SECRET", "sandbox-origin-secret")
    monkeypatch.setenv("GOVAGENT_SANDBOX_RATE_LIMIT", "3")
    monkeypatch.setenv("GOVAGENT_SANDBOX_RATE_WINDOW_SECONDS", "60")
    blocked = api_client.get("/api/v1/governance/policies", headers=AUTH)
    assert blocked.status_code == 403
    assert blocked.text == "Forbidden"
    headers = {**AUTH, "X-Govagent-Origin": "sandbox-origin-secret"}
    assert api_client.get("/api/v1/governance/policies", headers=headers).status_code == 200
    assert api_client.get("/api/v1/governance/policies", headers=headers).status_code == 200
    assert api_client.get("/api/v1/governance/policies", headers=headers).status_code == 200
    limited = api_client.get("/api/v1/governance/policies", headers=headers)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_sandbox_failed_auth_is_logged_without_the_token(api_client, caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="govagent.api"):
        response = api_client.get(
            "/api/v1/governance/policies",
            headers={"Authorization": "Bearer wrong-token-value", "User-Agent": "abuse-bot/1.0"},
        )
    assert response.status_code == 401
    text = caplog.text
    assert "sandbox auth rejected" in text and "abuse-bot/1.0" in text and "/api/v1/governance/policies" in text
    assert "wrong-token-value" not in text
