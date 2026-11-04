"""Shared setup for runtime tests."""

from __future__ import annotations

import json

from tests.platform import accounts


def script_task(tool: str, args: dict | None = None, tokens: int = 10, thought: str = "proceed") -> str:
    payload = {"tool": tool, "args": args or {}, "tokens": tokens, "thought": thought}
    return "Record the controlled task [[govagent-script]]" + json.dumps(payload) + "[[/govagent-script]]"


def activate_tenant_policy(client, daily: float) -> str:
    accounts.login(client, accounts.OPERATOR_EMAIL, accounts.OPERATOR_PASSWORD)
    floor = {
        "metadata": {"agent_name": "Floor"},
        "fiscal_governance": {
            "global_limits": {"daily_budget_usd": 1000, "recursive_tco_limit": 1000}
        },
    }
    drafted = client.post("/platform/v1/global-policies", json={"document": floor})
    assert drafted.status_code == 201, drafted.text
    activated = client.post(f"/platform/v1/global-policies/{drafted.json()['id']}/activate")
    assert activated.status_code == 200, activated.text

    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    document = {
        "metadata": {"agent_name": "TenantRuntime"},
        "fiscal_governance": {
            "global_limits": {"daily_budget_usd": daily, "recursive_tco_limit": 1000}
        },
        "infrastructure": {"routing_mode": "LOCAL_ONLY", "default_provider": "scripted"},
    }
    policy = client.post("/tenant/v1/policies", json={"name": f"runtime-{daily}", "document": document})
    assert policy.status_code == 201, policy.text
    turned_on = client.post(f"/tenant/v1/policies/{policy.json()['id']}/activate")
    assert turned_on.status_code == 200, turned_on.text
    return policy.json()["id"]


def make_agent(
    client,
    policy_id: str,
    tool_name: str,
    *,
    requires_approval: bool,
    param_schema: dict | None,
    agent_name: str | None = None,
) -> str:
    tool = client.post(
        "/tenant/v1/tools",
        json={
            "name": tool_name,
            "description": tool_name,
            "risk_level": "low",
            "requires_approval": requires_approval,
            "param_schema": param_schema,
        },
    )
    assert tool.status_code == 201, tool.text
    agent = client.post(
        "/tenant/v1/agents",
        json={
            "name": agent_name or f"agent-for-{tool_name}",
            "persona": "Clerk",
            "policy_id": policy_id,
        },
    )
    assert agent.status_code == 201, agent.text
    return agent.json()["id"]
