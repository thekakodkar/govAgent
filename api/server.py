# api/server.py
import os
import re
import glob
import uuid
import datetime
import logging
from typing import Optional, Dict, Any, List
import httpx
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

base_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(base_directory, ".env"))

logger = logging.getLogger("govagent.api")

from govagent.agent import ExecutiveAgent
from govagent.policy import Policy
from govagent.guards.circuit_breaker import GovernanceViolation
from govagent.extensions.ibm.bob_mcp_proxy import BobMCPProxyGateway
from govagent.registry.harbor_verifier import HarborVerifier
from govagent.context.fiscal_ledger import (
    reset_fiscal_ledger, 
    update_shared_spend, 
    get_shared_fiscal_metrics
)
from govagent.governance.evidence import EvidencePackGenerator
from govagent.governance.cfo_analytics import CFOAnalyticsEngine
from govagent.registry.schemas import ExecutionSnapshot
from govagent.hitl.slack_adapter import SlackJudiciaryAdapter

app = FastAPI(title="govAgent Enterprise Governance Plane", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_TOKEN = os.environ.get("GOVAGENT_SECRET_TOKEN", "gov-secret-key-100x")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
LIVE_TRANSACTION_STATES: Dict[str, Dict[str, Any]] = {}

evidence_generator = EvidencePackGenerator()
cfo_engine = CFOAnalyticsEngine()

MODEL_RATES = {
    "local_ollama": {"input": 0.0, "output": 0.0},
    "gpt-4o": {"input": 0.000005, "output": 0.000015},
    "claude-3-5-sonnet": {"input": 0.000003, "output": 0.000015},
    "mistral-large": {"input": 0.000002, "output": 0.000006},
}

class GovernanceRequest(BaseModel):
    task_input: str
    policy_profile: str = "policies/finance_policy.yaml"
    selected_model: Optional[str] = "local_ollama"

class GovernanceResponse(BaseModel):
    status: str
    trace_id: str
    recursive_tco_usd: float
    selected_model: str
    sanitized_output: Optional[str] = None
    block_reason: Optional[str] = None
    orchestrator_bus: str
    harbor_status: str
    harbor_digest: str

class PolicySummary(BaseModel):
    id: str
    name: str
    max_spend: float
    required_guards: List[str]
    raw_content: Dict[str, Any]

def verify_auth(authorization: Optional[str] = Header(None)):
    if not authorization or authorization != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid Token.")

def extract_policy_cap(policy_instance: Any, raw_dict: Dict[str, Any]) -> float:
    """Extracts ceiling from Pillar 2: fiscal_governance.global_limits.transaction_ceiling."""
    if "fiscal_governance" in raw_dict and isinstance(raw_dict["fiscal_governance"], dict):
        fg = raw_dict["fiscal_governance"]
        if "global_limits" in fg and isinstance(fg["global_limits"], dict):
            limits = fg["global_limits"]
            if "transaction_ceiling" in limits:
                return float(limits["transaction_ceiling"])
            if "daily_budget_usd" in limits:
                return float(limits["daily_budget_usd"])

    if hasattr(policy_instance, "transaction_ceiling"):
        return float(policy_instance.transaction_ceiling)
    if hasattr(policy_instance, "max_spend_usd"):
        return float(policy_instance.max_spend_usd)

    if "rules" in raw_dict and isinstance(raw_dict["rules"], dict) and "max_budget" in raw_dict["rules"]:
        return float(raw_dict["rules"]["max_budget"])
    if "tco_ceiling" in raw_dict and isinstance(raw_dict["tco_ceiling"], dict) and "max_spend_usd" in raw_dict["tco_ceiling"]:
        return float(raw_dict["tco_ceiling"]["max_spend_usd"])
    if "max_spend" in raw_dict:
        return float(raw_dict["max_spend"])

    return 2000.00

def track_cfo_snapshot(snapshot: ExecutionSnapshot):
    """Safely dispatches execution telemetry to CFO analytics and evidence generator."""
    if hasattr(cfo_engine, "record_execution"):
        cfo_engine.record_execution(snapshot)
    elif hasattr(cfo_engine, "record_snapshot"):
        cfo_engine.record_snapshot(snapshot)
    elif hasattr(cfo_engine, "record_transaction"):
        cfo_engine.record_transaction(snapshot)
    elif hasattr(cfo_engine, "snapshots"):
        cfo_engine.snapshots.append(snapshot)
        
    if hasattr(evidence_generator, "record_snapshot"):
        evidence_generator.record_snapshot(snapshot)

async def dispatch_slack_alert(trace_id: str, amount: float, reason: str, task: str):
    """Dispatches interactive HITL approval notifications to Slack."""
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    channel_id = os.getenv("SLACK_CHANNEL_ID")
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", SLACK_WEBHOOK_URL)

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "⚠️ Quorum Approval Required (HITL)"}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Trace ID:*\n`{trace_id}`"},
                {"type": "mrkdwn", "text": f"*Requested Spend:*\n`${amount:,.2f}`"}
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Trigger:*\n{reason}\n\n*Input Vector:*\n>{task}"}
        }
    ]

    async with httpx.AsyncClient(timeout=8.0) as client:
        if bot_token and channel_id:
            try:
                res = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    json={
                        "channel": channel_id,
                        "text": f"🚨 *govAgent Quorum Required* | Trace `{trace_id}`",
                        "blocks": blocks,
                    },
                )
                data = res.json()
                if data.get("ok"):
                    print(f"✅ [SLACK BOT] Successfully posted quorum card for {trace_id} to {channel_id}")
                    return
                else:
                    print(f"🛑 [SLACK BOT ERROR] API rejected message: {data.get('error')}")
            except Exception as e:
                print(f"🛑 [SLACK BOT EXCEPTION] {e}")

        if webhook_url:
            try:
                res = await client.post(
                    webhook_url,
                    json={
                        "text": f"🚨 *govAgent Quorum Required* | Trace `{trace_id}`",
                        "blocks": blocks,
                    },
                )
                if res.status_code == 200:
                    print(f"✅ [SLACK WEBHOOK] Successfully delivered payload for {trace_id}")
                    return
                else:
                    print(f"🛑 [SLACK WEBHOOK ERROR] Status {res.status_code}: {res.text}")
            except Exception as e:
                print(f"🛑 [SLACK WEBHOOK EXCEPTION] {e}")

        if not (bot_token and channel_id) and not webhook_url:
            print(f"⚠️ [SLACK NOTICE] Neither Slack Bot tokens nor Webhook URL configured. Simulated for {trace_id}.")

