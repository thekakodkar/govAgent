from sqlalchemy import text

from tests.platform.runtime_support import activate_tenant_policy, make_agent, script_task


def test_scripted_tool_persists_snapshot_and_ledger(client, session):
    policy_id = activate_tenant_policy(client, daily=100)
    agent_id = make_agent(
        client,
        policy_id,
        "record_note",
        requires_approval=False,
        param_schema={"required": []},
    )
    response = client.post(
        f"/tenant/v1/agents/{agent_id}/evaluate",
        json={"task": script_task("record_note", tokens=10)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert body["output"] == "AUTHORIZED:record_note"
    stored = client.get(f"/tenant/v1/executions/{body['trace_id']}")
    assert stored.status_code == 200, stored.text
    assert stored.json()["status"] == "success"
    spend = session.execute(text("SELECT COALESCE(SUM(amount_usd), 0) FROM fiscal_ledger_entries")).scalar_one()
    assert float(spend) > 0


def test_fiscal_governance_ceiling_blocks_without_changing_policy_class(client):
    policy_id = activate_tenant_policy(client, daily=0.01)
    agent_id = make_agent(
        client,
        policy_id,
        "record_note",
        requires_approval=False,
        param_schema={"required": []},
    )
    response = client.post(
        f"/tenant/v1/agents/{agent_id}/evaluate",
        json={"task": script_task("record_note", tokens=10000)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "blocked"
    assert "RECURSIVE TCO REJECT" in body["output"]
