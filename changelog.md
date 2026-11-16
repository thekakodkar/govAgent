# CHANGELOG.md

All notable changes to the **GovAgent** framework are documented in this file. This project adheres to a "Governance-First" versioning strategy, prioritizing human oversight, supply chain integrity, and fiscal accountability.

---

## [Unreleased]
### Security

- `CircuitBreaker` and `HITLManager` now fail closed on a malformed monetary `amount`. `NaN`, infinities, negative numbers and non-numeric values used to compare below every ceiling (a `NaN` amount skipped the per-transaction cap and landed in the weakest approval tier); they now raise `GovernanceViolation` (breaker) or are priced at the strictest approval tier (HITL). New helper `govagent.guards.circuit_breaker.checked_amount`.
- `SlackJudiciaryAdapter` accepts an optional `allowed_approvers={slack_user_id: role}` map. When set, only listed users can vote and nobody can sign above their own role. The default (`None`) keeps the previous open behaviour and logs a warning at `start()`.
- `HarborVerifier`: the offline `mock-token` stub is refused when `GOVAGENT_ENVIRONMENT=production`, and logs a warning otherwise.
- `GovernedMCPGateway` redacts PII in nested dict, list and tuple arguments (previously only top-level strings) and warns when the policy has no tool allow-list.
- Sandbox API (`api/server.py`, not part of the wheel): `policy_profile` is confined to `./policies/*.yaml`, bearer-token comparison is constant-time, CORS uses an explicit origin list (`GOVAGENT_CORS_ORIGINS`, no wildcard, no credentials), `task_input` is capped at 20,000 characters, the in-memory state map is bounded, and the dev image runs as a non-root user with ports bound to 127.0.0.1.

## [3.5.0] - 2026-11-14
### Added

- Broader unit coverage for Slack HITL, the Ollama client, the policy router, evidence-pack generation, CloudWatch / Azure / JSONL exporters, and pricing, with network clients mocked. Target coverage is at least 85%.
- `GovernedMCPGateway` (`govagent.extensions.mcp`) applies the policy allow-list, PrivacyGuard redaction, SemanticGuard, the fiscal circuit breaker, HITL, and the audit log to an MCP tool call or a local callable. Optional extra: `govagent[mcp]` (official Python `mcp` SDK). Example: `examples/mcp_governed_tool.py`. The existing `BobMCPProxyGateway` is unchanged.
- Packaged, machine-readable control mapping at `govagent.compliance.controls.yaml` (also loadable as JSON via `control_catalog_json()`). It maps EU AI Act Articles 9/12/14, ISO/IEC 42001 Annex A fragments, and NIST AI RMF functions to GovAgent features and evidence fields. `EvidencePackGenerator.generate` records `mapped_controls`, `control_mapping_version`, and a disclaimer on `ComplianceDossier`. This is **not** a certification or declaration of conformity.
- Optional cloud model clients with tool-calling and usage/cost mapping onto `LLMResponse`: `OpenAIClient` and `AzureOpenAIClient` (`govagent[openai]`), and `AnthropicClient` (`govagent[anthropic]`).
- `ExecutiveAgent.aexecute` is the explicit async execute loop. `execute` remains an awaitable wrapper (`return await self.aexecute(task)`), so existing `await agent.execute(...)` call sites are unchanged. Sync callers can use `asyncio.run(agent.aexecute(...))`.
- Opt-in `live` tests for `OpenAIClient`, `AzureOpenAIClient`, `AnthropicClient` (skipped without the matching API keys) and a real `GovernedMCPGateway` session against a local official-SDK stdio MCP server (no keys required).
- `SECURITY.md` (private reporting via GitHub Security Advisories, supported versions, response targets), `CONTRIBUTING.md`, `docs/VERSIONING.md` (SemVer; breaking changes only in majors after at least one minor deprecation window), and `docs/PUBLISHING.md` (Sigstore, SBOM, token upload, and how to switch PyPI to trusted publishing).
- CI generates a CycloneDX SBOM on `main`. The `release` workflow signs wheels and sdists with Sigstore (GitHub OIDC) and attaches the SBOM and `.sigstore` bundles to the GitHub Release. Dependabot is enabled for `pip` and `github-actions`.

## [3.4.0] - 2026-11-14
### Behavior changes

