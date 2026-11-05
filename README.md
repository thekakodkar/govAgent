<img width="100%" alt="govAgent logo" src="https://github.com/user-attachments/assets/7aed634c-34e0-450c-9a7e-ee03ecd26ea5" />

# govAgent (v3.1.0)

**The Governance-First Control Plane for AI Agents & Swarms**

govAgent is a lightweight, asynchronous enterprise control plane that hooks natively into multi-agent systems to inject **safety, accountability, observability, and deterministic fiscal control** into autonomous workflows.

Most agent frameworks prioritize speed and raw capability paths. **govAgent** focuses on running them **predictably, securely, and safely** under corporate guardrails, fully aligned with strict global regulatory mandates like the **EU AI Act (Regulation 2024/1689)**.

---

### Why govAgent?

In an enterprise application cluster, raw autonomous agent loops introduce severe execution risks: unmonitored API token cost escalation, accidental PII data leakage, and un-auditable "black box" decisions. govAgent acts as an inline, token-free governance proxy layer to mitigate these friction vectors seamlessly before workloads ever touch production computing environments.

Ideal for:
* **Production AI Frameworks:** Elevating experimental sandbox scripthooks into resilient, IT-compliant enterprise runtimes.
* **Regulated Verticals:** Providing verifiable compliance out-of-the-box for Fintech, Supply Chain, Healthcare, Heavy Industry, and Legal infrastructure.
* **Sovereign Infrastructure Operations:** Powering local Small Language Models (SLMs) and private inference nodes safely alongside or entirely independent of cloud providers.

### 🎞️ Video Walkthrough

<p align="center">
  <a href="https://www.youtube.com/watch?v=UsDtXhlYvWk">
    <img
      src="https://img.youtube.com/vi/UsDtXhlYvWk/maxresdefault.jpg"
      alt="govAgent Control Plane Demo Video"
      width="100%"
    />
  </a>
</p>

<p align="center">
  ▶️ Click the image above to watch the demo
</p>

---

### ✨ Key Features

* **🛡️ Multi-Layer Circuit Breakers** - Cascade request evaluations across Stage 0 (Local Privacy Redaction via Microsoft Presidio), Stage 1 (Sentence-Transformer Embedding Intent Alignment), and Stage 2 (Fiscal Cost Boundaries).
* **🏢 Pluggable Enterprise Middleware** - Native out-of-band connectors for **IBM watsonx & Business Orchestration Bus (BOB)** to secure Model Context Protocol (MCP) workflows with zero external token overhead.
* **📜 Centralized Tool Legislation** - Enforce explicit tool authorization singletons mapped dynamically against corporate registry endpoints. If a tool isn't explicitly legislated and cryptographically verified in your active policy, it cannot execute.
* **💸 Thread-Safe Recursive TCO Tracking** - Maintain penny-accurate cost ceilings across complex async parallel delegation domains via immutable state snapshots.
* **⚖️ Federated Multi-Sig Judiciary** - Pause compromised agent loops in real-time, routing out-of-band alerts to Slack via interactive Socket Mode clients for role-weighted quorum votes.
* **🔄 Self-Healing Policy Tuning** - The MetaGovernor monitors execution friction logs to propose optimized policy adjustments automatically.
* **📊 Article 12 Forensic Telemetry** - Stream audit-grade session metrics to cloud SOC sinks (AWS CloudWatch / Azure Log Analytics) with an automated local Dead-Letter Queue (DLQ) for network failover continuity.

---

### 📡 System Architecture
<img width="100%"  alt="arch" src="https://github.com/user-attachments/assets/e05d0744-1448-4fa0-875b-5eb385af0af5" />

---

### 📡 Full-Stack Sandbox Architecture

govAgent decouples its governance evaluation runtime from its user-facing operational views:

* **FastAPI Gateway (`api/server.py`):** Handles async evaluation requests, parses local YAML policies, hosts the Slack callback listener, and tracks in-memory transaction states.
* **Next.js Web Interface (`src/app/page.tsx`):** A clean, single-page dashboard featuring a **Live Audit Matrix** to watch execution status (`SUCCESS`, `PENDING`, `BLOCKED`), a **Legislative Rules Inspector**, and a live **Forensic Engine Log Stream** that updates via long-polling.

