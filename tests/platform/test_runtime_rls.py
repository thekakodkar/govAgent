from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from govagent_platform.db import begin_tenant
from govagent_platform.domain.models import ExecutionSnapshotRow
from tests.platform import accounts
from tests.platform.runtime_support import activate_tenant_policy, make_agent, script_task


def test_beta_cannot_read_alpha_runtime_rows(client):
    policy_id = activate_tenant_policy(client, daily=100)
    agent_id = make_agent(
        client,
        policy_id,
        "record_note",
        requires_approval=False,
        param_schema={"required": []},
    )
    created = client.post("/tenant/v1/tools", json={"name": "alpha-only-tool", "description": "secret"})
    assert created.status_code == 201, created.text
    evaluated = client.post(
        f"/tenant/v1/agents/{agent_id}/evaluate",
        json={"task": script_task("record_note")},
    )
    assert evaluated.status_code == 200, evaluated.text
    trace_id = evaluated.json()["trace_id"]

    accounts.login(client, accounts.BETA_ADMIN_EMAIL, accounts.BETA_ADMIN_PASSWORD)
    hidden_execution = client.get(f"/tenant/v1/executions/{trace_id}")
    assert hidden_execution.status_code == 404
    visible_tools = client.get("/tenant/v1/tools")
    assert visible_tools.status_code == 200
    assert "alpha-only-tool" not in visible_tools.text
    assert "record_note" not in visible_tools.text


def test_cross_tenant_execution_insert_fails_with_check(session, world):
    begin_tenant(session, world.alpha.id)
    with pytest_rls():
        with session.begin_nested():
            session.add(
                ExecutionSnapshotRow(
                    tenant_id=world.beta.id,
                    trace_id="smuggled",
                    status="success",
                    task_input="beta secret",
                )
            )
            session.flush()


class pytest_rls:
    def __enter__(self):
        import pytest

        self._ctx = pytest.raises(DBAPIError)
        self._inner = self._ctx.__enter__()
        return self._inner

    def __exit__(self, exc_type, exc, tb):
        suppressed = self._ctx.__exit__(exc_type, exc, tb)
        if suppressed:
            assert "row-level security" in str(self._inner.value).lower()
        return suppressed