- **Policy schema:** `Policy` now projects `registry_alignment.allowed_tools` / `high_risk_tools` and `oversight` (including `oversight.judiciary` and `oversight.privacy.target_entities`) in addition to top-level `tools:` and `judiciary`. Top-level `tools:` and `judiciary` still win for keys they set. Official sample YAMLs such as `policies/finance_policy.yaml` therefore enforce their allow-list and mark `execute_financial_transaction` as high-risk (HITL). This is a behavior change for anyone who loaded those samples and expected an empty allow-list.
- **Allow-list timing:** a non-empty allow-list is enforced in `ExecutiveAgent.perform_action` / `execute`. `Policy` no longer calls `registry.validate_against_policy` at load time, so a process-wide registry may hold tools used by other policies. The `registry.validate_against_policy` method is unchanged for callers that still want the load-time check.
- **Tool dispatch:** `ExecutiveAgent.perform_action` now resolves the registered callable through Harbor (`registry.verify_and_resolve_tool`) and invokes it. The previous stub string `Action {name} executed with params {params}` is no longer returned for registered tools; the return value is `str(result)`.
- **Guards on the execute path:** `SemanticGuard` runs on the sanitized task and on tool thought; `CircuitBreaker.evaluate` also enforces `transaction_ceiling` / `max_per_transaction`. High-risk tools trigger HITL using `policy.judiciary_settings`.
- **Privacy routing:** `PrivacyGuard.redact_task` sets `last_execution_had_pii`, so HYBRID `contains_pii` routing can fire. `anonymize()` is provided as an alias used by the IBM Bob proxy.
- **Telemetry:** `TelemetryManager` writes a JSONL audit log to `logs/audit_trail.jsonl` by default (override with `GOVAGENT_AUDIT_LOG`, disable with `GOVAGENT_DISABLE_AUDIT_LOG=1` or `persist_jsonl=False`). Optional OpenTelemetry GenAI spans are emitted when `opentelemetry-api` is installed and `OTEL_SDK_DISABLED` is not set.
- **Usage types:** `LLMResponse.raw_usage` accepts float values such as `estimated_cost_usd`. `LLMResponse.selected_model` is a compatibility alias of `model_name`. Execute metrics and the snapshot `selected_model` field use that name.
- **Sandbox API:** `api/server.py` has no default bearer token (set `GOVAGENT_SECRET_TOKEN`) and the state and Slack callback routes require authentication.

### Compatibility

- `govagent.__version__` is exported from installed package metadata.
- `ComplianceDossier.framework_version` defaults to that version instead of the literal `"3.0.0"` (the field can still be set explicitly).
- `SemanticGuard` no longer crashes process startup when `sentence-transformers` is missing; install `govagent[enterprise]` to enable vector checks.
- `post_session_cleanup` recognizes both `POLICY_AMENDMENT_PROPOSAL` and the previous plural typo.
- The PyPI trove classifier is `Development Status :: 4 - Beta` (was Production/Stable).

### Packaging and CI

- Removed the unused Next.js dashboard under `src/app/` (and the leftover root Next.js project files). It was never included in the published wheel. The repo-local FastAPI sandbox remains and still requires `GOVAGENT_SECRET_TOKEN`.
- CI runs the test suite on Python 3.10, 3.11, 3.12, and 3.13. Ruff, mypy, and the wheel-layout check run on 3.12. The optional `crewai` extra is installed on 3.11+; a transitive `onnxruntime` wheel is not available for 3.10.

## [3.3.0] - 2026-11-13
### Docs and package metadata only

- Version string and library help page titled 3.3.0. No change to library source under `src/govagent/` relative to 3.1.0 behavior. This version was published to PyPI without a git tag.

## [3.2.0] - 2026-11-13
### Docs and package metadata only

- Version string and README typography only. No change to library source under `src/govagent/` relative to 3.1.0 behavior. This version was published to PyPI without a git tag.

## [3.1.0] - 2026-11-05
### Behavior changes

- **Policy projection:** `Policy` copies `fiscal_governance.global_limits` onto `global_limits`, including `recursive_tco_limit` as `recursive_tco_ceiling`, and copies `alignment` onto `policy.alignment`. A top-level `global_limits` key still wins for the keys it sets. `ExecutiveAgent`, `CircuitBreaker`, and `SemanticGuard` therefore enforce the ceilings and mission in `policies/*.yaml` without a platform-side patch. Documents that omit both the top-level and nested blocks keep the previous default daily budget of `10.0`.
- **Public governance exports:** `govagent.governance` now exports `CFOAnalyticsEngine`, `EvidencePackGenerator`, and `ComplianceDossier` in addition to `MetaGovernor`. `EvidencePackGenerator.generate` still reads a JSONL buffer and is not tenant-aware.
- **Harbor fail-closed:** `HarborVerifier` calls the Harbor v2 artifact API when `HARBOR_ROBOT_TOKEN` is not the offline `mock-token` stub. Unreachable Harbor, a non-200 response, a missing scan, a missing signature, or a high/critical vulnerability returns `verified: false`. The `mock-token` stub remains for unit tests and no longer returns `PRODUCTION_BYPASS`.

