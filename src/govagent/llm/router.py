import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from govagent.llm.base import BaseLLMClient, LLMRequest, LLMResponse

logger = logging.getLogger("govagent.llm.router")

class RoutingMode(str, Enum):
    LOCAL_ONLY = "LOCAL_ONLY"
    CLOUD_ONLY = "CLOUD_ONLY"
    HYBRID = "HYBRID"

class RoutingRule(BaseModel):
    condition_key: str          # e.g., "contains_pii", "tool_complexity"
    expected_value: Any
    target_provider: str        # e.g., "local_ollama", "cloud_anthropic"

class RouterConfig(BaseModel):
    routing_mode: RoutingMode = RoutingMode.LOCAL_ONLY  # Defensively default to most secure
    default_provider: str
    rules: list[RoutingRule] = Field(default_factory=list)

class PolicyBasedRouter:
    """
    Environmental Traffic Cop. Adapts dynamically to isolated on-prem, 
    pure-cloud SaaS, or complex hybrid enterprise architectures with explicit failover handling.
    """
    def __init__(self, clients: dict[str, BaseLLMClient], config: RouterConfig):
        self.clients = clients
        self.config = config
        
        # Guard against misconfigured infrastructure profiles during server bootstrap
        if self.config.default_provider not in self.clients:
            raise ValueError(
                f"🛑 GOVERNANCE CRASH: Router misconfiguration. The default provider "
                f"'{self.config.default_provider}' requested by the policy was not loaded. "
                f"Available clients: {list(self.clients.keys())}"
            )

    def determine_target(self, context_metadata: dict[str, Any]) -> str:
        # Enforce structural environment containment first
        if self.config.routing_mode == RoutingMode.LOCAL_ONLY:
            return self.config.default_provider
            
        if self.config.routing_mode == RoutingMode.CLOUD_ONLY:
            return self.config.default_provider

        # Process conditional logic ONLY when operating in a hybrid deployment profile
        if self.config.routing_mode == RoutingMode.HYBRID:
            for rule in self.config.rules:
                if context_metadata.get(rule.condition_key) == rule.expected_value:
                    target = rule.target_provider
                    
                    # 🔍 RUNTIME FAILOVER PROTECTION
                    if target not in self.clients:
                        logger.error(
                            f"⚠️ GOVERNANCE ALERT: Policy requested target provider '{target}', "
                            f"but that client wrapper instance is unmapped or missing credentials. "
                            f"Falling back to verified default fallback: '{self.config.default_provider}'."
                        )
                        return self.config.default_provider
                        
                    return target
                        
        return self.config.default_provider

    async def route_and_generate(self, request: LLMRequest, context_metadata: dict[str, Any]) -> LLMResponse:
        target_provider = self.determine_target(context_metadata)
        selected_client = self.clients[target_provider]
        return await selected_client.generate(request)