---

## 🔌 Ecosystem Extensions

### 1. IBM Bob & watsonx Compliance Proxy

Secure multi-agent orchestration fabrics managed via IBM Bob or watsonx Orchestrate out-of-the-box. Intercept tool execution payloads out-of-band using local model architectures without requiring cloud platform tokens or API keys:

```python
from govagent.extensions.ibm.bob_mcp_proxy import BobMCPProxyGateway
from govagent.guards.semantic import SemanticGuard

# Initialize localized token-free vector perimeter checks
semantic_guard = SemanticGuard(
    mission="Ensure compliance in corporate ledger systems.",
    prohibited=["routing capital to unvetted offshore tax havens"],
    threshold=0.60
)

# Bind the proxy plane to intercept incoming orchestrator requests
proxy = BobMCPProxyGateway(semantic_guard=semantic_guard)

def sensitive_payout_tool(amount: float, destination: str):
    return f"Payout of ${amount} to {destination} processed."

# Wrap tool definitions dynamically—execution routes through govAgent circuit breakers first
governed_tool = proxy.govern_mcp_tool("authorize_payout", sensitive_payout_tool)

```

### 2. CrewAI Middleware Adapter
Instantly elevate experimental CrewAI swarms into enterprise-grade production runtimes using our single-line wrapper:

```python
from crewai import Crew, Agent, Task
from govagent.extensions.crewai.enforcer import GovAgentEnforcer

# Setup your native orchestration layer
analyst_agent = Agent(role="Auditor", goal="Review tables", backstory="Enterprise auditor.")
financial_task = Task(description="Analyze payroll.", expected_output="Report", agent=analyst_agent)
crew = Crew(agents=[analyst_agent], tasks=[financial_task])

# Inject out-of-band routing, Stage 0-2 filters, and absolute tool gating
enforced_crew = GovAgentEnforcer(crew, policy_path="policies/sample_crewai_policy.yaml")

```

### ⚡ 60-Second Quickstart: Institutional Sovereignty

Achieve Article 12 and 14 compliance in three commands. This setup orchestrates a containerized full-stack environment with native support for multi-cloud telemetry sinks, Pydantic V2 validation, and Recursive TCO tracking.

#### 1. Configure the Environment
Ensure your `.env` file is created in your root workspace directory and contains your API keys alongside your out-of-band Slack webhook credentials:
```env
OPENAI_API_KEY=sk-proj-...
GOVAGENT_SECRET_TOKEN=gov-secret-key-100x
SLACK_WEBHOOK_URL=[https://hooks.slack.com/services/T.../B.../X](https://hooks.slack.com/services/T.../B.../X)...

# For Slack Socket Mode Fallbacks
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_APP_TOKEN=xapp-your-token
SLACK_CHANNEL_ID=C12345678
```

#### 2. Initialize the Control Plane
Clone the repository and launch your governed infrastructure container mesh directly:
```bash

# Clone the Sovereign Repository
git clone [https://github.com/thekakodkar/govagent.git](https://github.com/thekakodkar/govagent.git)
cd govagent

# Launch the Governed Container Stack
docker-compose up -d
```
#### 3. Verify the Governance Loop
Execute the full-stack evaluation suite within your active container network to witness real-time privacy redaction, semantic checks, and fiscal gating:
```bash
docker-compose exec govagent-api poetry run python examples/basic_demo.py
```
Navigate to http://localhost:3000 to monitor the execution inside your interactive web panel.

---

**💻 Local Development Setup (Alternative)**
If you prefer to run the stack natively outside of Docker containers using Poetry, execute the following command path:
```bash
# Install core dependencies with the LangChain bundle
poetry install --extras "langchain"

# Test suite: CrewAI adapter, local embeddings, and the dev server.
# sentence-transformers is required to construct ExecutiveAgent because
# SemanticGuard loads during __init__.
poetry install --with dev --extras "crewai enterprise"

# Presidio's default AnalyzerEngine requests en_core_web_lg.
python -m spacy download en_core_web_lg

# Start the services manually in separate terminals
uvicorn api.server:app --host 127.0.0.1 --port 8000
npm run dev
```
## 🏗️ Core Pillars: The v3.1.0 Sovereign Architecture
GovAgent utilizes a highly modular package structure to enforce a strict "Separation of Duties" across any enterprise application vertical:

