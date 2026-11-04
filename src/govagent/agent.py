import os
import logging
from typing import List, Optional, Any, Dict
from pydantic import ValidationError
from govagent.policy import Policy
from govagent.guards import CircuitBreaker, GovernanceViolation, SemanticGuard
from govagent.telemetry import TelemetryManager
from govagent.hitl import HITLManager, SlackJudiciaryAdapter
from govagent.context import set_current_agent, reset_current_agent
from govagent.registry import registry, ExecutionSnapshot  
from govagent.governance.meta import MetaGovernor
from govagent.llm.base import LLMRequest

logger = logging.getLogger("govagent.agent")

class ExecutiveAgent:
    def __init__(
        self,
        persona: str,
        policy: Policy,
        router: Any,  # Sovereign Routing Bus injected cleanly
        telemetry: Optional[TelemetryManager] = None,
        hitl_manager: Optional[HITLManager] = None
    ):
        self.persona = persona
        self.policy = policy
        self.router = router  # Environmental Router Configuration
        
        # Initialize the Alignment Judge
        align_config = getattr(policy, 'alignment', {})
        self.semantic_guard = SemanticGuard(
            mission=align_config.get('mission_statement', ""),
            prohibited=align_config.get('prohibited_strategies', []),
            threshold=align_config.get('min_similarity_score', 0.85)
        )

        # Inject Pillars into the CircuitBreaker
        self.guard = CircuitBreaker(policy, self.semantic_guard) 
        self.telemetry = telemetry or TelemetryManager()
        self.hitl = hitl_manager or HITLManager()
        
    @classmethod
    def bootstrap(cls, policy_path: str, router_client: Any, slack_channel: Optional[str] = None):
        """Institutional Factory: Fully pluggable Enterprise Setup."""
        policy = Policy.from_yaml(policy_path)
        adapter = None
        if slack_channel:
            adapter = SlackJudiciaryAdapter(
                bot_token=os.getenv("SLACK_BOT_TOKEN"),
                app_token=os.getenv("SLACK_APP_TOKEN"),
                channel_id=slack_channel
            )
            adapter.start()
            
        return cls(
            persona=policy.metadata.get("agent_name", "ExecutiveAgent"),
            policy=policy,
            router=router_client,
            hitl_manager=HITLManager(adapter=adapter)
        )

    async def evaluate(self, guards: List[str], intent: dict = None, value: float = 0.0):
        """Modular Triage with Federated M-of-N support."""
        if not self.telemetry.current_session:
            self.telemetry.start_trace(self.persona, "Internal Evaluation")
        
        # SEMANTIC ALIGNMENT
        if intent and intent.get("thought"):
            await self.guard.evaluate(
                tool_name=intent.get("action", "unknown"), 
                args=intent.get("params", {}), 
                thought=intent["thought"]
            )

        # FISCAL SOVEREIGNTY
        if "fiscal" in guards:
            current_total = self.telemetry.current_session.estimated_cost_usd + value
            self.guard.check_financial_risk(current_total)

        # FEDERATED JUDICIARY (M-of-N)
        if "judiciary" in guards and intent and intent.get("action") != "complete":
            if self.policy.is_high_risk(intent["action"]):
                judiciary_cfg = getattr(self.policy, 'oversight', {}).get('judiciary', {})
                tool_cfg = judiciary_cfg.get('high_risk_protocol', {})
                
                approved = await self.hitl.secure_approval(
                    agent_id=self.persona,
                    reason=f"Judiciary Authorization Required: {intent['action']}",
                    context=intent,
                    triggered_by="judiciary",
                    config=tool_cfg
                )
                if not approved:
                    raise GovernanceViolation(f"Human Judiciary denied request for {intent['action']}")
        
        return True

    async def execute(self, task: str) -> ExecutionSnapshot:
        """Governed Reasoning Loop driven dynamically by YAML Infrastructure Parameters."""
        token = set_current_agent(self)
        sanitized_task = self.guard.privacy.redact_task(task)  # Article 9 Compliance
        
        self.telemetry.start_trace(self.persona, sanitized_task)
        current_step, total_tokens = 0, 0
        last_active_model = "None Assigned"
        
        try:
            while current_step < 10:
                # Package the standardized generation contract
                request_payload = LLMRequest(
                    prompt=sanitized_task,
                    system_instruction=f"You are a {self.persona}. Corporate Policy Boundaries apply.",
                    temperature=0.0
                )

                # Extract context metadata live from the parsed YAML properties
                context_metadata = {
                    "routing_mode": getattr(self.policy, "routing_mode", "LOCAL_ONLY"),
                    "default_provider": getattr(self.policy, "default_provider", "local_ollama"),
                    "agent_risk_profile": self.policy.metadata.get("risk_profile", "standard"),
                    "contains_pii": getattr(self.guard.privacy, "last_execution_had_pii", False),
                    "current_step": current_step
                }

                # Safe fallback if router is not hydrated during unit testing context
                if self.router is None:
                    return await self._finalize("success", "Task complete (Test Sandbox Mode).", total_tokens, model_node="mock_sandbox")

                # Route & Generate via the pluggable routing bus
                response = await self.router.route_and_generate(request_payload, context_metadata)
                
                # Update tracking parameters with current runtime node snapshot
                if hasattr(response, 'selected_model'):
                    last_active_model = response.selected_model
                elif "local_ollama" in context_metadata["default_provider"]:
                    last_active_model = "local_ollama"

                tokens_used = response.raw_usage.get("total_tokens", 0)
                cost_incurred = response.raw_usage.get("estimated_cost_usd", 0.0)
                total_tokens += tokens_used

                if response.tool_calls:
                    tool_call = response.tool_calls[0]
                    intent = {
                        "thought": response.text[:250] + "...",
                        "action": tool_call.get("name"),
                        "params": tool_call.get("args", {}),
                        "full_audit_log": response.text
                    }
                else:
                    intent = {
                        "thought": response.text[:250] + "...",
                        "action": "complete" if "complete" in response.text.lower() else None,
                        "params": {},
                        "full_audit_log": response.text
                    }
                
                if not intent.get("action") or intent["action"] == "complete":
                    return await self._finalize("success", "Task complete.", total_tokens, model_node=last_active_model)

                # STAGE 1: Schema Validation
                # 3.0.2 returns a dict. Unpublished builds returned True. Accept both.
                try:
                    validation = registry.validate_intent_schema(
                        intent.get("action"),
                        intent.get("params", {}),
                    )
                except (ValidationError, ValueError, TypeError) as schema_error:
                    return await self._finalize(
                        "blocked",
                        f"Schema Violation: {schema_error}",
                        total_tokens,
                        model_node=last_active_model,
                    )
                if isinstance(validation, dict):
                    if not validation.get("valid", False):
                        return await self._finalize(
                            "blocked",
                            f"Schema Violation: {validation.get('error')}",
                            total_tokens,
                            model_node=last_active_model,
                        )
                elif validation is not True:
                    return await self._finalize(
                        "blocked",
                        "Schema Violation",
                        total_tokens,
                        model_node=last_active_model,
                    )

                # STAGE 2: Evaluation (Circuit Breaker)
                await self.evaluate(guards=["fiscal", "judiciary"], intent=intent, value=cost_incurred)

                # STAGE 3: Action Execution
                self.telemetry.current_session.estimated_cost_usd += cost_incurred
                result = await self.perform_action(intent.get("action"), intent.get("params", {}))
                self.telemetry.log_step(intent.get("thought", ""), intent.get("action"), str(result))
                
                if intent.get("action") == "execute_financial_transaction":
                    return await self._finalize("success", result, total_tokens, impact=intent["params"].get("amount", 0.0), model_node=last_active_model)
                
                current_step += 1

            return await self._finalize("timeout", "Max steps reached.", total_tokens, model_node=last_active_model)

        except GovernanceViolation as gv:
            return await self._finalize("blocked", str(gv), total_tokens, model_node=last_active_model)
        except Exception as e:
            return await self._finalize("error", str(e), total_tokens, model_node=last_active_model)
        finally:
            reset_current_agent(token)

    async def _finalize(self, status: str, output: Any, tokens: int, impact: float = 0.0, model_node: str = "None Assigned") -> ExecutionSnapshot:
        """Institutional Finalization: Ensures proper metric mapping."""
        await self.telemetry.finalize(status=status, tokens=tokens)
        
        return ExecutionSnapshot(
            trace_id=self.telemetry.current_session.trace_id,
            status=status,
            output=output,
            metrics={
                "fiscal_impact": impact, 
                "total_tokens": tokens,
                "recursive_tco_usd": self.telemetry.current_session.estimated_cost_usd,
                "selected_model": model_node
            },
            parent_trace_id=self.telemetry.current_session.parent_trace_id
        )

    async def perform_action(self, action: str, params: dict) -> str:
        if not action or action == "complete": return "Task complete."
        return f"Action {action} executed with params {params}"
    
    async def post_session_cleanup(self):
        """Executes institutional governance verification post-transaction lifecycle."""
        governor = MetaGovernor(log_path="logs/audit_trail.jsonl", friction_threshold=3)
        analysis_result = governor.analyze_friction()
        
        if analysis_result.get("type") == "POLICY_AMENDMENT_PROPOSALS" or analysis_result.get("status") != "OPTIMAL":
            if "proposed_limit" in analysis_result:
                logger.info("ExecutiveAgent: Escalating policy amendment proposal to Federated Slack Courtroom.")
                
                slack_payload = (
                    f"🚨 *GovAgent Governance Alert: Automated Policy Amendment Proposed*\n"
                    f"• *Reason:* {analysis_result.get('reason', 'Systemic friction detected')}\n"
                    f"• *Target File:* `{analysis_result.get('target_policy', 'policy.yaml')}`\n"
                    f"• *Current Limit:* ${analysis_result.get('current_limit', 0.0):.4f}\n"
                    f"• *Proposed Ceiling:* *${analysis_result.get('proposed_limit', 0.0):.4f}*\n"
                    f"• *Impact:* {analysis_result.get('impact_assessment', 'N/A')}\n"
                    f"👉 _Reply with 'APPROVE AMENDMENT' to apply this change to the root policy layer._"
                )
                
                if hasattr(self, 'hitl') and self.hitl.adapter:
                    await self.hitl.adapter.send_message(text=slack_payload)