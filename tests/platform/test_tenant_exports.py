from govagent.telemetry.exporters.mock import MockSOCExporter

from tests.platform import accounts
from tests.platform.runtime_support import activate_tenant_policy, make_agent, script_task


def test_dossier_and_cfo_stay_inside_the_tenant(client, monkeypatch):
    calls: list[str] = []

    async def record(self, snapshot):
        calls.append(str(snapshot.get("trace_id")))
        return True

    monkeypatch.setattr(MockSOCExporter, "export", record)
    policy_id = activate_tenant_policy(client, daily=100)
    agent_id = make_agent(
        client,
        policy_id,
        "record_note",
        requires_approval=False,
        param_schema={"required": []},
        agent_name="export-agent",
    )
    sink = client.post("/tenant/v1/sinks", json={"sink_type": "mock", "locator": "memory://alpha"})
    assert sink.status_code == 201, sink.text
    listed = client.get("/tenant/v1/sinks")
    assert listed.status_code == 200
    assert listed.json()[0]["locator"] == "memory://alpha"
    evaluated = client.post(
        f"/tenant/v1/agents/{agent_id}/evaluate",
        json={"task": script_task("record_note", tokens=10)},
    )
    assert evaluated.status_code == 200, evaluated.text
    trace_id = evaluated.json()["trace_id"]
    assert trace_id in calls

    dossier = client.get("/tenant/v1/compliance/export")
    assert dossier.status_code == 200, dossier.text
    traces = [row["trace_id"] for row in dossier.json()["eu_ai_act_article_12"]]
    assert trace_id in traces
    assert dossier.json()["dossier_sha256"]

    overview = client.get("/tenant/v1/financials/risk-overview")
    assert overview.status_code == 200, overview.text
    assert overview.json()["total_realized_spend_usd"] > 0

    accounts.login(client, accounts.BETA_ADMIN_EMAIL, accounts.BETA_ADMIN_PASSWORD)
    foreign = client.get("/tenant/v1/compliance/export")
    assert foreign.status_code == 200, foreign.text
    foreign_traces = [row["trace_id"] for row in foreign.json()["eu_ai_act_article_12"]]
    assert trace_id not in foreign_traces
    beta_money = client.get("/tenant/v1/financials/risk-overview")
    assert beta_money.status_code == 200
    assert beta_money.json()["total_realized_spend_usd"] == 0
