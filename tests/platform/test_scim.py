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
    names = {row["displayName"] for row in groups.json()["Resources"]}
    assert "tenant_admin" in names
    assert "tenant_auditor" in names

    revoked = client.put(f"/tenant/v1/scim/v2/Users/{user_id}", json={"active": False})
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["active"] is False

    still_there = client.get(f"/tenant/v1/scim/v2/Users/{user_id}")
    assert still_there.status_code == 200
    assert still_there.json()["userName"] == "scim-user@example.com"

    accounts.login(client, accounts.BETA_ADMIN_EMAIL, accounts.BETA_ADMIN_PASSWORD)
    hidden = client.get(f"/tenant/v1/scim/v2/Users/{user_id}")
    assert hidden.status_code == 404


def _group_by_name(client, name: str) -> dict:
    listed = client.get("/tenant/v1/scim/v2/Groups")
    assert listed.status_code == 200, listed.text
    for row in listed.json()["Resources"]:
        if row["displayName"] == name:
            return row
    raise AssertionError(name)


def test_scim_groups_crud_patch_permissions_and_isolation(client):
    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    invited = client.post(
        "/tenant/v1/identities",
        json={"email": "group-member@example.com", "display_name": "Group Member", "password": "group-member-pass"},
    )
    assert invited.status_code == 201, invited.text
    member_id = invited.json()["id"]
    membership = client.post("/tenant/v1/memberships", json={"identity_id": member_id})
    assert membership.status_code == 201, membership.text

    accounts.login(client, "group-member@example.com", "group-member-pass")
    denied = client.get("/tenant/v1/agents")
    assert denied.status_code == 403, denied.text

    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    admin_group = _group_by_name(client, "tenant_admin")
    protected = client.delete(f"/tenant/v1/scim/v2/Groups/{admin_group['id']}")
    assert protected.status_code == 403, protected.text
    renamed = client.put(
        f"/tenant/v1/scim/v2/Groups/{admin_group['id']}",
        json={"displayName": "not-the-system-role", "members": []},
    )
    assert renamed.status_code == 403, renamed.text

    added = client.patch(
        f"/tenant/v1/scim/v2/Groups/{admin_group['id']}",
        json={"Operations": [{"op": "add", "path": "members", "value": [{"value": member_id}]}]},
    )
    assert added.status_code == 200, added.text
    assert member_id in {row["value"] for row in added.json()["members"]}

    accounts.login(client, "group-member@example.com", "group-member-pass")
    allowed = client.get("/tenant/v1/agents")
    assert allowed.status_code == 200, allowed.text

    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    removed = client.patch(
        f"/tenant/v1/scim/v2/Groups/{admin_group['id']}",
        json={
            "Operations": [
                {"op": "remove", "path": f'members[value eq "{member_id}"]'}
            ]
        },
    )
    assert removed.status_code == 200, removed.text
    assert member_id not in {row["value"] for row in removed.json()["members"]}

    accounts.login(client, "group-member@example.com", "group-member-pass")
    denied_again = client.get("/tenant/v1/agents")
    assert denied_again.status_code == 403, denied_again.text

    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    created = client.post(
        "/tenant/v1/scim/v2/Groups",
        json={"displayName": "Analysts", "externalId": "okta-analysts", "members": [{"value": member_id}]},
    )
    assert created.status_code == 201, created.text
    group_id = created.json()["id"]
    assert created.json()["displayName"] == "Analysts"
    assert member_id in {row["value"] for row in created.json()["members"]}

    fetched = client.get(f"/tenant/v1/scim/v2/Groups/{group_id}")
    assert fetched.status_code == 200, fetched.text
    replaced = client.put(
        f"/tenant/v1/scim/v2/Groups/{group_id}",
        json={"displayName": "Analysts", "members": []},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["members"] == []

    accounts.login(client, accounts.BETA_ADMIN_EMAIL, accounts.BETA_ADMIN_PASSWORD)
    foreign = client.get(f"/tenant/v1/scim/v2/Groups/{group_id}")
    assert foreign.status_code == 404, foreign.text
    beta_names = {row["displayName"] for row in client.get("/tenant/v1/scim/v2/Groups").json()["Resources"]}
    assert "Analysts" not in beta_names
    cross = client.patch(
        f"/tenant/v1/scim/v2/Groups/{_group_by_name(client, 'tenant_admin')['id']}",
        json={"Operations": [{"op": "add", "path": "members", "value": [{"value": member_id}]}]},
    )
    assert cross.status_code == 400, cross.text

    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    deleted = client.delete(f"/tenant/v1/scim/v2/Groups/{group_id}")
    assert deleted.status_code == 204, deleted.text
    missing = client.get(f"/tenant/v1/scim/v2/Groups/{group_id}")
    assert missing.status_code == 404