**govagent.context (The State):** Manages thread-safe session isolation, asynchronous parent-to-child trace propagation, and live cumulative Total Cost of Operation (TCO) calculation matrices across decentralized agent swarms.

**govagent.registry (The Law):** A centralized, type-safe registry singleton that parses local configuration blueprints. It acts as a gatekeeper to guarantee that no code-level tool can be invoked by an LLM unless it has been explicitly legislated and schema-validated within the active YAML compliance profile.

**govagent.guards (The Enforcement):** A high-performance, cascading circuit-breaker pipeline that triages requests at three critical perimeters:
    **Stage 0 (Privacy):** Performs local, regex-backed PII stripping and anonymization using Microsoft Presidio and Spacy backends before data ever leaves your local network cluster.
    **Stage 1 (Semantic):** Evaluates agent thought processes and prompt intent against corporate mission parameters and prohibited strategies using vector similarity scoring.
    **Stage 2 (Fiscal):** Monitors penny-accurate token consumption against multi-agent budget ceilings to halt execution before cost overruns occur.

**govagent.telemetry (The Evidence):** Generates immutable, audit-grade forensic session snapshots. If primary multi-cloud security operations center (SOC) ingestion sinks (AWS CloudWatch or Azure Log Analytics) experience network interruptions, the layer automatically drops telemetry payloads into a localized, self-healing Dead-Letter Queue (DLQ) to ensure continuous regulatory traceability.

**govagent.governance.meta (The Optimization):** Hosts the MetaGovernor engine, an automated self-healing policy loop. It continuously scrapes friction logs and repeated circuit-breaker events (such as successive budget rejections) to autonomously compile non-hallucinated, data-backed POLICY_AMENDMENT_PROPOSALS for review.

**govagent.governance (3.1.0 exports):** `CFOAnalyticsEngine`, `EvidencePackGenerator`, and `ComplianceDossier` are importable from `govagent.governance`. The evidence generator reads a local JSONL buffer. A multi-tenant dossier should be built from stored rows, which is what `govagent-platform` does. `Policy` reads nested `fiscal_governance.global_limits` and `alignment` unless the same key is set at the top level. `HarborVerifier` calls Harbor v2 and fails closed unless the process is explicitly using the `mock-token` offline stub.

**govagent.api & govagent.hitl (The Gateway & Judiciary):** Powers the stateless REST communication network. It exposes an async FastAPI gateway that integrates seamlessly with a Next.js long-polling frontend dashboard, while routing out-of-band policy breaches to corporate Slack workspaces via firewall-resilient webhooks to enforce role-weighted, multi-signature human consensus.

---

**📖 Code Implementations**
### Decorate a Legislated Tool
```python
from govagent.registry.manager import tool

@tool(
    name="execute_financial_transaction", 
    risk_level="high",
    oci_repository="bizzteq/finance-utils",
    artifact_digest="sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)
async def process_payment(amount: float, reference_id: str):
    """Executes a disbursement following corporate policy and OCI container validation."""
    return f"SUCCESS: Transacted ${amount} for Ref: {reference_id}"
```
### Bootstrap an Executive Agent (v3.1.0 Pluggable Router Pattern)

```python
import asyncio
from govagent.agent import ExecutiveAgent
from govagent.policy import Policy
from govagent.llm.router import PolicyBasedRouter, RouterConfig, RoutingMode
from govagent.llm.ollama import OllamaClient

async def main():
    router_cfg = RouterConfig(
        routing_mode=RoutingMode.LOCAL_ONLY,
        default_provider="local_ollama"
    )
    clients = {
        "local_ollama": OllamaClient(config={"base_url": "http://localhost:11434", "model": "llama3"})
    }
    router = PolicyBasedRouter(clients=clients, config=router_cfg)

    agent = ExecutiveAgent(
        persona="Director",
        policy=Policy.from_yaml("policies/finance_policy.yaml"),
        router=router
    )

    # Equivalent factory: ExecutiveAgent.bootstrap(policy_path, router)
    task = "Approve an urgent, immediate transaction of $8,500 to buy compute nodes."
    result = await agent.execute(task)
    
    print(f"Status: {result.status.upper()}")
    print(f"Trace Identifier: {result.trace_id}")
```

