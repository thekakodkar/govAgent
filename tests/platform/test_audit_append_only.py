from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from govagent_platform.db import begin_platform
from govagent_platform.services.tenants import create_tenant


def test_tenant_create_is_audited_and_audit_rows_cannot_be_mutated(session, world):
    begin_platform(session)
    before = session.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
    tenant = create_tenant(
        session,
        world.actor,
        slug="audited",
        display_name="Audited Tenant",
    )
    after = session.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
    assert after == before + 1

    actions = session.execute(
        text("SELECT action FROM audit_events WHERE target_id = :target_id"),
        {"target_id": str(tenant.id)},
    ).scalars().all()
    assert actions == ["tenant.create"]

    with pytest_db_error():
        with session.begin_nested():
            session.execute(text("UPDATE audit_events SET action = 'tampered'"))
    with pytest_db_error():
        with session.begin_nested():
            session.execute(text("DELETE FROM audit_events"))


class pytest_db_error:
    def __enter__(self):
        import pytest

        self._ctx = pytest.raises(DBAPIError)
        return self._ctx.__enter__()

    def __exit__(self, exc_type, exc, tb):
        return self._ctx.__exit__(exc_type, exc, tb)