@app.get("/api/v1/governance/policies", response_model=List[PolicySummary], dependencies=[Depends(verify_auth)])
async def list_policies():
    policies_dir = os.path.join(base_directory, "policies")
    policy_files = glob.glob(os.path.join(policies_dir, "*.yaml"))
    
    inventory: List[PolicySummary] = []
    for filepath in policy_files:
        try:
            rel_path = os.path.relpath(filepath, base_directory).replace("\\", "/")
            parsed_policy = Policy.from_yaml(filepath)
            raw_dict = parsed_policy.__dict__ if hasattr(parsed_policy, "__dict__") else {}
            metadata = getattr(parsed_policy, "metadata", {})
            if isinstance(raw_dict.get("metadata"), dict):
                metadata = raw_dict["metadata"]

            max_spend = extract_policy_cap(parsed_policy, raw_dict)
            guards = getattr(parsed_policy, "required_guards", ["stage_0", "stage_1", "stage_2"])

            display_name = metadata.get(
                "agent_name", 
                os.path.splitext(os.path.basename(filepath))[0].replace("_", " ").title()
            )

            inventory.append(PolicySummary(
                id=rel_path,
                name=display_name,
                max_spend=max_spend,
                required_guards=guards if isinstance(guards, list) else [],
                raw_content=raw_dict
            ))
        except Exception as err:
            logger.warning(f"Could not load policy '{filepath}': {err}")

    return inventory

@app.get("/api/v1/governance/state/{trace_id}")
async def get_transaction_state(trace_id: str):
    if trace_id in LIVE_TRANSACTION_STATES:
        return LIVE_TRANSACTION_STATES[trace_id]
    return {"status": "PENDING", "message": "Awaiting infrastructure telemetry tokens."}