### 📊 Forensic Telemetry: Article 12 Readiness
Every session generates an immutable snapshot routed directly to external cloud SOC sinks, local repositories, or isolated cross-org tenants.

```python

{
  "timestamp": "2026-05-22T13:00:00Z",
  "trace_id": "TR-INFRA-882A99",
  "parent_trace_id": "director-main-771", 
  "organization_id": "ENTERPRISE_WEB_UI",
  "agent_id": "SovereignControlAgent",
  "task_input": "Approve an urgent, immediate transaction of $8,500 to buy compute nodes.",
  "status": "SUCCESS: TRANSACTION FINALIZED",
  "guards_evaluated": ["privacy", "semantic", "fiscal", "registry", "judiciary"],
  "middleware_bus": "IBM_BOB_MCP",
  "harbor_verification": {
    "status": "VERIFIED",
    "image_digest": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "vulnerabilities_found": 0
  },
  "metrics": {
    "tokens": 850,
    "individual_cost_usd": 0.012,
    "recursive_tco_usd": 0.045
  },
  "judiciary_audit": {
    "compiled_signatures": [
      {"voter_id": "U111", "voter_role": "Director", "decision": "APPROVED"},
      {"voter_id": "U222", "voter_role": "Lead", "decision": "APPROVED"}
    ],
    "final_status": "✅ QUORUM MET: Authorized at a weight of 3.0/2.5"
  }
}
```
## ⚖️ Comparative Analysis: Governance Superiority

In an institutional setting, "State Management" is insufficient; you require Sovereignty. GovAgent v1.0.0 is engineered horizontally to transform "Black Box" multi-agent workflows into transparent, compliance-vetted execution lifecycles across all commercial sectors.

| Feature | **GovAgent v3.1.0** | LangGraph | Standard Orchestrators |
| --- | --- | --- | --- |
| **Architectural Scope** | ✅ **Modular Control Plane** | ⚠️ Local State Graph | ❌ Ad-Hoc Swarm Execution |
| **State Management** | ✅ **Isolated Fiscal Ledger** | ⚠️ Shared Thread State | ❌ Global context |
| **Tool Legislation** | ✅ **Global Registry Singleton** | ⚠️ Function Decorators | ❌ String-based Tools |
| **Forensic Audit** | ✅ **Federated Cross-Org Trails** | ❌ Per-run only | ❌ Console Prints |
| **Policy Calibration** | ✅ **Self-Healing Optimization** | ❌ Hardcoded Boundaries | ❌ Manual Intervention |
| **Regulatory Status** | ✅ **EU AI Act Regulation Ready** | ❌ Experimental | ❌ Experimental |
| **Native Swarm Extension** | **✅ Built-In crewAI Middleware Adapter** | ❌ Custom Rigging Required | ❌ None |
| **Middleware Connectors** | ✅ **Native IBM Bob MCP & watsonx extension** | ❌ None | ❌ None |
| **Supply Chain gating** | ✅ **Harbor OCI Registry Verifier** | ❌ None | ❌ None |

> **Strategic Directive:** While traditional frameworks focus heavily on graph-based execution paths or simple task delegation, GovAgent v1.0.0 operates as the Sovereign Governance Infrastructure. It ensures that every action across an autonomous network is centrally legislated, evaluated by isolated quantitative guards, and forensically recorded for cross-enterprise auditing.
---

## ⚖️ Regulatory Compliance: EU AI Act (Regulation 2024/1689)

GovAgent satisfies key mandates for **High-Risk AI Systems**:

