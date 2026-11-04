from tests.platform import accounts


def test_non_shared_isolation_tiers_are_rejected(client):
    accounts.login(client, accounts.OPERATOR_EMAIL, accounts.OPERATOR_PASSWORD)
    for tier in ("dedicated_schema", "dedicated_db"):
        response = client.post(
            "/platform/v1/tenants",
            json={
                "slug": f"tier-{tier.replace('_', '-')}",
                "display_name": "Later",
                "isolation_tier": tier,
            },
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "isolation_tier_not_available"

    created = client.post(
        "/platform/v1/tenants",
        json={"slug": "shared-ok", "display_name": "Shared", "isolation_tier": "shared"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["isolation_tier"] == "shared"
