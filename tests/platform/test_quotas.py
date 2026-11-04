from tests.platform import accounts
from tests.platform.runtime_support import activate_tenant_policy, make_agent, script_task


def test_second_active_agent_is_rejected_at_the_plan_cap(client, world):
    accounts.login(client, accounts.OPERATOR_EMAIL, accounts.OPERATOR_PASSWORD)
    plan = client.post(
        "/platform/v1/plans",
        json={
            "code": "cap-one",
            "name": "Cap one",
            "max_agents": 1,
            "monthly_tco_ceiling_usd": "100",
            "retention_days": 30,
        },
    )
    assert plan.status_code == 201, plan.text
    assigned = client.put(
        f"/platform/v1/tenants/{world.alpha.id}/plan",
        json={"plan_id": plan.json()["id"]},
    )
    assert assigned.status_code == 200, assigned.text
    policy_id = activate_tenant_policy(client, daily=100)
    make_agent(client, policy_id, "record_note", requires_approval=False, param_schema={"required": []})
    blocked = client.post(
        "/tenant/v1/agents",
        json={"name": "second-agent", "persona": "Clerk", "policy_id": policy_id},
    )
    assert blocked.status_code == 409, blocked.text
    assert "1" in blocked.text


def test_monthly_ceiling_blocks_the_projected_step(client, world):
    accounts.login(client, accounts.OPERATOR_EMAIL, accounts.OPERATOR_PASSWORD)
    plan = client.post(
        "/platform/v1/plans",
        json={
            "code": "tiny-month",
            "name": "Tiny month",
            "max_agents": 5,
            "monthly_tco_ceiling_usd": "0.0001",
            "retention_days": 30,
        },
    )
    assert plan.status_code == 201, plan.text
    assigned = client.put(
        f"/platform/v1/tenants/{world.alpha.id}/plan",
        json={"plan_id": plan.json()["id"]},
    )
    assert assigned.status_code == 200, assigned.text
    policy_id = activate_tenant_policy(client, daily=100)
    agent_id = make_agent(
        client,
        policy_id,
        "record_note",
        requires_approval=False,
        param_schema={"required": []},
        agent_name="monthly-agent",
    )
    response = client.post(
        f"/tenant/v1/agents/{agent_id}/evaluate",
        json={"task": script_task("record_note", tokens=10)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "blocked"
    assert "MONTHLY TCO REJECT" in body["output"]
