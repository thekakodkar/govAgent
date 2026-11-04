from sqlalchemy import text

from tests.platform import accounts


def test_stub_oidc_callback_reuses_the_membership(client, session):
    accounts.login(client, accounts.OPERATOR_EMAIL, accounts.OPERATOR_PASSWORD)
    listed = client.get("/platform/v1/tenants")
    assert listed.status_code == 200, listed.text
    session.execute(
        text(
            """
            INSERT INTO oidc_providers (issuer, client_id, client_secret_locator)
            VALUES ('https://idp.example', 'platform-ui', 'stub://local')
            """
        )
    )
    session.execute(
        text("UPDATE identities SET external_subject = 'alpha-subject' WHERE email = :email"),
        {"email": accounts.ALPHA_ADMIN_EMAIL},
    )
    session.flush()

    started = client.get("/platform/v1/session/oidc/start", params={"issuer": "https://idp.example"})
    assert started.status_code == 200, started.text
    client.cookies.clear()
    callback = client.post(
        "/platform/v1/session/oidc/callback",
        json={"state": started.json()["state"], "subject": "alpha-subject"},
    )
    assert callback.status_code == 200, callback.text
    assert callback.json()["scope"] == "tenant"
    assert callback.json()["tenant_id"]
    agents = client.get("/tenant/v1/agents")
    assert agents.status_code == 200, agents.text
