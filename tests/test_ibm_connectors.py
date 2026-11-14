# tests/test_ibm_connectors.py
import pytest
from unittest.mock import MagicMock
from govagent.extensions.ibm.bob_mcp_proxy import BobMCPProxyGateway
from govagent.extensions.ibm.watsonx_bus import WatsonxOrchestrateBusSync
from govagent.guards.circuit_breaker import GovernanceViolation
from govagent.context.fiscal_ledger import reset_fiscal_ledger, get_shared_fiscal_metrics

@pytest.mark.asyncio
async def test_ibm_bob_mcp_proxy_semantic_intercept():
    """Verifies that the MCP gateway successfully blocks prohibited tool executions."""
    # 1. Setup mock guard parameters returning a 0.0 hard-stop violation score
    mock_semantic_guard = MagicMock()
    mock_semantic_guard.evaluate_alignment.return_value = 0.0
    
    proxy = BobMCPProxyGateway(semantic_guard=mock_semantic_guard)
    
    # Target function simulating a backend transaction tool
    def sample_tool(disbursement_target: str):
        return "Disbursement Successful"
        
    governed_tool = proxy.govern_mcp_tool("authorize_payout", sample_tool)
    
    # 2. Execution Assert: Must raise GovernanceViolation circuit breaker exception
    with pytest.raises(GovernanceViolation) as excinfo:
        await governed_tool(disbursement_target="unauthorized_offshore_entity")
        
    assert "IBM BOB MCP PROXY REJECT" in str(excinfo.value)

def test_watsonx_orchestrate_bus_spend_sync():
    """Verifies that incoming watsonx token payloads are processed into the atomic ledger."""
    reset_fiscal_ledger()
    sync_bus = WatsonxOrchestrateBusSync(fallback_rate_per_token=0.0001)
    
    # Simulated IBM Granite orchestration token response block
    mock_response = {
        "model_id": "ibm/granite-20b-code",
        "usage": {
            "prompt_tokens": 150,
            "completion_tokens": 50
        }
    }
    
    # Process 200 total tokens * 0.0001 cost rate = 0.02 spend metric
    cost = sync_bus.process_watsonx_generation_metric(mock_response)
    assert cost == 0.02
    
    metrics = get_shared_fiscal_metrics()
    assert metrics["cumulative_spend"] == 0.02
    assert metrics["task_counter"] == 1.0

@pytest.mark.asyncio
async def test_ibm_bob_mcp_proxy_uses_privacy_redact_task():
    from govagent.guards.privacy import PrivacyGuard
    from govagent.policy import Policy

    guard = PrivacyGuard(Policy({"metadata": {"agent_name": "P"}}))
    proxy = BobMCPProxyGateway(privacy_guard=guard)

    def sample_tool(note: str):
        return "ok"

    governed = proxy.govern_mcp_tool("note_tool", sample_tool)
    result = await governed(note="Contact Jane Doe at 123 Main St")
    assert result == "ok"
    assert guard.last_execution_had_pii is True
