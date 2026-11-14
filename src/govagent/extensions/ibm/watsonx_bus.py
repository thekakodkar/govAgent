# src/govagent/extensions/ibm/watsonx_bus.py
import logging
from typing import Any

from govagent.context.fiscal_ledger import update_shared_spend

logger = logging.getLogger("govagent.extensions.ibm.watsonx_bus")

class WatsonxOrchestrateBusSync:
    """
    Synchronizes runtime transaction costs from watsonx Orchestrate supervisors (v3.0.0).
    Updates thread-isolated ledger states to maintain aggregate TCO ceiling compliance.
    """
    def __init__(self, fallback_rate_per_token: float = 0.00002):
        self.fallback_rate = fallback_rate_per_token

    def process_watsonx_generation_metric(self, response_payload: dict[str, Any]) -> float:
        """
        Extracts token usage metrics from standard watsonx/IBM Granite execution tokens 
        and updates the global atomic fiscal ledger snapshot.
        """
        usage = response_payload.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = prompt_tokens + completion_tokens
        
        model_name = response_payload.get("model_id", "ibm/granite-13b-instruct")
        
        # Safe Dynamic Resolution: Check for pricing matrix availability at runtime
        try:
            from govagent import pricing
            if hasattr(pricing, 'calculate_cost'):
                calculated_cost = pricing.calculate_cost(model_name, prompt_tokens, completion_tokens)
            else:
                raise AttributeError
        except (ImportError, AttributeError):
            # Deterministic calculation fallback matching structural baseline parameters
            calculated_cost = round(total_tokens * self.fallback_rate, 6)
            
        logger.info(f"🏢 watsonx Cost Sync: Model '{model_name}' consumed {total_tokens} total tokens. Calculated Cost: ${calculated_cost}")
        
        # Atomically update global ledger tracking values
        update_shared_spend(calculated_cost)
        
        return calculated_cost