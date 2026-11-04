from tests.platform import accounts


def test_alpha_admin_invites_user_and_beta_cannot_read_the_policy(client):
    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    invited = client.post(
        "/tenant/v1/identities",
        json={
            "email": "new-alpha@example.com",
            "display_name": "New Alpha",
            "password": "new-alpha-pass",
        },
    )
    assert invited.status_code == 201, invited.text
    identity_id = invited.json()["id"]

    membership = client.post("/tenant/v1/memberships", json={"identity_id": identity_id})
    assert membership.status_code == 201, membership.text
    assert membership.json()["status"] == "active"

    granted = client.post(
        f"/tenant/v1/memberships/{identity_id}/roles",
        json={"role_code": "tenant_admin"},
    )
    assert granted.status_code == 201, granted.text
    assert "tenant.policies.write" in granted.json()["permissions"]

    secret = "alpha-only-policy-document-marker"
    drafted = client.post(
        "/tenant/v1/policies",
        json={
            "name": "Alpha draft",
            "document": {
                "metadata": {"agent_name": "Alpha"},
                "note": secret,
            },
        },
    )
    assert drafted.status_code == 201, drafted.text
    assert secret in drafted.text

    accounts.login(client, accounts.BETA_ADMIN_EMAIL, accounts.BETA_ADMIN_PASSWORD)
    visible = client.get("/tenant/v1/policies")
    assert visible.status_code == 200, visible.text
    assert secret not in visible.text
    assert visible.json() == []
