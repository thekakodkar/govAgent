from sqlalchemy import text

from govagent_platform.db import begin_platform, begin_tenant
from tests.platform import accounts


def test_purge_archives_snapshots_and_leaves_ledger_and_audit(client, session, world):
    accounts.login(client, accounts.ALPHA_ADMIN_EMAIL, accounts.ALPHA_ADMIN_PASSWORD)
    begin_tenant(session, world.alpha.id)
    snapshot_id = session.execute(
        text(
            """
            INSERT INTO execution_snapshots (
                tenant_id, trace_id, status, metrics, guards_evaluated, created_at
            ) VALUES (
                :tenant_id, 'old-trace', 'success', '{}'::jsonb, '[]'::jsonb,
                now() - interval '400 days'
            )
            RETURNING id
            """
        ),
        {"tenant_id": world.alpha.id},
    ).scalar_one()
    session.execute(
        text(
            """
            INSERT INTO fiscal_ledger_entries (tenant_id, trace_id, amount_usd, created_at)
            VALUES (:tenant_id, 'old-trace', 1.25, now() - interval '400 days')
            """
        ),
        {"tenant_id": world.alpha.id},
    )
    session.flush()
    audit_before = set(
        session.execute(text("SELECT id FROM audit_events")).scalars().all()
    )
    ledger_before = session.execute(
        text("SELECT count(*) FROM fiscal_ledger_entries WHERE trace_id = 'old-trace'")
    ).scalar_one()

    accounts.login(client, accounts.OPERATOR_EMAIL, accounts.OPERATOR_PASSWORD)
    purged = client.post("/platform/v1/retention/purge")
    assert purged.status_code == 200, purged.text
    assert purged.json()["archived_snapshots"] >= 1

    begin_platform(session, break_glass=True)
    gone = session.execute(
        text("SELECT count(*) FROM execution_snapshots WHERE id = :id"),
        {"id": snapshot_id},
    ).scalar_one()
    assert int(gone) == 0
    archived = session.execute(
        text(
            "SELECT count(*) FROM retention_archives "
            "WHERE source_table = 'execution_snapshots' AND source_id = :id"
        ),
        {"id": snapshot_id},
    ).scalar_one()
    assert int(archived) == 1
    ledger_after = session.execute(
        text("SELECT count(*) FROM fiscal_ledger_entries WHERE trace_id = 'old-trace'")
    ).scalar_one()
    assert int(ledger_after) == int(ledger_before)
    audit_after = set(session.execute(text("SELECT id FROM audit_events")).scalars().all())
    assert audit_before <= audit_after