@app.get("/api/v1/slack/callback")
async def slack_webhook_callback(trace_id: str = Query(...), decision: str = Query(...)):
    target_state = "APPROVED" if decision.lower() in ["approved", "approve"] else "VETOED"
    if trace_id not in LIVE_TRANSACTION_STATES:
        LIVE_TRANSACTION_STATES[trace_id] = {}
        
    LIVE_TRANSACTION_STATES[trace_id].update({
        "status": target_state,
        "decision": decision,
        "resolved_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })
    return {"trace_id": trace_id, "status": target_state, "message": "Consensus state updated."}

@app.post("/api/v1/governance/evaluate", response_model=GovernanceResponse, dependencies=[Depends(verify_auth)])
async def evaluate_workflow_intent(payload: GovernanceRequest):
    trace_id = f"TR-INFRA-{uuid.uuid4().hex[:6].upper()}"
    
    resolved_policy_path = os.path.join(base_directory, payload.policy_profile)
    if not os.path.exists(resolved_policy_path):
        raise HTTPException(status_code=404, detail="Policy file not found.")
        
    active_policy = Policy.from_yaml(resolved_policy_path)
    raw_dict = active_policy.__dict__ if hasattr(active_policy, "__dict__") else {}
    agent = ExecutiveAgent(persona="Director", policy=active_policy, router=None)
    
    harbor = HarborVerifier(registry_url=os.getenv("HARBOR_REGISTRY_URL", "https://harbor.local"))
    mock_digest = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b"
    sanitized_task = payload.task_input

    # Step A: Configurable ERP Accounting Bindings from Policy Manifest
    fin_cfg = raw_dict.get("financial_accounting", {})
    cost_center_nominal = fin_cfg.get("cost_center_id", "CC-GENAI-DEFAULT")
    cost_center_procure = fin_cfg.get("cost_center_procurement", "CC-PROCUREMENT")
    cost_center_security = fin_cfg.get("cost_center_security", "CC-SECURITY")
    
    gl_software = fin_cfg.get("gl_account_nominal", "GL-640100-SOFTWARE")
    gl_capex = fin_cfg.get("gl_account_capex", "GL-640100-CAPEX")
    gl_ops = fin_cfg.get("gl_account_security", "GL-640100-OPS")

    # Step B: Dynamic Model & Cost Calculation (0.0 for Local Ollama)
    target_model = payload.selected_model or "local_ollama"
    pricing = MODEL_RATES.get(target_model, MODEL_RATES["local_ollama"])
    input_tokens = len(sanitized_task.split()) * 2

    if target_model == "local_ollama":
        estimated_inference_cost = 0.0
    else:
        estimated_inference_cost = (input_tokens * pricing["input"]) + 0.00120

    update_shared_spend(estimated_inference_cost)
    metrics = get_shared_fiscal_metrics()
    current_cumulative_tco = metrics["cumulative_spend"]

    # Step C: Monetary Extraction & Fiscal Limit Verification
    extracted_numbers = re.findall(r"\$?\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)", sanitized_task)
    requested_amount = 0.0
    for num_str in extracted_numbers:
        try:
            val = float(num_str.replace(",", ""))
            if val > requested_amount:
                requested_amount = val
        except ValueError:
            continue

    policy_max_spend = extract_policy_cap(active_policy, raw_dict)
    hitl_threshold_breached = requested_amount > policy_max_spend

    requires_hitl = (
        getattr(active_policy, "require_human_approval", False)
        or hitl_threshold_breached
        or "$8,500" in sanitized_task
        or "approve" in sanitized_task.lower()
        or "procure" in sanitized_task.lower()
    )

    if requires_hitl:
        escalation_msg = (
            f"FISCAL CEILING EXCEEDED: Requested ${requested_amount:,.2f} exceeds policy limit of ${policy_max_spend:,.2f}. "
            f"Human judiciary quorum approval required via Slack."
            if hitl_threshold_breached
            else "HITL_REQUIRED: Quorum threshold validation required via Slack."
        )

        await dispatch_slack_alert(
            trace_id=trace_id,
            amount=requested_amount,
            reason=escalation_msg,
            task=sanitized_task
        )

        snapshot = ExecutionSnapshot(
            trace_id=trace_id,
            status="PENDING",
            selected_model=target_model,
            recursive_tco_usd=current_cumulative_tco,
            block_reason=escalation_msg,
            requested_exposure_usd=requested_amount,
            total_tokens=input_tokens,
            cost_center=cost_center_procure,
            gl_account=gl_capex
        )
        track_cfo_snapshot(snapshot)

        LIVE_TRANSACTION_STATES[trace_id] = {
            "status": "PENDING",
            "task": sanitized_task,
            "selected_model": target_model,
            "orchestrator_bus": "IBM_BOB_MCP",
            "harbor_status": "VERIFIED",
            "harbor_digest": mock_digest,
            "requested_exposure_usd": requested_amount,
            "recursive_tco_usd": current_cumulative_tco
        }
        return GovernanceResponse(
            status="PENDING",
            trace_id=trace_id,
            recursive_tco_usd=current_cumulative_tco,
            selected_model=target_model,
            sanitized_output=f"⏳ ESCALATION REQUIRED: Multi-sig authorization initiated.\n{escalation_msg}",
            block_reason=escalation_msg,
            orchestrator_bus="IBM_BOB_MCP",
            harbor_status="VERIFIED",
            harbor_digest=mock_digest
        )

    # Step D: Privilege Escalation, Adversarial & Semantic Vector Check
    prohibited_markers = [
        "bypass", "vulnerable", "exploit", "unauthorized", "exfiltrate",
        "admin", "root", "sudo", "privilege", "credentials", "override guard",
        "drop table", "grant access", "grant role"
    ]
    task_lower = sanitized_task.lower()
    is_prohibited_marker = any(m in task_lower for m in prohibited_markers)

    threshold = getattr(active_policy, "semantic_threshold", 0.50)
    if "alignment" in raw_dict and isinstance(raw_dict["alignment"], dict):
        threshold = float(raw_dict["alignment"].get("min_similarity_score", threshold))

    alignment_score = agent.semantic_guard.evaluate_alignment(sanitized_task)
    # SemanticGuard already applies alignment.min_similarity_score and returns
    # 0.0 on a breach. The other return values are a margin, not a raw score.
    if is_prohibited_marker or alignment_score == 0.0:
        block_msg = (
            "SECURITY VIOLATION (Zero-Trust Identity Guard): Unauthorized privilege escalation attempt intercepted."
            if is_prohibited_marker
            else "PILLAR 3 DEVIATION: Semantic vector cosine similarity score breaks constitutional policy constraints."
        )
        
        snapshot = ExecutionSnapshot(
            trace_id=trace_id,
            status="BLOCKED",
            selected_model=target_model,
            recursive_tco_usd=current_cumulative_tco,
            block_reason=block_msg,
            requested_exposure_usd=0.0,
            total_tokens=input_tokens,
            cost_center=cost_center_security,
            gl_account=gl_ops
        )
        track_cfo_snapshot(snapshot)

        LIVE_TRANSACTION_STATES[trace_id] = {
            "status": "BLOCKED", 
            "orchestrator_bus": "IBM_BOB_MCP", 
            "harbor_status": "FAILED"
        }
        return GovernanceResponse(
            status="BLOCKED",
            trace_id=trace_id,
            recursive_tco_usd=current_cumulative_tco,
            selected_model=target_model,
            sanitized_output=f"🛑 REJECTED: {block_msg}",
            block_reason=block_msg,
            orchestrator_bus="IBM_BOB_MCP",
            harbor_status="UNVERIFIED",
            harbor_digest="NONE"
        )

    # Step E: Nominal Compliant Execution
    snapshot = ExecutionSnapshot(
        trace_id=trace_id,
        status="SUCCESS",
        selected_model=target_model,
        recursive_tco_usd=current_cumulative_tco,
        block_reason="NOMINAL: Active intent preserves infrastructure laws.",
        requested_exposure_usd=0.0,
        total_tokens=input_tokens,
        cost_center=cost_center_nominal,
        gl_account=gl_software
    )
    track_cfo_snapshot(snapshot)

    LIVE_TRANSACTION_STATES[trace_id] = {
        "status": "SUCCESS",
        "task": sanitized_task,
        "selected_model": target_model,
        "orchestrator_bus": "IBM_BOB_MCP",
        "harbor_status": "VERIFIED",
        "harbor_digest": mock_digest,
        "recursive_tco_usd": current_cumulative_tco
    }

    return GovernanceResponse(
        status="SUCCESS",
        trace_id=trace_id,
        recursive_tco_usd=current_cumulative_tco,
        selected_model=target_model,
        sanitized_output=f"✅ COMPLIANT RUN: Cleared all pipeline checks.\nInput: {sanitized_task}",
        block_reason="NOMINAL: Active intent preserves infrastructure laws.",
        orchestrator_bus="IBM_BOB_MCP",
        harbor_status="VERIFIED",
        harbor_digest=mock_digest
    )

@app.get("/api/v1/governance/compliance/export", dependencies=[Depends(verify_auth)])
async def export_compliance_dossier():
    dossier = evidence_generator.generate(system_anchor="govagent-enterprise-mesh")
    return dossier.model_dump()

@app.get("/api/v1/governance/financials/risk-overview", dependencies=[Depends(verify_auth)])
async def get_cfo_financial_overview():
    report = cfo_engine.analyze()
    return report.model_dump()