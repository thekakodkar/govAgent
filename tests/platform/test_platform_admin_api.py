from govagent_platform.cli import BootstrapError, bootstrap_operator

from tests.platform import accounts


def test_operator_creates_tenant_and_assigns_plan(client):
    accounts.login(client, accounts.OPERATOR_EMAIL, accounts.OPERATOR_PASSWORD)
    plan = client.post(
        "/platform/v1/plans",
        json={
            "code": "regulated",
            "name": "Regulated",
            "max_agents": 20,
            "monthly_tco_ceiling_usd": "250.00",
            "retention_days": 90,
            "features": {"evidence": True},
        },
    )
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["id"]

    created = client.post(
        "/platform/v1/tenants",
        json={"slug": "gamma", "display_name": "Gamma", "region": "eu"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["slug"] == "gamma"
    assert body["status"] == "active"
    assert body["isolation_tier"] == "shared"
    assert body["plan"]["code"] == "community"
    assert "document" not in body

    assigned = client.put(
        f"/platform/v1/tenants/{body['id']}/plan",
        json={"plan_id": plan_id},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["plan"]["code"] == "regulated"

    listing = client.get("/platform/v1/tenants")
    assert listing.status_code == 200
    slugs = {row["slug"] for row in listing.json()}
    assert "gamma" in slugs


def test_tenant_actor_cannot_create_tenants(client):
    accounts.login(client, accounts.AUDITOR_EMAIL, accounts.AUDITOR_PASSWORD)
    denied = client.post(
        "/platform/v1/tenants",
        json={"slug": "delta", "display_name": "Delta"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Forbidden"


def test_bootstrap_refuses_a_second_operator(session, world):
    try:
        bootstrap_operator("second@example.com", "second-pass", session=session)
    except BootstrapError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("bootstrap_operator created a second operator")


def test_cli_refuses_password_on_argv():
    from govagent_platform.cli import main

    code = main(["bootstrap-operator", "--email", "cli@example.com"])
    assert code == 2
