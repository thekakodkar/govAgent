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
    assert body["output"] == "Task complete."
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


def test_non_numeric_amount_is_blocked_and_audited(client, session):
    policy_id = activate_tenant_policy(client, daily=100)
    agent_id = make_agent(
        client,
        policy_id,
        "execute_financial_transaction",
        requires_approval=False,
        param_schema={"model": "FinancialTransactionIntent"},
        agent_name="payer-bad-amount",
    )
    response = client.post(
        f"/tenant/v1/agents/{agent_id}/evaluate",
        json={"task": script_task("execute_financial_transaction", {"amount": "nope"}, tokens=10)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "blocked"
    assert "Schema Violation" in body["output"]
    audited = session.execute(
        text(
            "SELECT after->>'status' FROM audit_events "
            "WHERE action = 'runtime.evaluate' AND target_id = :trace_id"
        ),
        {"trace_id": body["trace_id"]},
    ).scalar_one()
    assert audited == "blocked"


def test_allow_list_permission_error_is_denied_and_audited(client, session):
    from govagent.registry import registry, tool

    from tests.platform import accounts

    accounts.login(client, accounts.OPERATOR_EMAIL, accounts.OPERATOR_PASSWORD)
    floor = {
        "metadata": {"agent_name": "Floor"},
        "fiscal_governance": {"global_limits": {"daily_budget_usd": 1000}},
        "tools": [{"name": "record_note"}],
    }
    drafted = client.post("/platform/v1/global-policies", json={"document": floor})
    assert drafted.status_code == 201, drafted.text
    activated = client.post(f"/platform/v1/global-policies/{drafted.json()['id']}/activate")
    assert activated.status_code == 200, activated.text
    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    document = {
        "metadata": {"agent_name": "AllowList"},
        "fiscal_governance": {"global_limits": {"daily_budget_usd": 100}},
        "infrastructure": {"routing_mode": "LOCAL_ONLY", "default_provider": "scripted"},
        "tools": [{"name": "record_note"}],
    }
    policy = client.post("/tenant/v1/policies", json={"name": "allow-list", "document": document})
    assert policy.status_code == 201, policy.text
    turned_on = client.post(f"/tenant/v1/policies/{policy.json()['id']}/activate")
    assert turned_on.status_code == 200, turned_on.text
    agent = client.post(
        "/tenant/v1/agents",
        json={"name": "allow-list-agent", "persona": "Clerk", "policy_id": policy.json()["id"]},
    )
    assert agent.status_code == 201, agent.text

    @tool(name="shadow_outside_allow_list", risk_level="low")
    def _shadow():
        return "x"

    try:
        response = client.post(
            f"/tenant/v1/agents/{agent.json()['id']}/evaluate",
            json={"task": script_task("record_note")},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "denied"
        assert "UNAUTHORIZED TOOL" in body["output"]
        audited = session.execute(
            text(
                "SELECT after->>'status' FROM audit_events "
                "WHERE action = 'runtime.evaluate' AND target_id = :agent_id"
            ),
            {"agent_id": agent.json()["id"]},
        ).scalar_one()
        assert audited == "denied"
    finally:
        registry.tools.pop("shadow_outside_allow_list", None)
