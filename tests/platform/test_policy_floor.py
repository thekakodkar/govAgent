import govagent.policy as policy_mod

from tests.platform import accounts


def _document(daily: float) -> dict:
    return {
        "metadata": {"agent_name": "FloorCheck"},
        "fiscal_governance": {"global_limits": {"daily_budget_usd": daily}},
        "security_guardrails": {"required_guards": ["privacy_redaction"]},
    }


def test_tenant_policy_cannot_raise_the_floor_and_library_policy_is_constructed(client, monkeypatch):
    calls: list[dict] = []
    real = policy_mod.Policy

    class Spy(real):
        def __init__(self, config):
            calls.append(config)
            super().__init__(config)

    monkeypatch.setattr(policy_mod, "Policy", Spy)

    accounts.login(client, accounts.OPERATOR_EMAIL, accounts.OPERATOR_PASSWORD)
    drafted = client.post("/platform/v1/global-policies", json={"document": _document(100)})
    assert drafted.status_code == 201, drafted.text
    activated = client.post(f"/platform/v1/global-policies/{drafted.json()['id']}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"

    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    loose = client.post(
        "/tenant/v1/policies",
        json={"name": "Too loose", "document": _document(150)},
    )
    assert loose.status_code == 201, loose.text
    rejected = client.post(f"/tenant/v1/policies/{loose.json()['id']}/activate")
    assert rejected.status_code == 409, rejected.text
    assert "daily_budget_usd" in rejected.text

    strict = client.post(
        "/tenant/v1/policies",
        json={"name": "Tighter", "document": _document(40)},
    )
    assert strict.status_code == 201, strict.text
    accepted = client.post(f"/tenant/v1/policies/{strict.json()['id']}/activate")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "active"
    assert accepted.json()["floor_version"] == 1
    assert calls, "govagent.policy.Policy was not constructed"
    assert any(
        (doc.get("fiscal_governance") or {}).get("global_limits", {}).get("daily_budget_usd") == 40
        for doc in calls
    )
