"""Tenant tool maps stay off the process-global registry, including under overlap."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

from govagent.registry import registry
from govagent.registry.manager import GlobalRegistry

from govagent_platform.runtime.agent import TenantExecutiveAgent
from govagent_platform.runtime.llm import build_router
from govagent_platform.runtime.policy_binding import hydrate_policy
from govagent_platform.runtime.validation import overlap_hook, validate_tenant_intent
from tests.platform.runtime_support import script_task


class _Exporter:
    def __init__(self):
        self.incremental_steps: list[float] = []
        self.tokens = 0
        self.model_name = None
        self.approval_request_id = None

    async def export(self, snapshot):
        return True


def _row(name: str):
    return SimpleNamespace(
        name=name,
        description=name,
        risk_level="low",
        requires_approval=False,
        param_schema={"required": []},
        oci_repository=None,
        artifact_digest=None,
    )


def _agent(policy, tool_map):
    return TenantExecutiveAgent(
        "Clerk",
        policy,
        build_router(policy),
        tool_map=tool_map,
        exporter=_Exporter(),
        all_time=0.0,
        today=0.0,
        on_pending=lambda **kwargs: "unused",
        month_spend=0.0,
        monthly_ceiling=1000.0,
    )


def test_concurrent_tenant_evaluations_cannot_see_each_other():
    before = dict(registry.tools)
    tools_id = id(registry.tools)
    policy = hydrate_policy(
        {
            "metadata": {"agent_name": "Isolation"},
            "infrastructure": {"routing_mode": "LOCAL_ONLY", "default_provider": "scripted"},
            "fiscal_governance": {"global_limits": {"daily_budget_usd": 100, "recursive_tco_limit": 1000}},
        }
    )
    alpha_map = {"alpha_only": _row("alpha_only")}
    beta_map = {"beta_only": _row("beta_only")}
    alpha = _agent(policy, alpha_map)
    beta = _agent(policy, beta_map)

    seen: list[set[str]] = []
    registry_during: list[set[str]] = []
    barrier = threading.Barrier(2)

    def hook(tool_map):
        seen.append(set(tool_map))
        registry_during.append(set(registry.tools))
        barrier.wait(timeout=10)

    def run(agent, task, slot, results):
        token = overlap_hook.set(hook)
        try:
            results[slot] = asyncio.run(agent.execute(script_task(task)))
        finally:
            overlap_hook.reset(token)

    results: list = [None, None]
    threads = [
        threading.Thread(target=run, args=(alpha, "alpha_only", 0, results)),
        threading.Thread(target=run, args=(beta, "beta_only", 1, results)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive()

    assert {name for names in seen for name in names} == {"alpha_only", "beta_only"}
    assert all(names == set() or names <= set(before) for names in registry_during)
    assert all("alpha_only" not in names and "beta_only" not in names for names in registry_during)
    assert results[0].status == "success"
    assert results[1].status == "success"
    assert set(registry.tools) == set(before)
    assert registry.tools == before
    assert id(registry.tools) == tools_id
    assert registry.tools is GlobalRegistry().tools

    missing = validate_tenant_intent(alpha_map, "beta_only", {})
    assert missing["valid"] is False
    assert missing["error"] == "Tool not legislated"
    assert set(registry.tools) == set(before)
