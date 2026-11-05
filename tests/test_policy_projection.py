from govagent.guards.circuit_breaker import CircuitBreaker, GovernanceViolation
from govagent.policy import Policy
from govagent.context import reset_fiscal_ledger, update_shared_spend


def test_nested_fiscal_and_alignment_are_projected():
    policy = Policy(
        {
            "metadata": {"agent_name": "Projected"},
            "fiscal_governance": {
                "global_limits": {"daily_budget_usd": 100.0, "recursive_tco_limit": 500.0}
            },
            "alignment": {
                "mission_statement": "Protect the patient.",
                "prohibited_strategies": ["Share raw charts."],
                "min_similarity_score": 0.85,
            },
        }
    )
    assert policy.global_limits["daily_budget_usd"] == 100.0
    assert policy.global_limits["recursive_tco_ceiling"] == 500.0
    assert policy.alignment["mission_statement"] == "Protect the patient."
    assert policy.alignment["min_similarity_score"] == 0.85

    reset_fiscal_ledger()
    update_shared_spend(0.0)
    breaker = CircuitBreaker(policy, semantic_guard=None)
    breaker.check_financial_risk(90.0)
    try:
        breaker.check_financial_risk(150.0)
        raise AssertionError("projected daily ceiling was not enforced")
    except GovernanceViolation as exc:
        assert "RECURSIVE TCO REJECT" in str(exc)


def test_top_level_global_limits_override_nested_keys():
    policy = Policy(
        {
            "metadata": {"agent_name": "Override"},
            "global_limits": {"daily_budget_usd": 7},
            "fiscal_governance": {
                "global_limits": {"daily_budget_usd": 100, "recursive_tco_limit": 40}
            },
        }
    )
    assert policy.global_limits["daily_budget_usd"] == 7
    assert policy.global_limits["recursive_tco_ceiling"] == 40


def test_yaml_without_nested_fiscal_keeps_the_code_default():
    policy = Policy({"metadata": {"agent_name": "Plain"}})
    assert policy.global_limits["daily_budget_usd"] == 10.0
    assert policy.alignment == {}