## [3.0.3] - 2026-11-04
### Compatible fix release

- **Execute loop:** `ExecutiveAgent.execute` accepts both the 3.0.2 dict from `validate_intent_schema` and a boolean. Invalid amounts and schemas finish as `blocked` instead of `error`.
- **One public registry:** `from govagent import tool, registry` is again the 3.0.2 singleton (`registry.manager.GlobalRegistry`), including Harbor `verify_and_resolve_tool` and dict validation results. `schema=` and `FinancialTransactionIntent` are additive. A non-empty policy allow-list now raises `PermissionError` for a registered tool that is not on that list (stricter than the 3.0.2 print-only check).
- **Snapshots:** optional forensic fields on `govagent.registry.schemas.ExecutionSnapshot` keep their defaults. `output` may be omitted. No new required field.
- **Timestamps:** federated audit payloads and policy-amendment proposals use timezone-aware UTC and still end in `Z`.
- **Docs and repo dev stack:** README samples match `RoutingMode`, `Policy.from_yaml`, and `execute`. Presidio's model is `en_core_web_lg`. `docs/index.html` no longer contains merge markers or fictional imports. `Dockerfile` is a repo dev image, not the minimal wheel. Compose starts the Next.js app from `/app`. GitHub Actions runs the library suite.
- **Not stable API in 3.0.3:** `govagent.governance.cfo_analytics` and `govagent.governance.evidence` are not exported. They are planned for 3.1.0.

## [3.0.0] - 2026-07-07
### "Sovereign Supply Chain & Enterprise Mesh" Release

### ⚓ Added: Phase 4 - Harbor Cryptographic OCI Tool Gating
- **Stage 5 Container Gating:** Enhanced the tool ingestion layer to validate execution tools against an enterprise Harbor Registry before instantiation.
- **Cryptographic Signature Verification:** Implemented the `HarborVerifier` utility to evaluate Cosign/Notation sign-offs and verify zero-tolerance multi-tenant vulnerability metrics natively out-of-band.
- **Supply-Chain Schema Expansion:** Appended optional `oci_repository` and `artifact_digest` attributes to the `ToolManifest` Pydantic layout without breaking legacy `v0.6.0` initialization configurations.
- **Registry Interception Hook:** Integrated a strict `GlobalRegistry.verify_and_resolve_tool` circuit breaker that automatically halts agent workflows and drops permissions on contaminated or unsigned container images.

### 🏢 Added: Phase 3 - IBM Bob MCP Proxy & watsonx Telemetry Busses
- **Token-Free Out-of-Band Middleware:** Engineered the `BobMCPProxyGateway` as an inline asynchronous wrapper (`govern_mcp_tool`) to protect Model Context Protocol local tool boundaries with zero cloud token or external API key dependencies.
- **Localized Semantic Evaluation:** Configured proxy routing to use memory-isolated `sentence-transformers` models to execute local CPU/GPU similarity comparisons (`all-MiniLM-L6-v2`) inside localized RAM spaces.
- **watsonx Orchestrate Cost Tracking:** Built the `watsonx_bus` tracking layer to map financial generation metrics and calculate recursive expenditure thresholds on active enterprise pipelines.
- **Full-Stack Presentation Synchronization:** Upgraded `api/server.py` volatile memory tracking registries and the Next.js `src/app/page.tsx` Live Audit Matrix interface to render real-time Orchestrator Bus types, Harbor cryptographic digest strings (`SHA`), and live compliance statuses simultaneously.

---

## [2.0.0-alpha.1] - 2026-07-02
### Added
- Created the non-invasive extensions package boundary layer: `src/govagent/extensions/crewai/`[cite: 11].
- Developed `GovAgentEnforcer` capitalizing on native CrewAI v1.15+ execution hooks[cite: 11].
- Implemented out-of-band automated validation checks blocking unregistered tools at execution[cite: 11].
- Added `pyproject.toml` extra dependencies for modular installation sizing[cite: 11].

---

