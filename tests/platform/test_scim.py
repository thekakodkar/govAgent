from tests.platform import accounts


def test_scim_user_is_a_membership_and_revoke_does_not_delete_the_identity(client):
    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    created = client.post(
        "/tenant/v1/scim/v2/Users",
        json={"userName": "scim-user@example.com", "displayName": "SCIM User", "externalId": "ext-scim-1"},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert created.json()["active"] is True

    listed = client.get("/tenant/v1/scim/v2/Users", params={"filter": 'userName eq "scim-user@example.com"'})
    assert listed.status_code == 200, listed.text
    assert listed.json()["totalResults"] == 1
    assert listed.json()["Resources"][0]["id"] == user_id

    groups = client.get("/tenant/v1/scim/v2/Groups")
    assert groups.status_code == 200
    assert groups.json()["totalResults"] == 0

    revoked = client.put(f"/tenant/v1/scim/v2/Users/{user_id}", json={"active": False})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["active"] is False

    still_there = client.get(f"/tenant/v1/scim/v2/Users/{user_id}")
    assert still_there.status_code == 200
    assert still_there.json()["userName"] == "scim-user@example.com"

    accounts.login(client, accounts.BETA_ADMIN_EMAIL, accounts.BETA_ADMIN_PASSWORD)
    hidden = client.get(f"/tenant/v1/scim/v2/Users/{user_id}")
    assert hidden.status_code == 404
