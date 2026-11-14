import logging
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("govagent.hitl.manager")

class ApprovalStatus(Enum):
    PENDING = "pending"
    QUORUM_MET = "approved" 
    REJECTED = "rejected"

class ApprovalRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    reason: str 
    action_type: str = "policy"  
    context: Any 
    status: ApprovalStatus = ApprovalStatus.PENDING
    
    # Upgraded v0.6.0 Governance Parameters
    min_approvals: int = 1         # Maintained for v0.5.1 simple threshold fallback
    required_score: float = 1.0    # Target accumulated role weight threshold
    risk_tier: str = "TIER_1_OPERATIONAL"
    approvers: set[str] = Field(default_factory=set)  # Format: "user_id|role|weight"
    message_ts: str | None = None 

class HITLManager:
    """
    v0.6.0 Federated Judiciary Control Unit.
    Centralizes risk-tier evaluation and role-based signature tallies.
    """
    def __init__(self, adapter=None):
        from .adapters import CLIAdapter
        self.adapter = adapter or CLIAdapter()
        self.history = []
        
        # Corporate hierarchy authority weights
        self.voter_weights = {
            "C-Suite": 3.0,
            "Director": 2.0,
            "Auditor": 1.5,
            "Lead": 1.0,
            "Clerk": 0.5
        }

    async def secure_approval(
        self, 
        agent_id: str, 
        reason: str, 
        context: dict | None = None, 
        triggered_by: str = "policy", 
        config: dict | None = None            
    ) -> bool:
        """
        Orchestrates the asynchronous evaluation process against an escalating risk matrix.
        """
        context_dict = context or {}
        requested_amount = context_dict.get("params", {}).get("amount", 0.0)
        
        # 1. Evaluate Risk Tiers & Define Corporate Score Constraints
        if requested_amount >= 5000.0:
            required_score = 4.0
            risk_tier = "TIER_3_CRITICAL"
        elif requested_amount >= 1000.0:
            required_score = 2.5
            risk_tier = "TIER_2_HIGH"
        else:
            required_score = 1.0
            risk_tier = "TIER_1_OPERATIONAL"

        logger.warning(f"HITLManager: Evaluating action under {risk_tier}. Required Score: {required_score}")

        # 2. Build the structural Request model
        request = ApprovalRequest(
            agent_id=agent_id,
            reason=reason,
            action_type=triggered_by, 
            context=context_dict,
            required_score=required_score,
            risk_tier=risk_tier,
            min_approvals=config.get("min_approvals", 1) if config else 1
        )
        
        # 3. Dispatch to the active adapter channel
        raw_responses = await self.adapter.notify(request)
        
        # 4. Process the Tally Verification
        if isinstance(raw_responses, bool):
            # Fallback alignment for legacy v0.5.1 Boolean adapters
            is_approved = raw_responses
        else:
            # v0.6.0 Consolidated Weight Accumulator Engine
            accumulated_score = 0.0
            veto_triggered = False
            
            for resp in raw_responses:
                if resp.get("decision") == "REJECTED":
                    veto_triggered = True
                    break
                if resp.get("decision") == "APPROVED":
                    role = resp.get("voter_role", "Lead")
                    accumulated_score += self.voter_weights.get(role, 1.0)
            
            is_approved = accumulated_score >= required_score and not veto_triggered
        
        request.status = ApprovalStatus.QUORUM_MET if is_approved else ApprovalStatus.REJECTED
        self.history.append(request)
        
        return is_approved