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


def test_registry_alignment_and_oversight_are_projected():
    policy = Policy(
        {
            "metadata": {"agent_name": "Aligned"},
            "registry_alignment": {
                "allowed_tools": ["execute_financial_transaction", "audit_transaction_logs"],
                "high_risk_tools": ["execute_financial_transaction"],
            },
            "oversight": {
                "judiciary": {
                    "high_risk_protocol": {"min_approvals": 2, "quorum_size": 3, "timeout_seconds": 3600}
                },
                "privacy": {"target_entities": ["CREDIT_CARD"]},
            },
        }
    )
    assert policy.allowed_tools == [
        "execute_financial_transaction",
        "audit_transaction_logs",
    ]
    assert policy.is_high_risk("execute_financial_transaction") is True
    assert policy.is_high_risk("audit_transaction_logs") is False
    assert policy.oversight["judiciary"]["high_risk_protocol"]["min_approvals"] == 2
    assert policy.judiciary_settings["high_risk_protocol"]["min_approvals"] == 2
    assert policy.oversight["privacy"]["target_entities"] == ["CREDIT_CARD"]


def test_top_level_tools_override_registry_alignment_risk():
    policy = Policy(
        {
            "registry_alignment": {
                "allowed_tools": ["execute_financial_transaction"],
                "high_risk_tools": ["execute_financial_transaction"],
            },
            "tools": [
                {"name": "execute_financial_transaction", "risk_level": "low", "require_human_approval": False}
            ],
        }
    )
    assert policy.allowed_tools == ["execute_financial_transaction"]
    assert policy.is_high_risk("execute_financial_transaction") is False


def test_finance_yaml_allow_list_and_high_risk():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "policies" / "finance_policy.yaml"
    policy = Policy.from_yaml(str(path))
    assert "execute_financial_transaction" in policy.allowed_tools
    assert policy.is_high_risk("execute_financial_transaction") is True
    assert policy.judiciary_settings.get("high_risk_protocol", {}).get("min_approvals") == 2


def test_transaction_ceiling_is_enforced():
    policy = Policy(
        {
            "metadata": {"agent_name": "Caps"},
            "fiscal_governance": {
                "global_limits": {
                    "daily_budget_usd": 1000.0,
                    "recursive_tco_limit": 1000.0,
                    "transaction_ceiling": 50.0,
                }
            },
        }
    )
    reset_fiscal_ledger()
    breaker = CircuitBreaker(policy, semantic_guard=None)
    breaker.check_transaction_limit(40.0)
    try:
        breaker.check_transaction_limit(51.0)
        raise AssertionError("transaction ceiling was not enforced")
    except GovernanceViolation as exc:
        assert "TRANSACTION CEILING" in str(exc)
