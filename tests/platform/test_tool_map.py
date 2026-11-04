from govagent.registry import registry
from govagent.registry.manager import GlobalRegistry

from tests.platform.runtime_support import activate_tenant_policy, make_agent, script_task
from govagent_platform.runtime.tool_map import authorize


def test_unknown_tool_is_blocked_and_global_registries_stay_unchanged(client):
    public_before = set(registry.tools)
    manager_before = set(GlobalRegistry().tools)
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
        json={"task": script_task("not_in_the_tenant_map")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "blocked"
    assert "Tool not legislated" in body["output"]
    assert set(registry.tools) == public_before
    assert set(GlobalRegistry().tools) == manager_before


def test_harbor_rejection_does_not_register_a_global_tool():
    public_before = set(registry.tools)
    manager_before = set(GlobalRegistry().tools)

    class Row:
        name = "wipe"
        risk_level = "low"
        requires_approval = False
        param_schema = None
        oci_repository = "example/malicious-image"
        artifact_digest = "sha256:abc"

    decision = authorize({"wipe": Row()}, "wipe", {})
    assert decision.ok is False
    assert decision.reason == "harbor_blocked"
    assert set(registry.tools) == public_before
    assert set(GlobalRegistry().tools) == manager_before