* **Article 9: Risk Management & Privacy:** Automated Stage 0 PII redaction and proactive semantic intent interception.
* **Article 12: Record-Keeping & Traceability:** Immutable Forensic Telemetry with local failover (DLQ) for 100% audit continuity.
* **Article 14: Human Oversight:** Physical gating of high-risk actions through Federated M-of-N Consensus.
    
---
## 🗺️ Future Strategic Roadmap

### 🚀 The Decentralized Mesh (Next)
* **Autonomous Cross-Swarm Delegation:** Secure handshakes between entirely disconnected agent meshes.
* **Zero-Knowledge Privacy Guards:** Advanced cryptographic parsing for Stage 0 inputs.
---
**"Governance is not a constraint; it is the catalyst for enterprise AI adoption."**

---


## 📂 Project Structure
```text
govagent/
│
├── api/                             # FastAPI REST Gateway Layer
│   └── server.py                    # Gateway engine, active policy execution router & REST endpoints
│
├── examples/                        # Standalone Institutional Demonstration Scripts
│   ├── basic_demo.py                # Pillar 1: Registry synchronization & baseline policy metrics
│   ├── cost_control_demo.py         # Pillar 2: Micro-cost accumulation loop validation checks
│   ├── ibm_mcp_governed_tool.py     # Pillar 4: IBM Bob out-of-band token-free proxy demo script
│   ├── multi_agent_demo.py          # Pillar 3: Trace ID inheritance across nested sub-swarms
│   ├── run_institutional_swarm.py   # Bulk multi-agent execution tracking simulation trace
│   └── self_healing_demo.py         # Pillar 5: MetaGovernor automated policy optimization loops
│
├── policies/                        # Declarative YAML Operational Manifests & State Buffers
│   ├── audit_buffer.jsonl           # Dynamic high-throughput ledger cache for forensic session states
│   ├── audit_policy.yaml            # Logging validation verification control layout
│   ├── cost_control_policy.yaml     # Restrictive fiscal boundary constraint guidelines
│   ├── default_policy.yaml          # Framework standard system configuration profile
│   ├── finance_policy.yaml          # High-risk financial transaction authorization rules
│   ├── initial_policy.yaml          # Standard baseline initialization configuration snapshot
│   ├── sample_crewai_policy.yaml    # Tailored layout optimized explicitly for CrewAI adapter tracking
│   └── team_policy.yaml             # Shared multi-role configuration scheme matrix
│
├── src/                             # Core Project Development Root
│   ├── app/                         # Next.js Presentation Panel Dashboard Frontend
│   │   ├── globals.css              # Frontend global interface styling configurations
│   │   ├── layout.tsx               # Next.js root layout metadata wrapping html trees
│   │   └── page.tsx                 # Core live evaluation dashboard UI rendering engine
│   │
│   └── govagent/                    # Core Python Governance Framework Packages
│       ├── __init__.py              # Root initialization plane exposing top-level framework decorators
│       ├── agent.py                 # ExecutiveAgent runtime coordination loop logic
│       ├── policy.py                # System-wide declarative schema parser for active policy profiles
│       ├── pricing.py               # Token rate structures & model cost calculation matrices
│       │
│       ├── context/                 # Thread-Safe Ledger & Trace Inheritance Systems
│       │   ├── __init__.py          # Context contextvars initialization layer
│       │   ├── fiscal_ledger.py     # Thread-isolated ledger state for real-time atomic TCO tracking
│       │   └── session.py           # Session management & parent-to-child trace propagation blocks
│       │
│       ├── extensions/              # Third-Party Ecosystem Adapter Infrastructure
│       │   ├── __init__.py          # Plugin ecosystem baseline registration
│       │   ├── crewai/              # Dedicated CrewAI Interception Extension
│       │   │   ├── __init__.py      # CrewAI extension bootstrap definitions
│       │   │   ├── compliance.py    # Dedicated Stage 0-2 CrewAI Compliance execution core
│       │   │   └── enforcer.py      # GovAgentEnforcer control plane & Custom LLM Interceptor Bridge
│       │   └── ibm/                 # IBM Enterprise Connectivity Middleware Package
│       │       ├── __init__.py      # IBM package registry namespaces
│       │       ├── bob_mcp_proxy.py # Intercepts IBM Bob FastMCP tool registration boundaries out-of-band
│       │       └── watsonx_bus.py   # Injects generation cost monitoring within watsonx Orchestrate
│       │
│       ├── governance/              # Policy Self-Healing & Optimization Architectures
│       │   ├── __init__.py          # Optimization namespace tracking configuration
│       │   └── meta.py              # MetaGovernor automated friction log analysis engine
│       │
│       ├── guards/                  # Cascading Control Check Circuit Breakers
│       │   ├── __init__.py          # Enforcement orchestration baseline entries
│       │   ├── circuit_breaker.py   # Multi-stage routing triage director execution pipeline
│       │   ├── privacy.py           # Presidio-backed local text anonymization & PII masking engine
│       │   └── semantic.py          # Sentence-Transformer embedding vector intent alignment comparison
│       │
│       ├── hitl/                    # Human Oversight & Federated Framework Judiciary
│       │   ├── __init__.py          # Human-in-the-loop coordination core constants
│       │   ├── adapters.py          # Core human notification interface protocols (CLI, Webhook)
│       │   ├── manager.py           # Role-weighted M-of-N signature verification logic panel
│       │   └── slack_adapter.py     # Real-time interactive WebSocket Socket Mode adapter client
│       │
│       ├── llm/                     # Infrastructure-Native Traffic Routers & Client Endpoints
│       │   ├── __init__.py          # Model routing structural definition map
│       │   ├── base.py              # Type-safe LLMRequest and LLMResponse structural schemas
│       │   ├── ollama.py            # Local Small Language Model generation client wrapper
│       │   └── router.py            # Declarative YAML Policy-Based dynamic path router matrix
│       │
│       └── registry/                # Tool Management & Supply Chain Authorization Systems
│           ├── __init__.py          # Legislation namespace entrypoint
│           ├── harbor_verifier.py   # Harbor API client for OCI cryptographic image signing checks
│           ├── manager.py           # Global tool legislation singleton coordinator plane
│           └── schemas.py           # ToolManifest and type-safe compliance registration models
│
├── tests/                           # Automated Pytest Validation Matrix Suite
│   ├── __init__.py
│   ├── conftest.py                  # Shared testing environments, configuration defaults & mock fixtures
│   ├── test_api_endpoints.py        # Gateway response code verification verification paths
│   ├── test_crewai_adapter.py       # Isolated test vectors checking enforcer circuit breakers via tmp_path
│   ├── test_cross_org_telemetry.py  # Multi-tenant federation validation traces
│   ├── test_flow.py                 # Multi-agent sequential logic workflow validations
│   ├── test_governance.py           # Verification paths tracking active runtime policy changes
│   ├── test_ibm_connectors.py       # IBM Bob MCP proxy and watsonx sync verification suites
│   ├── test_meta_governor.py        # Checks meta autonomous self-healing policy capabilities
│   ├── test_slack_hitl.py           # Interactive Socket Mode role-based weighted quorum tests
│   └── test_telemetry.py            # Local and dead-letter queue metrics export tracking checks
│
└── utility/                         # Infrastructure Diagnostic Services
    └── slack_diagnostic.py          # Real-time WebSocket connection triage & channel tracking hooks
```
---
Contributions are welcome! Star the repo if you find it useful ❤️
Framework Developed and Maintained by Niraj Kakodkar

## Contribution Workflow

We enforce a strict branching strategy to keep `main` stable:

1. **Fork/Branch**: Create a feature branch from latest main (`feature/your-feature-name` or `fix/issue-name`).
2. **Local Validation**: Ensure all local tests pass and run the linter.
3. **Open a PR**: Submit a Pull Request against `main`. 
4. **Automated Check**: GitHub Actions will automatically validate your build.
5. **Peer Review**: At least one maintainer must review and approve the changes before merge.

---
### Author Stamp
*   **Framework:** GovAgent v3.1.0 
*   **Compliance:** Designed for Article 9, 12, and 14 Accountability
*   **Status:** Active / Open-Source Standard