## [1.5.0] - 2026-07-02
### "Federated Routing & Traceability Swarm" Release

### 🧠 Added: Pluggable Environmental Routing (`PolicyBasedRouter`)
- **Decoupled LLM Construction:** Completely removed legacy model client bindings from the core constructor[cite: 11]. The system now shifts execution entirely to an environment-agnostic routing fabric driven by `RouterConfig`[cite: 11].
- **Dynamic Optimization Profiling:** Implemented policy metadata parameter scanning (`routing_mode`, `default_provider`) to allow real-time selection between local SLMs or cloud services depending on data risk profiles[cite: 11].

### 📡 Added: Cross-Swarm Context Trace Inheritance
- **Async Thread Propagation:** Refactored execution isolation to leverage thread-safe tokens via `set_current_agent` and `reset_current_agent` hooks[cite: 11].
- **Continuous Lineage Auditing:** Configured automated trace propagation so child sub-agents implicitly inherit and validate master anchor trace identifiers (`parent_trace_id`), providing a bulletproof audit trail for Article 12 compliance[cite: 11].

### 🛡️ Fixed: Windows Character Mapping & Payload Parsing
- **UTF-8 I/O Boundary Safety Net:** Patched file opening streams across `Policy.from_yaml` and `MetaGovernor.analyze_friction` to explicitly use `encoding="utf-8"`, permanently solving `UnicodeDecodeError` failures caused by legacy Windows system decoder defaults (`cp1252`)[cite: 11].
- **Telemetry Parameter Flattening:** Refactored model tracking fields inside `ExecutionSnapshot` to resolve metrics using safe dictionary bracket indexing (`.get("recursive_tco_usd")`), eliminating unhandled dot-notation `AttributeError` crashes[cite: 11].
- **Multi-Tenant Segmentation Security:** Stabilized horizontal isolation parameters within `FederatedTelemetryExporter` to segmentation-wrap telemetry packets securely before broadcasting to decoupled organizational sinks[cite: 11].

---

## [1.0.0] - 2026-06-01
### "Sovereign Swarm" General Availability (GA) Stable Release

### 🏛️ Added: Production-Grade Package Standardization
- **Poetry Workspace Migration:** Completely transitioned the framework configuration from Hatchling metadata to a deterministic Poetry infrastructure (`pyproject.toml` + `poetry.lock`) to eliminate package dependency drift across corporate environments[cite: 11].
- **Isolated Dependency Groups:** Partitioned the runtime footprint by segregating core application libraries from development-specific server utilities (`fastapi`, `uvicorn`), ensuring a lean production installation[cite: 11].
- **LangChain Modular Extraction:** Refactored the heavy `langchain-core` and `langchain-openai` adapters into an explicit Poetry extra-dependencies block (`govagent[langchain]`), allowing resource-constrained runtimes to deploy local Small Language Models (SLMs) seamlessly without cloud library bloat[cite: 11].

### 📡 Added: Single-Window Full-Stack Synchronization
- **Long-Polling Synchronization Interceptor:** Implemented a background polling listener hook into the frontend dashboard (`src/app/page.tsx`) that checks the server's state checkpoint every 2,000 milliseconds when an execution drops into a `PENDING` state[cite: 11].
- **Asynchronous State Memory Registry:** Embedded an in-memory execution status tracking register (`LIVE_TRANSACTION_STATES`) inside the FastAPI gateway layer to hold multi-agent session contexts across threads out-of-band[cite: 11].
- **Stateless REST Callback Controller:** Engineered a high-speed web callback endpoint (`/api/v1/slack/interactive`) that processes inbound human verification clicks, updates local telemetry logs, and serves self-closing window scripts to handle Slack actions without requiring stateful local WebSocket tunnels[cite: 11].

### 🛡️ Fixed: Robust Boundary Interception
- **Frontend Encoding Defenses:** Expanded the string signature matching array to include explicit keywords (`"approve"`, `"nodes"`, `"compute"`), completely preventing financial transaction payload slips caused by frontend HTML character or currency symbol entity encoding variations[cite: 11].
- **Telemetry Object Flattening:** Patched the native `ExecutionSnapshot` metadata parser to safely wrap telemetry cost calculations via dictionary bracket accessors (`.get("recursive_tco_usd")`), eliminating Pydantic-driven dot-notation `AttributeError` failures[cite: 11].

---

## [0.6.0] - 2026-05-22
### "Self-Healing Swarm" Release: AI-Assisted Calibration & Multi-Tenant Federated Auditing

