from uuid import UUID

from sqlalchemy import text

from govagent_platform.db import begin_platform, begin_tenant
from tests.platform import accounts


def test_dedicated_schema_hides_cost_centers_and_dedicated_db_is_refused(client, session, world):
    accounts.login(client, accounts.OPERATOR_EMAIL, accounts.OPERATOR_PASSWORD)
    created = client.post(
        "/platform/v1/tenants",
        json={"slug": "schema-tenant", "display_name": "Schema"},
    )
    assert created.status_code == 201, created.text
    tenant_id = created.json()["id"]

    refused = client.post(
        f"/platform/v1/tenants/{tenant_id}/isolation",
        json={"isolation_tier": "dedicated_db"},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "dedicated_db_not_available"

    begin_tenant(session, UUID(tenant_id))
    session.execute(
        text(
            "INSERT INTO cost_centers (tenant_id, code, gl_account) "
            "VALUES (:tenant_id, 'CC-PROMOTE', 'GL-1')"
        ),
        {"tenant_id": tenant_id},
    )
    session.flush()
    begin_platform(session)

    promoted = client.post(
        f"/platform/v1/tenants/{tenant_id}/isolation",
        json={"isolation_tier": "dedicated_schema"},
    )
    assert promoted.status_code == 200, promoted.text
    schema_name = promoted.json()["schema_name"]
    assert promoted.json()["isolation_tier"] == "dedicated_schema"
    assert schema_name.startswith("tenant_")

    begin_tenant(session, UUID(tenant_id), schema_name)
    own = session.execute(
        text("SELECT count(*) FROM cost_centers WHERE code = 'CC-PROMOTE'")
    ).scalar_one()
    assert int(own) == 1

    begin_tenant(session, world.beta.id, schema_name)
    foreign = session.execute(
        text("SELECT count(*) FROM cost_centers WHERE code = 'CC-PROMOTE'")
    ).scalar_one()
    assert int(foreign) == 0
