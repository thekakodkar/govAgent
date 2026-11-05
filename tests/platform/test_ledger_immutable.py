import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from govagent_platform.db import begin_tenant
from tests.platform import accounts


def _rejects_write(session, statement: str) -> None:
    with pytest.raises(ProgrammingError):
        with session.begin_nested():
            session.execute(text(statement))


def test_app_role_cannot_update_or_delete_audit_or_ledger(client, session, world):
    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    begin_tenant(session, world.alpha.id)
    session.execute(
        text(
            """
            INSERT INTO fiscal_ledger_entries (tenant_id, trace_id, amount_usd)
            VALUES (:tenant_id, 'immutable-trace', 1)
            """
        ),
        {"tenant_id": world.alpha.id},
    )
    session.flush()
    _rejects_write(session, "UPDATE fiscal_ledger_entries SET amount_usd = 0")
    _rejects_write(session, "DELETE FROM fiscal_ledger_entries")
    _rejects_write(session, "UPDATE audit_events SET action = 'rewritten'")
    _rejects_write(session, "DELETE FROM audit_events")
    remaining = session.execute(
        text("SELECT count(*) FROM fiscal_ledger_entries WHERE trace_id = 'immutable-trace'")
    ).scalar_one()
    assert int(remaining) == 1