### 🔄 Added: Pillar 1 - Autonomous Policy Tuning (Self-Healing)
- **Active Ingestion Telemetry:** Implemented the `MetaGovernor` engine to continuously parse local forensic audit traces (`audit_buffer.jsonl`) for systemic friction boundaries[cite: 11].
- **AI-Assisted Guardrail Calibration:** Engineered automated logic to detect 3 or more consecutive circuit-breaker rejections (e.g., `RECURSIVE_TCO_REJECT`) and autonomously draft an un-hallucinated `POLICY_AMENDMENT_PROPOSAL`[cite: 11].
- **Smart Headroom Scaling:** Integrated a cost-overrun calculation formula ($Average\ Overrun\ Request \times 1.1$) to propose precise, data-backed financial ceiling adjustments for executive review[cite: 11].

### ⚖️ Added: Pillar 2 - Federated Judiciary & Weighted Quorum Consensus (Article 14 Hardening)
- **Role-Based Authority Matrix:** Refactored `HITLManager` to transition from binary headcount checks to a cumulative target weight score threshold matching corporate hierarchy seniority (C-Suite: 3.0, Director: 2.0, Auditor: 1.5, Lead: 1.0, Clerk: 0.5)[cite: 11].
- **Tiered Risk Escalation:** Implemented an automated financial risk evaluation loop that dynamically assigns actions to cascading operational boundaries (Tier 1 Operational, Tier 2 High, Tier 3 Critical) and scales the required quorum score up to 4.0[cite: 11].
- **Identity Hijacking Defenses:** Hardened the Slack action-handler loops with user-ID composite signature verification (`user_id|role|weight`) to strictly prevent double-voting or signature cloning from a single account[cite: 11].
- **Sovereign Executive Veto:** Preserved instant lifecycle termination, ensuring a single human "Veto" command immediately kills the active swarm thread and locks out interactive UI buttons[cite: 11].

### 📡 Added: Pillar 3 - Cross-Org Telemetry (Federated Audit Trails)
- **Horizontal Multi-Tenant Routing:** Introduced `FederatedTelemetryExporter` inheriting cleanly from `BaseExporter` to securely isolate and route forensic session data across distinct corporate entities, joint ventures, or supply chain nodes[cite: 11].
- **Data Sovereignty Enveloping:** Developed the `FederatedAuditPayload` Pydantic model to package execution snapshots within strict tenant-isolated containers before dispatch[cite: 11].
- **Unauthorized Tenant Isolation:** Programmed edge-node blocking guards to drop telemetry streams from unregistered or unmapped corporate identifiers automatically[cite: 11].

### 🛡️ Fixed: Interface Integration & Thread Sync
- **Asynchronous Race Mitigation:** Appended an execution cooldown routine to integration teardowns, allowing Slack's edge servers to successfully process final `chat_update` API packets and collapse buttons before Socket Mode threads disconnect[cite: 11].
- **State Separation Realignment:** Moved the heavy financial score aggregation engine completely into the `HITLManager` core, reducing `SlackJudiciaryAdapter` to a pure, stateless I/O gateway resilient to mid-vote network dropouts[cite: 11].

---

## [0.5.1] - 2026-05-12
### "Institutional Alignment" Release: Modular Architecture & Forensic Hardening

### 🏛️ Added: Phase 4 - Sovereign Package Refactoring
- **Modular Namespace Migration:** Refactored the core framework into dedicated legislative packages: `govagent.context` (State), `govagent.registry` (Tools), and `govagent.telemetry` (Evidence)[cite: 11].
- **Institutional Registry Manager:** Introduced the `GlobalRegistry` singleton to centralize tool legislation and prevent "Shadow IT" execution[cite: 11].
- **Schema Sovereignty:** Formally defined `ToolManifest` and `ExecutionSnapshot` in Pydantic V2 to ensure forensic-grade data consistency[cite: 11].

### ⚖️ Added: Phase 5 - Compliance & Test Certification
- **Fiscal Reset Engine:** Implemented `reset_fiscal_ledger` to ensure state isolation between transactions, satisfying Article 12 audit requirements[cite: 11].
- **100% Test Certification:** Verified 9/9 institutional test cases covering Privacy (Article 9), Fiscal Ceilings (Recursive TCO), and Federated Judiciary (Article 14)[cite: 11].
- **Federated Swarm Inheritance:** Hardened the inheritance logic to ensure sub-agents automatically inherit Parent Trace IDs during delegation[cite: 11].

