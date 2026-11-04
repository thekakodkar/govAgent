from tests.platform import accounts
from tests.platform.runtime_support import activate_tenant_policy, make_agent, script_task


def _invite(client, email: str, password: str) -> str:
    created = client.post(
        "/tenant/v1/identities",
        json={"email": email, "display_name": email, "password": password},
    )
    assert created.status_code == 201, created.text
    identity_id = created.json()["id"]
    membership = client.post("/tenant/v1/memberships", json={"identity_id": identity_id})
    assert membership.status_code == 201, membership.text
    granted = client.post(
        f"/tenant/v1/memberships/{identity_id}/roles",
        json={"role_code": "tenant_admin"},
    )
    assert granted.status_code == 201, granted.text
    return identity_id


def _assign(client, identity_id: str, role: str) -> None:
    response = client.put(
        f"/tenant/v1/hitl-assignments/{identity_id}",
        json={"hitl_role": role},
    )
    assert response.status_code == 200, response.text


def _pending_request(client, suffix: str) -> str:
    policy_id = activate_tenant_policy(client, daily=100)
    tool_name = f"pay-{suffix}"
    agent_id = make_agent(
        client,
        policy_id,
        tool_name,
        requires_approval=True,
        param_schema={"model": "FinancialTransactionIntent"},
        agent_name=f"payer-{suffix}",
    )
    response = client.post(
        f"/tenant/v1/agents/{agent_id}/evaluate",
        json={"task": script_task(tool_name, {"amount": 1500}, tokens=10)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "pending", body
    assert body["approval_request_id"]
    detail = client.get(f"/tenant/v1/approvals/{body['approval_request_id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["required_score"] == 2.5
    assert detail.json()["risk_tier"] == "TIER_2_HIGH"
    return body["approval_request_id"]


def test_clerk_alone_stays_pending(client):
    request_id = _pending_request(client, "clerk")
    clerk_id = _invite(client, "clerk@example.com", "clerk-pass-1")
    _assign(client, clerk_id, "Clerk")
    accounts.login(client, "clerk@example.com", "clerk-pass-1")
    vote = client.post(f"/tenant/v1/approvals/{request_id}/votes", json={"decision": "APPROVED"})
    assert vote.status_code == 200, vote.text
    assert vote.json()["status"] == "pending"
    assert vote.json()["signatures"][0]["weight"] == 0.5
    assert vote.json()["signatures"][0]["role"] == "Clerk"


def test_director_then_lead_meets_quorum(client, world):
    request_id = _pending_request(client, "quorum")
    lead_id = _invite(client, "lead@example.com", "lead-pass-1")
    _assign(client, str(world.alpha_admin.id), "Director")
    _assign(client, lead_id, "Lead")

    director = client.post(f"/tenant/v1/approvals/{request_id}/votes", json={"decision": "APPROVED"})
    assert director.status_code == 200, director.text
    assert director.json()["status"] == "pending"
    assert director.json()["signatures"][0]["weight"] == 2.0

    duplicate = client.post(f"/tenant/v1/approvals/{request_id}/votes", json={"decision": "APPROVED"})
    assert duplicate.status_code == 409

    accounts.login(client, "lead@example.com", "lead-pass-1")
    lead = client.post(f"/tenant/v1/approvals/{request_id}/votes", json={"decision": "APPROVED"})
    assert lead.status_code == 200, lead.text
    assert lead.json()["status"] == "approved"
    assert {item["weight"] for item in lead.json()["signatures"]} == {2.0, 1.0}


def test_rejected_vote_vetoes(client, world):
    request_id = _pending_request(client, "veto")
    _assign(client, str(world.alpha_admin.id), "Director")
    vote = client.post(f"/tenant/v1/approvals/{request_id}/votes", json={"decision": "REJECTED"})
    assert vote.status_code == 200, vote.text
    assert vote.json()["status"] == "rejected"
