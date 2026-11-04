import json
import logging
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field

logger = logging.getLogger("govagent.governance.meta")

class PolicyAmendmentProposal(BaseModel):
    """
    Type-safe legislative snapshot defining a proposed policy modification.
    """
    type: str = "POLICY_AMENDMENT_PROPOSAL"
    version: str = "1.0.0"
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    reason: str
    target_policy: str
    metric_breached: str
    current_limit: float
    proposed_limit: float
    impact_assessment: str

class MetaGovernor:
    """
    v1.0.0 Optimization Layer.
    Ingests Article 12 forensic logs to diagnose systemic friction 
    and autonomously design policy amendment proposals for board sign-off.
    """
    def __init__(self, log_path: str = "logs/audit_trail.jsonl", friction_threshold: int = 3):
        self.log_path = Path(log_path)
        self.friction_threshold = friction_threshold

    def analyze_friction(self) -> Dict[str, Any]:
        """
        Scans the active audit log ledger for Recursive TCO block signatures.
        """
        if not self.log_path.exists():
            logger.info(f"MetaGovernor: Path {self.log_path} not found. System running optimally.")
            return {"status": "OPTIMAL", "reason": "No forensic data available for ingestion."}

        rejections = []
        try:
            # Enforce strict UTF-8 boundaries during stream reads to ensure Windows environment safety
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    
                    status_str = entry.get("status", "").upper()
                    if "REJECT" in status_str or "BLOCKED" in status_str:
                        if "TCO" in status_str or "FISCAL" in status_str:
                            rejections.append(entry)
        except Exception as e:
            logger.error(f"MetaGovernor: Fatal ledger ingestion error: {str(e)}")
            return {"status": "ERROR", "reason": f"Audit ingestion fault: {str(e)}"}

        if len(rejections) >= self.friction_threshold:
            logger.warning(f"MetaGovernor: Systemic friction threshold breached ({len(rejections)} blocks detected). Generating legislation.")
            proposal = self._draft_amendment(rejections)
            return proposal.model_dump()
        
        return {
            "status": "OPTIMAL", 
            "reason": f"Friction levels within tolerance ({len(rejections)} / {self.friction_threshold} blocks recorded)."
        }

    def _draft_amendment(self, rejections: List[Dict]) -> PolicyAmendmentProposal:
        """
        Compiles structural log traces to craft a precise policy update proposal.
        """
        latest_block = rejections[-1]
        metrics = latest_block.get("metrics", {})
        
        current_limit = metrics.get("recursive_tco_usd") or latest_block.get("limit") or 500.0
        
        requested_costs = [
            r.get("metrics", {}).get("requested_amount") or 
            r.get("metrics", {}).get("recursive_tco_usd", current_limit) * 1.1 
            for r in rejections
        ]
        
        avg_request = sum(requested_costs) / len(requested_costs)
        proposed_limit = max(current_limit * 1.20, avg_request * 1.10)
        target_policy = latest_block.get("policy_id", "finance_policy.yaml")
        
        return PolicyAmendmentProposal(
            reason=f"Systemic blockage intercepted: {len(rejections)} consecutive TCO budget rejections encountered.",
            target_policy=target_policy,
            metric_breached="recursive_tco_usd",
            current_limit=round(float(current_limit), 4),
            proposed_limit=round(float(proposed_limit), 4),
            impact_assessment="Mitigates operational friction across autonomous sub-agent delegation domains, restoring workspace automation liquidity."
        )