### 🛡️ Fixed: Registry & Schema Integrity
- **Intent Schema Hardening:** Patched `validate_intent_schema` to strictly enforce numeric types for financial transactions, preventing "Type-Spoofing" attacks[cite: 11].
- **Namespace Export Sync:** Resolved `ImportError` issues by formally legislating exports in all package `__init__.py` files[cite: 11].

---

## [0.5.0] - 2026-05-12
### "Federated Judiciary" Release: Consensus-Driven Governance & Forensic Resilience

### ⚖️ Added: Phase 1 - Federated M-of-N Consensus
- **Federated Quorum Logic:** Introduced the `ApprovalRequest` model with `min_approvals` support, requiring multiple human stakeholders to reach consensus before high-risk execution[cite: 11].
- **M-of-N Quorum Extraction:** Enhanced `ExecutiveAgent` and `HITLManager` to dynamically extract quorum requirements from the institutional policy manifest[cite: 11].
- **Threaded Slack Judiciary:** Implemented `message_ts` tracking in the `SlackJudiciaryAdapter` to support persistent, threaded voting within Slack channels[cite: 11].

### 🧠 Added: Phase 2 - Qualitative Semantic Guardrails
- **Semantic Alignment Judge:** Integrated a vector-based `SemanticGuard` that evaluates agent "Thoughts" against institutional mission statements and prohibited strategies[cite: 11].
- **Intent Alignment Scoring:** Implemented a similarity-threshold check (default 0.85) to block predatory or non-compliant reasoning before tool selection[cite: 11].

### 📡 Added: Phase 3 - Forensic Self-Healing (DLQ)
- **Local Dead Letter Queue (DLQ):** Developed a self-healing mechanism in `TelemetryManager` that automatically buffers forensic snapshots to `logs/audit_buffer.jsonl` if cloud sinks (AWS/Azure) are unreachable[cite: 11].
- **Execution Snapshot Hardening:** Expanded the `ExecutionSnapshot` schema to include `guards_evaluated`, ensuring a deterministic record of which triage stages (Fiscal, Semantic, Judiciary) were passed[cite: 11].

### 🛡️ Fixed: Privacy & Logic Integrity
- **Stage 0 Address Redaction:** Hardened the `PrivacyGuard` with a custom regex-based Pattern Recognizer to successfully scrub street-level PII (e.g., "123 Main St"), resolving an Article 9 compliance gap[cite: 11].
- **Safe Policy Accessors:** Refactored `CircuitBreaker` and `ExecutiveAgent` to use `getattr` for policy configuration, preventing `AttributeError` crashes during partial policy loads[cite: 11].
- **Indentation & Syntax:** Resolved critical indentation errors in the `ExecutiveAgent.evaluate` method that previously blocked institutional test suites[cite: 11].

---

## [0.4.0] - 2026-05-07
### "Sovereign Swarm" Release: Cloud-Native Governance & Recursive Fiscal Control

### 💸 Added: Phase 2 - Recursive Fiscal Sovereignty
- **Recursive TCO Tracking**: Introduced an institutional context that aggregates **Total Cost of Operation (TCO)** across parent and sub-agents, preventing "Budget Fragmentation" in complex swarms[cite: 11].
- **Shared Fiscal Metrics**: Implemented `get_shared_fiscal_metrics` and `update_shared_spend` to provide a single source of truth for financial ceilings across async threads[cite: 11].
- **Penny-Accurate Pricing**: Integrated a dedicated pricing engine in `telemetry.py` to calculate exact token costs before finalization[cite: 11].

### ☁️ Added: Phase 3 - Institutional Evidence (Cloud SOC)
- **Multi-Sink Dispatch**: Refactored `TelemetryManager.finalize` as an asynchronous engine capable of broadcasting forensic snapshots to multiple destinations simultaneously[cite: 11].
- **AWS CloudWatch Exporter**: Launched native integration for real-time log ingestion into AWS, supporting enterprise-grade security monitoring[cite: 11].
- **Azure Monitor Exporter**: Provided architectural support for Azure Data Collection Rules (DCR) for long-term regulatory record-keeping[cite: 11].
- **Mock Forensic Sink**: Developed a high-fidelity `MockSOCExporter` for local validation of telemetry dispatch without requiring cloud credentials[cite: 11].

