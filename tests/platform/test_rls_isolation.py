"""Row-level security against real Postgres, connected as govagent_app."""

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from govagent_platform.db import begin_tenant
from govagent_platform.domain.models import Agent, AuditEvent, ExecutionSnapshotRow, TenantPolicy


def _policy(session, world, tenant, name: str) -> TenantPolicy:
    row = TenantPolicy(
        tenant_id=tenant.id,
        name=name,
        document={"metadata": {"agent_name": name}},
        checksum="checksum",
        status="draft",
        created_by=world.operator.id,
    )
    session.add(row)
    session.flush()
    return row


def test_alpha_selects_do_not_return_beta_rows(session, world):
    alpha_id = world.alpha.id
    beta_id = world.beta.id
    operator_id = world.operator.id
    alpha_admin_id = world.alpha_admin.id
    beta_admin_id = world.beta_admin.id

    begin_tenant(session, alpha_id)
    alpha_policy = _policy(session, world, world.alpha, "alpha-policy")
    session.add(
        Agent(
            tenant_id=alpha_id,
            name="alpha-agent",
            persona="Alpha",
            policy_id=alpha_policy.id,
            status="active",
        )
    )
    session.add(
        ExecutionSnapshotRow(
            tenant_id=alpha_id,
            trace_id="trace-alpha",
            status="success",
            task_input="alpha task",
        )
    )
    session.add(
        AuditEvent(
            tenant_id=alpha_id,
            actor_scope="tenant",
            actor_id=alpha_admin_id,
            action="tenant.note",
            target_type="tenant",
            target_id=str(alpha_id),
        )
    )
    session.flush()

    begin_tenant(session, beta_id)
    beta_policy = _policy(session, world, world.beta, "beta-policy")
    session.add(
        Agent(
            tenant_id=beta_id,
            name="beta-agent",
            persona="Beta",
            policy_id=beta_policy.id,
            status="active",
        )
    )
    session.add(
        ExecutionSnapshotRow(
            tenant_id=beta_id,
            trace_id="trace-beta",
            status="success",
            task_input="beta secret task",
        )
    )
    session.add(
        AuditEvent(
            tenant_id=beta_id,
            actor_scope="tenant",
            actor_id=beta_admin_id,
            action="tenant.note",
            target_type="tenant",
            target_id=str(beta_id),
        )
    )
    session.flush()

    begin_tenant(session, alpha_id)

    def visible(table: str) -> list:
        return list(session.execute(text(f"SELECT tenant_id FROM {table}")).scalars().all())

    for table in ("tenant_policies", "agents", "audit_events", "execution_snapshots"):
        rows = visible(table)
        assert rows, table
        assert set(rows) == {alpha_id}, table

    leaked = session.execute(text("SELECT task_input FROM execution_snapshots")).scalars().all()
    assert "beta secret task" not in leaked

    with pytest_raises_rls():
        with session.begin_nested():
            session.add(
                TenantPolicy(
                    tenant_id=beta_id,
                    name="smuggled",
                    document={"metadata": {"agent_name": "smuggled"}},
                    checksum="checksum",
                    status="draft",
                    created_by=operator_id,
                )
            )
            session.flush()


class pytest_raises_rls:
    """Assert the insert dies because WITH CHECK rejects the other tenant."""

    def __enter__(self):
        self._ctx = __import__("pytest").raises(DBAPIError)
        self._inner = self._ctx.__enter__()
        return self._inner

    def __exit__(self, exc_type, exc, tb):
        suppressed = self._ctx.__exit__(exc_type, exc, tb)
        if suppressed:
            message = str(self._inner.value).lower()
            assert "row-level security" in message
        return suppressed