### 🛡️ Added: Phase 1 - Structural Hardening
- **Article 9 Privacy Guard**: Integrated an automated **Stage 0** defense using Microsoft Presidio to redact PII (Personally Identifiable Information) before tasks reach the LLM[cite: 11].
- **Type-Safe Intent Validation**: Replaced regex-based extraction with **Pydantic V2 Schema Enforcement** in the tool registry to ensure deterministic integrity of all tool parameters[cite: 11].

### 🛠️ Fixed: Async Lifecycle & Finalization
- **Coroutine Resolution**: Patched `ExecutiveAgent.execute` to fully `await` all telemetry paths, resolving a critical `AttributeError` where audit reports were returned as unresolved coroutines[cite: 11].
- **Address Leakage Patch**: Hardened the `PrivacyGuard` with a regex-based "Safety Net" to ensure physical addresses (e.g., "123 Main St") are successfully captured as `LOCATION` entities[cite: 11].

---

## [0.3.0] - 2026-05-07
### Major Release: Institutional Scaling & Terminal Integrity

### 🏛️ Added: Invisible Governance Layer
- **Context-Aware Execution**: Implemented `contextvars` in `govagent.context` to track active `ExecutiveAgent` sessions across async threads, eliminating the need for global variables[cite: 11].
- **Unified Tool Decorator**: Introduced `@tool` in `govagent.registry` which automatically intercepts tool calls to perform governance evaluation via the active context[cite: 11].
- **Institutional Factory Pattern**: Added `ExecutiveAgent.bootstrap()` for one-line initialization of governed sessions, inclusive of policy loading and Slack adapter attachment[cite: 11].

### ⚖️ Added: Judiciary & Compliance Enhancements
- **Synchronous HITL**: Enhanced `HITLManager` and `SlackJudiciaryAdapter` to provide blocking, real-time human oversight for high-risk tools[cite: 11].
- **Article 9/14 Compliance**: Standardized tool manifests to ensure no "Shadow IT" tools can execute without explicit YAML authorization[cite: 11].

### 🛡️ Fixed: Loop & Terminal Stability
- **Terminal Transaction Logic**: Refactored `ExecutiveAgent.execute` loop to force a hard return after any `execute_financial_transaction`, preventing "Reasoning Loops" and duplicate approval requests[cite: 11].
- **Rejection Circuit Breaker**: Ensured that a **Human Judiciary Rejection** acts as a terminal event, instantly killing the agent loop and preventing Slack notification spam[cite: 11].
- **Indentation & Syntax Integrity**: Resolved logic errors in the reasoning loop that previously caused agents to ignore safety thresholds[cite: 11].

### ⚙️ Changed: Generic Architectural Pivot
- **Industry-Agnostic Schema**: Renamed specific tools (e.g., `healthcare_payment_tool`) to generic counterparts like `execute_financial_transaction` to support horizontal scaling across Fintech, Supply Chain, and Audit sectors[cite: 11].
- **Forensic Telemetry**: Updated `TelemetryManager` to log every stage of the cascading triage (Fiscal -> Policy -> Judiciary)[cite: 11].

---

## [0.2.3] - 2026-05-06
### Added
- **LangChain Integration Adapter**: Automated wrapper in `ExecutiveAgent` to standardize LangChain `ChatOpenAI` clients to the GovAgent contract[cite: 11].
- **Dynamic Intent Extraction**: Replaced hardcoded parameters with Regex-based extraction for `claim_id` and `amount` within the model adapter[cite: 11].
- **Self-Healing Telemetry**: Automatic creation of `/logs` directory and `audit_trail.jsonl` persistence[cite: 11].

### Changed
- **Modular Evaluation Engine**: Refactored `evaluate()` to follow a cascading triage: Fiscal (Cheap) -> Policy (Automated) -> Judiciary (High-Risk/HITL)[cite: 11].
- **HITL Interface**: Streamlined Slack context messages to provide "Executive Summaries" rather than raw LLM thought-logs[cite: 11].

### Fixed
- Resolved `NoneType` and `AttributeError` issues during agent initialization[cite: 11].
- Fixed namespace exports in `govagent.hitl` for `SlackJudiciaryAdapter`[cite: 11].

---

## [0.2.2] - 2026-05-05
### Added
- **LangChain Integration**: Standardized `@langchain_tool` bridging logic for GovAgent interception[cite: 11].
- **Socket Mode Support**: Transitioned Slack Judiciary to persistent Socket Mode for increased security[cite: 11].
- **Intent Serialization**: JSON-based serialization for tool inputs to ensure telemetry data integrity[cite: 11].

### Fixed
- **Validation Schema**: Resolved Pydantic string-type constraints in `ExecutionSnapshot`[cite: 11].
- **Registry Mapping**: Fixed namespace mismatches between Python tool decorators and YAML policy names[cite: 11].

---

## [0.2.0] - 2026-05-04 (Stable)

### 🏛️ Added: The Judiciary Pillar
* **Synchronous HITL Manager**: Introduced a core orchestration layer to manage Human-in-the-Loop (HITL) requests across multiple communication adapters[cite: 11].
* **Slack Socket Mode Adapter**: Implemented a real-time, mobile-first intervention bridge using secure WebSockets, enabling remote executive oversight without public endpoint exposure[cite: 11].
* **Stateful Execution Blocking**: Developed a mechanism using `asyncio.Future` patterns that physically pauses the agent's logic thread until a human "Approve" or "Reject" signal is received[cite: 11].
* **Interactive Block Kit UI**: Added rich, structured Slack message templates providing forensic context (Agent ID, Reason, Parameters) for executive decision-making[cite: 11].

### 🛠️ Improvements & Refactoring
* **EU AI Act Compliance**: Mapped code-level functionality to **Article 14 (Human Oversight)** and **Article 12 (Traceability)** requirements[cite: 11].
* **Legislative Registry Hardening**: Stabilized the `@tool` decorator to ensure strict type-safety and parity between Python signatures and YAML policy permissions[cite: 11].
* **Self-Healing Handshake**: Added intelligent detection for common Slack errors (e.g., `not_in_channel`) with automated join attempts where permitted by scopes[cite: 11].
* **Executive Audit Logging**: Interaction handlers now capture and log the specific Slack User ID of the human overseer to maintain the "Chain of Accountability"[cite: 11].

### 🛡️ Security & Integrity
* **Zero-Trust Identity**: Standardized the dual-token system using `SLACK_APP_TOKEN` (`xapp-`) for connection and `SLACK_BOT_TOKEN` (`xoxb-`) for privileged communication[cite: 11].
* **Thread-Safe Callbacks**: Integrated `loop.call_soon_threadsafe` to bridge background WebSocket threads with the main asynchronous execution loop[cite: 11].
* **Constitutional Startup Check**: Enhanced the boot-up sequence to refuse execution if tool code and policy permissions do not align[cite: 11].

---

## [0.1.7] - 2026-05-04

### 📜 Added: Legislative Tool Registry
* **Legislative Tool Registry**: Introduced the `@tool` decorator to auto-map Python functions to governance permissions[cite: 11].
* **Strict Risk Parity Audit**: Implemented `Policy.validate_registry()` to prevent "Risk Downgrading" between code and YAML[cite: 11].
* **Shadow Tool Prevention**: The system now halts at startup if a code-level tool is not explicitly authorized in the Policy YAML[cite: 11].
* **Interface Reflection**: Captures function signatures and docstrings for automated prompt engineering[cite: 11].

### 🛠️ Fixed
* **Policy Attribute Sync**: Standardized naming for `max_spend_usd` and `require_human_approval` to ensure internal Guard compatibility[cite: 11].
* **Cross-Walk Validation**: Resolved the gap where code and policy could drift out of alignment without triggering a failure[cite: 11].

---

## [0.1.6] - 2026-05-03

### ✅ Added
* **Hardened Core**: Implemented explicit Intent Validation and a Telemetry Contract[cite: 11].
* **Financial Circuit Breaker**: Real-time spend tracking and budget enforcement[cite: 11].
* **Path Independence**: Absolute resolution for Policies[cite: 11].

---

## [0.1.5] - 2026-05-03

### 🏛️ Added
* **Synchronous HITL Enforcement**: The agent now treats a human 'Reject' signal as a terminal event, physically breaking the execution loop[cite: 11].
* **Governance Test Suite**: Added `test_governance.py` to verify policy enforcement and guardrail reliability[cite: 11].
* **ExecutionSnapshots**: Enhanced telemetry reporting for forensic-grade audit trails[cite: 11].

### 🛠️ Changed
* **Loop Hardening**: Refactored `ExecutiveAgent` to prioritize governance checks over tool execution[cite: 11].
* **Telemetry Mapping**: Standardized attribute names (e.g., `reasoning_steps`) across the framework[cite: 11].

### 🛠️ Fixed
* **Bypass Resolution**: Fixed a critical bypass where the agent would continue execution after an intervention request was denied[cite: 11].