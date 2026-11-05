# GovAgent Phase 0 audit and architecture proposal

> The control plane is no longer in this public repository. `govagent-platform` is at https://github.com/thekakodkar/govagent-platform. Paths below that begin with `platform/` or `tests/platform/` describe the tree before that move.

Status: documentation only. This pull request does not change the `govagent` package, the FastAPI gateway, the Next.js UI, tests, or policies.

Audience: the maintainer deciding how an enterprise control plane should sit on the existing library.

Date of inspection: 2026-11-04. Repository HEAD at audit time: `00a19d6` on `main` (`feat(governance): integrate dynamic ERP cost center accounting, collapsible layout & multi-channel Slack HITL`).

## 1. Specification search

There is no document in this repository titled "GovAgent Master Implementation Specification", and no `spec/`, `design/`, or similarly named specification.

Searched locations:

- `README.md` (the fullest product description; it labels the tree "v3.0.2")
- `changelog.md` (release narrative from 0.1.5 through 3.0.0; it does not contain a 3.0.1 or 3.0.2 section)
- `docs/index.html` (marketing page, not a specification; it also contains unresolved merge conflict markers)
- `pyproject.toml`, `policies/*.yaml`, and module docstrings

This audit therefore uses `README.md` and `changelog.md` as the capability claims, and the Python, API, and UI source as the implementation evidence. Enterprise items that the README never specifies (operator tenancy, authentication, a system of record) are called out as gaps against the enterprise build-out, not as missing sections of a spec that was found.

`docs/index.html` still contains conflict markers (`<<<<<<< HEAD` through `>>>>>>> 9665645f...`) and sample code that imports `Governor`, `AgentWorkflow`, and `GuardrailBoundary`. Those names do not exist anywhere under `src/govagent`. The page also disagrees with itself on the published version (`v3.0.2`, `v3.0.0`, and `pip install govagent==1.0.0` all appear inside the conflict).

## 2. Repository and package structure

The repository is a library plus an unpublished application shell.

| Path | Role | Shipped in the `govagent` wheel? |
| --- | --- | --- |
| `src/govagent/` | Importable library. Poetry packages only this tree (`packages = [{ include = "govagent", from = "src" }]`). | Yes |
| `api/server.py` | FastAPI gateway. Not a `govagent` submodule. | No |
| `src/app/` | Next.js App Router UI (`page.tsx`, `layout.tsx`, `components/CFOExecutivePanel.tsx`). | No |
| `policies/` | YAML manifests consumed by path. | No |
| `examples/` | Demos. | No |
| `tests/` | Pytest suite. | No |
| `utility/slack_diagnostic.py` | Manual Slack diagnostic. | No |
| `docs/index.html` | Static marketing page. | No |
| `docker-compose.yml` | Compose file for an API container and a dashboard container. | No |
| `package.json` | Next.js app at the repository root (`govagent-ui`). | No |

Library modules that exist today:

- `src/govagent/__init__.py` re-exports `ExecutiveAgent`, `Policy`, `tool`, `registry`, `get_current_agent`, and the LLM router types.
- `src/govagent/agent.py` — `ExecutiveAgent`.
- `src/govagent/policy.py` — YAML `Policy`.
- `src/govagent/pricing.py` — `PricingEngine`.
- `src/govagent/context/` — `contextvars` session and fiscal ledger.
- `src/govagent/guards/` — `CircuitBreaker`, `PrivacyGuard`, `SemanticGuard`.
- `src/govagent/hitl/` — `HITLManager`, `CLIAdapter`, `SlackJudiciaryAdapter`.
- `src/govagent/llm/` — `BaseLLMClient`, `OllamaClient`, `PolicyBasedRouter`.
- `src/govagent/registry/` — two different registry implementations (see drift and capability map).
- `src/govagent/telemetry/` — `TelemetryManager`, cloud and federated exporters.
- `src/govagent/governance/` — `MetaGovernor`, plus repo-only `EvidencePackGenerator` and `CFOAnalyticsEngine`.
- `src/govagent/extensions/crewai/enforcer.py` — `GovAgentEnforcer`.
- `src/govagent/extensions/ibm/bob_mcp_proxy.py` and `watsonx_bus.py`.

Documented paths that are not in the tree:

- `Dockerfile` is referenced by `docker-compose.yml` and is absent.
- `dashboard/` is the compose `working_dir` for the web container and is absent. The UI lives at `src/app` with `package.json` at the repo root.
- `src/govagent/extensions/crewai/compliance.py` and the extension `__init__.py` files described in the README project tree are absent. `src/govagent/extensions/__init__.py` exists and is empty.
- `.github` is an empty file, not a workflows directory. The README's GitHub Actions check is not present.
- `policies/audit_buffer.jsonl` is listed in the README and gitignored. Runtime buffers under `logs/` are also gitignored.

`pyproject.toml` version is `3.0.2`. Python requirement is `>=3.10,<3.14`. FastAPI and Uvicorn are dev dependencies, not runtime dependencies of the wheel. `opentelemetry-api` is a runtime dependency and is not imported anywhere under `src/`.

## 3. Test suite

### Environment

From a clean checkout, with Poetry installed and `~/.local/bin` on `PATH`:

```bash
poetry install --with dev --extras "crewai enterprise" --no-interaction
poetry run python -m spacy download en_core_web_lg
poetry run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
poetry run pytest -v --tb=short --asyncio-mode=auto
```

Interpreter: Python 3.12.3. Virtualenv created by Poetry: `govagent-xS3fZVNL-py3.12`. Resolved test tools: pytest 9.1.1, pytest-asyncio 1.4.0.

`en_core_web_lg` is required because `PrivacyGuard` constructs Presidio's `AnalyzerEngine()`, whose default configuration requests that model (`presidio_analyzer` `nlp_engine_provider`, model `en_core_web_lg`). The README's quickstart downloads `en_core_web_sm`, which does not satisfy that default. `all-MiniLM-L6-v2` is loaded by `SemanticGuard` whenever an `ExecutiveAgent` is constructed. The `enterprise` extra supplies `sentence-transformers`; the `crewai` extra supplies the adapter tests. The `langchain` extra is not required by the current suite.

A later spot check of `tests/test_telemetry.py` and `tests/test_meta_governor.py` also passed without `--asyncio-mode=auto`. The full-suite command above is the one that produced the counts in this report.

### Result

```text
collected 22 items
21 passed, 1 skipped, 25 warnings in 34.39s
```

Failures: none.

Skip (1):

| Test | Cause |
| --- | --- |
| `tests/test_slack_hitl.py::test_slack_interaction` | Skipped by the test itself when `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and `SLACK_CHANNEL_ID` are all unset. Message in source: `Skipping Slack integration test: Credentials missing from .env`. No `.env` is present in the checkout (`.env` is gitignored). |

Warnings (not failures):

- Starlette deprecation: FastAPI `TestClient` importing `httpx` (`fastapi/testclient.py`).
- CrewAI deprecations for `function_calling_llm`, `allow_code_execution`, and `reasoning` while the adapter tests construct agents.
- `datetime.utcnow()` in `src/govagent/telemetry/exporters/federated.py` (line 18) and `src/govagent/governance/meta.py` (line 16).

The 21 passing tests exercise guards, the fiscal context, trace inheritance, the public registry schema check, the Harbor registry in `registry/manager.py`, IBM wrappers with a mock semantic guard, MetaGovernor log parsing, weighted HITL with a mock adapter, federated exporter routing, telemetry dispatch to a mock exporter, the CrewAI enforcer's tool gate, and the FastAPI gateway's auth, keyword block, and in-memory Slack callback.

Passing tests do not prove that YAML policy sections are bound into the agent. `tests/test_governance.py::test_recursive_tco_ceiling_breach` passes because `Policy` falls back to a top-level `global_limits` default whose daily budget is `10.0`, and `90 + 20` exceeds that default. `tests/test_api_endpoints.py::test_api_semantic_guard_block` passes because the task string contains the keyword `bypass`, which `api/server.py` treats as prohibited. See the capability map.

## 4. PyPI versus repository

Latest release on PyPI: **govagent 3.0.2**, uploaded 2026-07-07 (`govagent-3.0.2-py3-none-any.whl`, sha256 prefix `2c255bf73eed9165`; sdist `govagent-3.0.2.tar.gz`). The project has published releases from 0.1.0 through 3.0.2. Nothing newer than 3.0.2 is on PyPI. The release is not yanked.

### Metadata

Wheel metadata matches `pyproject.toml` for name, version `3.0.2`, MIT license, summary, author, `Requires-Python: >=3.10,<3.14`, keywords, extras (`crewai`, `langchain`, `enterprise`), and the dependency set (including optional extras). Warehouse adds the usual `Programming Language :: Python :: 3.10` through `3.13` classifiers from the Python requirement; `pyproject.toml` lists only the generic Python 3 classifier. Project URLs match. This is metadata alignment, not source alignment.

The wheel's long description is `README.md` from publish time. The current README differs by the leading logo image and a trailing blank line. Republishing without a version bump would change the PyPI description while keeping version `3.0.2`.

### What the wheel contains

The wheel is only the `govagent` package (37 Python modules) plus license and metadata. It does not contain `api/`, `src/app/`, `tests/`, `examples/`, `policies/`, or compose files. That exclusion matches the Poetry package configuration. A `pip install govagent` user does not get the gateway or the dashboard described in the README quickstart.

### Source drift at the same version number

After normalising CRLF (the wheel) to LF (the repository), **every published module matches the repository except two**, and the repository has **two modules the wheel does not contain**.

| Item | PyPI 3.0.2 | Repository HEAD (still version 3.0.2) |
| --- | --- | --- |
| `src/govagent/registry/__init__.py` | Re-exports `GlobalRegistry` and `tool` from `registry/manager.py`, then creates the singleton `registry`. Public `tool` is the Harbor-aware decorator (`name`, `risk_level`, `oci_repository`, `artifact_digest`). | Defines a second `GlobalRegistry` and a second `tool` decorator. Does not import `manager.py`. Adds `FinancialTransactionIntent`. `validate_intent_schema` returns `True` or raises. `validate_against_policy` raises `PermissionError`. |
| `src/govagent/registry/schemas.py` | `ToolManifest` plus `ExecutionSnapshot` with required `output: Any`. | Adds `FinancialTransactionIntent`. `ExecutionSnapshot.output` is optional. Adds optional forensic and ERP fields (`selected_model`, `recursive_tco_usd`, `cost_center`, `gl_account`, `requested_exposure_usd`, `total_tokens`, and others). |
| `src/govagent/governance/cfo_analytics.py` | Absent. | Present. Not exported from `governance/__init__.py` (`__all__` is only `MetaGovernor`). |
| `src/govagent/governance/evidence.py` | Absent. | Present. Same export gap. Used by `api/server.py`. |

All other library files are byte-identical once line endings are normalised, including `agent.py`, guards, HITL, telemetry, extensions, and `governance/meta.py`.

### Public API drift that matters

`from govagent import tool, registry` is part of `govagent.__all__` in both trees, but it binds to different objects:

- On PyPI 3.0.2, `registry` is `manager.GlobalRegistry`, a process singleton with `verify_and_resolve_tool`. The decorator registers a `ToolManifest` and Harbor coordinates.
- On this repository, `registry` is the new class in `registry/__init__.py`. Harbor verification remains on `govagent.registry.manager.GlobalRegistry`, which the package `__init__` no longer wires up. `from govagent.registry.manager import tool` still reaches the published decorator, which is why `tests/test_harbor_registry.py` passes. `from govagent import tool` does not.

`FinancialTransactionIntent` is importable from `govagent.registry` in this tree and is not in the published wheel.

`ExecutionSnapshot` is two classes in both trees:

- `govagent.telemetry.manager.ExecutionSnapshot` (session record used by `TelemetryManager`)
- `govagent.registry.schemas.ExecutionSnapshot` (the one `ExecutiveAgent._finalize` and `api/server.py` construct)

The schema class grew optional fields in the repository. Old constructors that pass `trace_id`, `status`, `output`, and `metrics` still satisfy the new model. Publishing those additions under version `3.0.2` would still be a content change of a release that already exists.

There is a second, silent behaviour change if the repository registry is published as a patch: `tool(..., oci_repository=..., artifact_digest=...)` still accepts the keyword arguments via `**kwargs`, and then drops them. Callers would not get a `TypeError`. Harbor gating on the public decorator would disappear.

### README samples that do not match either tree

These samples are documentation drift against both the wheel and HEAD:

- `RoutingMode.LOCAL_PREFERRED` is not an enum member. `src/govagent/llm/router.py` defines `LOCAL_ONLY`, `CLOUD_ONLY`, and `HYBRID`.
- `ExecutiveAgent(persona=..., policy_path=..., router=...)` does not match `__init__`, which requires a `Policy` instance and a `router`. The factory is `ExecutiveAgent.bootstrap(policy_path, router_client, slack_channel=None)`.
- `docs/index.html` shows `agent.run(...)`. The method is `execute`.
- The README quickstart runs `docker-compose exec govagent-api poetry run python examples/basic_demo.py` and opens `http://localhost:3000`. Compose builds a missing `Dockerfile` and starts Node in a missing `/app/dashboard` directory.

## 5. Capability map

Status words mean:

- **Implemented** — the behaviour described in the README exists in code and is on the path a caller actually hits.
- **Partial** — a real component exists, and a material part of the claim is unbound, mocked, or only true for one entry point.
- **Stub** — the type or endpoint exists and the body does not do the claimed work.
- **Missing** — no implementation.

| Claim (README / changelog) | Status | Where it actually lives |
| --- | --- | --- |
| Stage 0 privacy redaction with Presidio and a street-address recogniser | Implemented in the library; partial at the gateway | `src/govagent/guards/privacy.py` `redact_task`. `ExecutiveAgent.execute` calls it. `api/server.py` assigns `sanitized_task = payload.task_input` and never calls `PrivacyGuard`. |
| Stage 1 semantic intent alignment with sentence-transformers | Partial | `src/govagent/guards/semantic.py` scores the prompt against `prohibited` strings and returns `0.0` over the threshold. `CircuitBreaker.evaluate` does not call it; it only runs `check_financial_risk`. `ExecutiveAgent` builds `SemanticGuard` from `getattr(policy, "alignment", {})`, but `Policy` stores `alignment` inside `self.config` and never sets `self.alignment`, so a normal YAML load produces an empty prohibited list and `evaluate_alignment` returns `1.0`. The gateway blocks a hard-coded keyword list (`bypass`, `exploit`, and others) in `api/server.py`. |
| Stage 2 fiscal ceilings and recursive TCO | Partial | In-process ledger: `src/govagent/context/fiscal_ledger.py`. Breaker: `src/govagent/guards/circuit_breaker.py`, which reads `policy.global_limits.recursive_tco_ceiling` and `daily_budget_usd`. YAML files put ceilings under `fiscal_governance.global_limits` and name the swarm cap `recursive_tco_limit` (`policies/finance_policy.yaml`). `Policy.__init__` reads only a top-level `global_limits` key, so those YAML values are not the numbers the breaker uses. The gateway uses a separate regex-and-keyword path and `MODEL_RATES` in `api/server.py`. |
| Penny-accurate pricing engine | Partial | `src/govagent/pricing.py` `PricingEngine.calculate_cost`. `ExecutiveAgent` reads `response.raw_usage["estimated_cost_usd"]`, which `OllamaClient` does not set. `WatsonxOrchestrateBusSync` looks for a module-level `pricing.calculate_cost`, which does not exist, and then uses `fallback_rate_per_token`. The gateway has a third rate table. |
| Central tool legislation, shadow-tool startup failure, and execution of the legislated function | Partial | Two registries, described in section 4. `Policy.validate_registry` consults whichever object `govagent.registry.registry` is. On HEAD that object raises `PermissionError` for unknown tools. `manager.GlobalRegistry.validate_against_policy` only prints. `ExecutiveAgent.perform_action` does not call either registry; it returns `Action {action} executed with params {params}` (`agent.py`). |
| Harbor OCI signature and CVE verification | Stub | `src/govagent/registry/harbor_verifier.py`. Default token is `mock-token`. The mock path returns verified unless the repository string contains `malicious`. Any other token returns `PRODUCTION_BYPASS` without an HTTP call to Harbor. The gateway constructs `HarborVerifier` and then returns the constant digest `sha256:e3b0c442...` and `harbor_status="VERIFIED"` (`api/server.py`). |
| Pluggable LLM router and local Ollama | Implemented for Ollama; partial as a multi-provider fabric | `src/govagent/llm/router.py`, `src/govagent/llm/ollama.py`. `LOCAL_ONLY` and `CLOUD_ONLY` both return `default_provider`. There is no OpenAI or Anthropic client in the package. The `langchain` extra declares libraries and no adapter module imports them. |
| CrewAI one-line enforcer | Partial | `src/govagent/extensions/crewai/enforcer.py`. It patches `Agent.execute_task` on the CrewAI class (process-global), enforces `governance_rules.authorized_tools`, and redacts via `PrivacyGuard`. During execution it replaces the routed client's `generate` with an inline mock that returns a fixed string. Semantic stage 1 is a keyword check for `payroll` / `ledger` / `confidential`, not `SemanticGuard`. |
| IBM Bob MCP proxy | Partial | `src/govagent/extensions/ibm/bob_mcp_proxy.py` wraps a Python callable. It does not speak MCP. It calls `privacy_guard.anonymize`, while `PrivacyGuard` exposes `redact_task`, so the privacy hook logs a warning and continues unless the caller passes a different object. |
| watsonx Orchestrate cost bus | Partial | `src/govagent/extensions/ibm/watsonx_bus.py` maps a usage dict into `update_shared_spend`. It does not call watsonx. |
| Thread-safe parent/child trace propagation | Implemented in-process | `src/govagent/context/session.py` and `TelemetryManager.start_trace`, which copies `parent_trace_id` from `get_current_agent()`. This is a `contextvars` value. It does not cross processes, workers, or restarts. |
| Federated multi-sig judiciary, role weights, veto | Implemented in the library; stub at the gateway | Weights and tiers live in `src/govagent/hitl/manager.py` (C-Suite 3.0 through Clerk 0.5; amount thresholds 1000 and 5000). Slack Socket Mode voting is `src/govagent/hitl/slack_adapter.py`. `CLIAdapter.notify` returns a bool, which the manager treats as a legacy approval. The gateway does not call `HITLManager`. It posts a Slack message when tokens exist and stores `PENDING` in the process-global dict `LIVE_TRANSACTION_STATES`. `GET /api/v1/slack/callback` is unauthenticated and sets `APPROVED` or `VETOED` for any `trace_id`. |
| Self-healing MetaGovernor proposals | Partial | `src/govagent/governance/meta.py` reads a JSONL file and returns a `POLICY_AMENDMENT_PROPOSAL` after three TCO/fiscal block lines. It does not write the YAML. `ExecutiveAgent.post_session_cleanup` is never called from `execute`. Default log path is `logs/audit_trail.jsonl`. The telemetry dead-letter path and the evidence pack read `logs/audit_buffer.jsonl`. |
| Article 12 telemetry, CloudWatch, Azure, local DLQ | Partial | `src/govagent/telemetry/manager.py` fans out to exporters and appends to the buffer path only when an exporter raises. With no exporters, finalize keeps the snapshot in memory. `CloudWatchExporter` and `AzureMonitorExporter` construct cloud clients in `__init__`, so import-and-construct fails closed without credentials. `FederatedTelemetryExporter` (`telemetry/exporters/federated.py`) routes by `organization_id` to an in-memory sink list and logs the route. Unregistered orgs return `False`. Default org id is `GLOBAL_HOLDING`. |
| EU AI Act evidence dossier and CFO rollup | Partial, and unpublished | `src/govagent/governance/evidence.py` hashes a dossier from `logs/audit_buffer.jsonl`. `src/govagent/governance/cfo_analytics.py` aggregates in-memory snapshots. The gateway calls both. The evaluate path records CFO snapshots in memory and does not append the JSONL the dossier reads, so an export of a fresh process is an empty sealed dossier. Neither module is in the 3.0.2 wheel. `governance/__init__.py` does not export them. |
| FastAPI control plane and long-polling dashboard | Partial | Gateway: `api/server.py` routes listed below. UI: `src/app/page.tsx` and `src/app/components/CFOExecutivePanel.tsx`. The UI loads policies, posts evaluate, exports a dossier, and the CFO panel polls `/financials/risk-overview` every 5 seconds. Nothing under `src/app` calls `/api/v1/governance/state/{trace_id}`. The README's 2 second PENDING long-poll is not in the current page. |
| OpenTelemetry | Missing | Declared in `pyproject.toml`. No import under `src/` or `api/`. |
| Autonomous cross-swarm delegation and zero-knowledge privacy guards | Missing | Listed under "Future Strategic Roadmap" in the README. No modules. |
| Multi-tenant enterprise control plane | Missing beyond an organisation id on a log envelope | The only tenancy primitive is `organization_id` on `FederatedAuditPayload`. There is no tenant directory, no membership, no policy store, and no database. |

Gateway routes in `api/server.py`:

| Route | Auth | Behaviour |
| --- | --- | --- |
| `GET /api/v1/governance/policies` | Bearer | Loads every `policies/*.yaml` through `Policy.from_yaml`. Spend cap extraction looks at `Policy.__dict__`, not `config["fiscal_governance"]`, and usually falls through to `2000.00`. |
| `POST /api/v1/governance/evaluate` | Bearer | Builds `ExecutiveAgent` with `router=None` (so `execute` is never used; the constructor still loads the embedding model) and then runs the keyword / amount heuristic. |
| `GET /api/v1/governance/state/{trace_id}` | None | Reads `LIVE_TRANSACTION_STATES`. Unknown ids return `PENDING`. |
| `GET /api/v1/slack/callback` | None | Writes `APPROVED` or `VETOED` into that dict. |
| `GET /api/v1/governance/compliance/export` | Bearer | `EvidencePackGenerator.generate`. |
| `GET /api/v1/governance/financials/risk-overview` | Bearer | `CFOAnalyticsEngine.analyze`. |

The bearer token defaults to `gov-secret-key-100x` when `GOVAGENT_SECRET_TOKEN` is unset (`api/server.py`). The same default is compiled into the UI as `NEXT_PUBLIC_GOVAGENT_TOKEN` (`src/app/page.tsx`, `CFOExecutivePanel.tsx`). CORS is `allow_origins=["*"]` with credentials enabled.

## 6. What to reuse, and what not to copy

The enterprise plane should import these types and keep their algorithms. Reimplementing them would fork the product the README already ships.

Reuse as-is for single-request library behaviour:

- `PrivacyGuard.redact_task` (`guards/privacy.py`)
- `SemanticGuard.evaluate_alignment` (`guards/semantic.py`), once a caller actually passes the prohibited list
- `CircuitBreaker.check_financial_risk` and `GovernanceViolation` (`guards/circuit_breaker.py`)
- `FiscalStateSnapshot` and `update_shared_spend` / `get_shared_fiscal_metrics` / `reset_fiscal_ledger` (`context/fiscal_ledger.py`) for the life of one task
- `set_current_agent` / `get_current_agent` (`context/session.py`) for parent trace inheritance inside that task
- `HITLManager.secure_approval` and `ApprovalRequest` (`hitl/manager.py`) for weight math
- `SlackJudiciaryAdapter` for Socket Mode delivery, behind a tenant-owned token reference
- `Policy.from_yaml` and `Policy` as the in-memory view of one policy document (`policy.py`)
- `PricingEngine` (`pricing.py`) as the single calculator the facade should call
- `BaseExporter` and the existing exporter classes (`telemetry/exporters/`)
- `MetaGovernor.analyze_friction` as a proposal generator over stored block rows
- `EvidencePackGenerator` and `CFOAnalyticsEngine` as report builders over stored rows
- `OllamaClient` and `PolicyBasedRouter` for local routing
- `BobMCPProxyGateway.govern_mcp_tool` and `WatsonxOrchestrateBusSync.process_watsonx_generation_metric` as optional edges, not as the tenancy model
- `HarborVerifier.verify_tool_artifact` once a real Harbor client replaces the mock; the manifest fields `oci_repository` and `artifact_digest` are already on `ToolManifest`

Extend, do not wrap with a second copy:

- `Policy` needs the nested YAML (`fiscal_governance`, `alignment`, `oversight`, `financial_accounting`, `infrastructure`) projected onto the attributes the guards already read. That projection is a behaviour change for every current caller of `Policy`. It waits on the compatibility gate in the Phase 1 plan.
- `TelemetryManager.finalize` needs a durable sink. The extension point that already exists is `add_exporter`. A platform exporter should implement `BaseExporter.export`, not a new telemetry stack.
- `FederatedTelemetryExporter.register_organization_sink` is the seed of per-tenant sink routing. Its `organization_id` should become the platform `tenant_id`. The class today only logs. Extend it, or adapt it, when sinks are real. Do not invent a parallel federated exporter.

Do not reuse as the multi-tenant store:

- `manager.GlobalRegistry` is a process singleton (`registry/manager.py`, `__new__`). One tenant's `@tool` registration is visible to every tenant in the process.
- The HEAD `registry` object is also one module-level instance.
- `LIVE_TRANSACTION_STATES` in `api/server.py` is one dict for the process, with no tenant key.
- `CFOAnalyticsEngine.snapshots` and `EvidencePackGenerator`'s JSONL file are process-global.
- `GovAgentEnforcer` assigns `Agent.execute_task` on the CrewAI class. That patch is process-global.
- `contextvars` fiscal state is the right isolation for one asyncio task and the wrong system of record across requests, workers, and restarts.

`api/server.py` should stay the demo gateway it is. The enterprise API should be a new application that calls the library. Growing the heuristic evaluate path would duplicate `CircuitBreaker`, `SemanticGuard`, and `HITLManager`, which already exist.

## 7. Missing enterprise functionality

The README describes one operator, one policy directory, one Slack workspace, and optional cross-org log routing. It does not specify a tenant control plane. The gaps below are what that enterprise build-out still has to add, given the code that exists.

| Area | What exists | What is missing |
| --- | --- | --- |
| Multi-tenancy | `organization_id` on a telemetry envelope; in-memory sink map | Tenant lifecycle, quotas, data isolation, and a tenant id on every persisted row |
| Authentication | One shared bearer string | User authentication, session or token issuance, rotation, and a path that does not put the token in a `NEXT_PUBLIC_` bundle |
| Authorization | HITL voter-role strings on a Slack button | A permission catalog, membership, and checks on every admin and runtime route |
| RBAC | Hard-coded weights in `HITLManager` | Roles that an operator or a tenant admin can assign; separation of platform roles from tenant roles |
| Audit logging | JSONL buffers, Python logs, an in-memory CFO list, a hash over a dossier | Append-only audit of admin actions and of evaluations, with actor, tenant, and before/after |
| Persistence | Files and process memory | A database, migrations, and retention |
| API layer | Demo FastAPI app outside the wheel | A versioned admin and runtime API with tenant context, pagination, and error model |
| Observability | `logging` and `print`; unused `opentelemetry-api` dependency | Traces, metrics, and health that follow `trace_id` and `tenant_id` |
| Config and secrets | `.env`, hard-coded default token, Harbor robot token default `mock-token` | Per-tenant secret references, no secrets in the database row or the browser bundle |
| Deployment | `docker-compose.yml` pointing at a missing Dockerfile and a missing `dashboard/` directory; empty `.github` file | An image, a database, migrations on boot, and CI that runs the suite |
| Policy administration | YAML files on disk, parsed loosely | Versioned global floor and tenant overlay, with a record of who activated which version |
| Identity for the judiciary | Slack user id captured when Socket Mode is used | A binding from Slack (or any IdP) user to a tenant membership so a weight cannot be self-asserted from a button `action_id` |

## 8. Target architecture

The library stays the governance engine. A new control plane, in a separate package, owns tenants, identity, and durable records, and calls the library for evaluation.

Principles:

1. `src/govagent` remains the published library. Enterprise modules are not added to `[tool.poetry] packages` for the `govagent` distribution.
2. The control plane imports `govagent`. It does not copy guards, the ledger, HITL weight math, or exporters.
3. One request builds one `Policy`, one `CircuitBreaker`, and one `ExecutiveAgent` from persisted documents and discards them at the end of the request. It does not register tools on the process-global registry.
4. Tenant id is a database key and a Postgres setting. It is not a new required field on the published `ExecutionSnapshot` models.
5. The existing `api/server.py` demo keeps its current routes until the owner accepts a compatibility change. The new API uses a different process and a different URL prefix (`/platform/v1`, `/tenant/v1`).

Component responsibilities:

- **Identity and RBAC.** Authenticate a person, resolve platform scope or exactly one tenant membership, and authorise a permission.
- **Policy service.** Store policy documents. On use, build a `govagent.policy.Policy`. Enforce the global floor before the tenant overlay is saved.
- **Runtime facade.** For an execution request, open a transaction, set the tenant, rehydrate the fiscal opening balance from `fiscal_ledger_entries`, call the existing guards and `ExecutiveAgent`, then persist the snapshot through a `BaseExporter` and append `audit_events`. Phase 1 does not have to finish the facade. The boundaries above are the ones Phase 2 must keep.
- **Audit writer.** Insert-only table. Application role has no update or delete on it.
- **Secret references.** Rows store a purpose and a locator (`env:SLACK_BOT_TOKEN_TENANT_X` or a vault path). They do not store the secret.
- **Library callers.** `import govagent` from an application that has no control plane keeps working. Those callers are single-tenant by definition, which is the library's current contract.

The diagrams are in [diagrams/target-architecture.md](diagrams/target-architecture.md).

## 9. Platform administration and tenant administration

Two actor scopes share one control plane and one database. They do not share permissions.

**Platform administration** is the operator of the service. The actor has `app.actor_scope = platform` and no implicit right to read a tenant's task text. Operators can:

- create, suspend, and resume tenants
- assign a plan (agent quota, monthly TCO ceiling, retention, feature flags)
- publish the global policy floor (the minimum guard set, the minimum semantic threshold, the maximum fiscal ceiling a tenant is allowed to grant itself, required Article 12 retention)
- manage operator accounts and operator roles
- read cross-tenant **metadata** required to run the service (tenant id, plan, status, aggregate spend, health)
- perform break-glass access to a tenant payload, which writes an `audit_events` row with reason and expiry

Operators cannot:

- weaken a tenant policy below the floor without a new floor version
- cast a tenant HITL vote
- register a tool inside a tenant

**Tenant administration** is a membership in exactly one tenant. Tenant admins can:

- invite identities and assign tenant roles
- author tenant policy documents that only tighten the active floor (lower spend cap, larger quorum, extra prohibited strategies, extra required guards)
- create agents bound to one active tenant policy
- legislate tools for that tenant, including optional OCI coordinates
- set the HITL roster, role weights, and risk tiers for that tenant, starting from the library defaults in `HITLManager.voter_weights`
- configure telemetry sink locators and cost centers
- read audit events and execution snapshots for their tenant

Tenant admins cannot:

- see another tenant's rows (the database denies it, not only the API)
- change their plan, retention below the plan, or the global floor
- create operator accounts

Suggested permission names, used by both the API and the seed migration:

Platform: `platform.tenants.read`, `platform.tenants.write`, `platform.plans.write`, `platform.policies.write`, `platform.audit.read_meta`, `platform.break_glass`.

Tenant: `tenant.users.write`, `tenant.roles.write`, `tenant.policies.write`, `tenant.agents.write`, `tenant.tools.write`, `tenant.hitl.configure`, `tenant.sinks.write`, `tenant.audit.read`, `tenant.runtime.evaluate`.

A person may hold memberships in several tenants. Each request names one tenant, and the membership is checked before `app.tenant_id` is set. Platform scope is a different credential path, not a membership with a null tenant.

HITL weights stay in `HITLManager`. The control plane's job is to pass a roster the membership store actually contains, so a Slack `action_id` of `approve_Director` cannot mint a Director weight for an identity that does not hold that role in the tenant.

## 10. Database schema and tenant isolation

### Options

| Strategy | How isolation is achieved | Operational shape | Fit for this codebase |
| --- | --- | --- | --- |
| Shared schema, `tenant_id` on each row, Postgres row-level security | The application role cannot see a row whose `tenant_id` differs from `current_setting('app.tenant_id')`. Policies are `FORCE ROW LEVEL SECURITY`. | One database, one migration stream, one pool. Platform queries are an explicit second policy on metadata tables. | Matches a library that is still a single process with no database. Tenant count for an early control plane is the number of customers on one deployment. |
| Schema per tenant | Each tenant has a schema. `search_path` selects it. | A migration must run once per tenant schema. Pooling and cross-tenant operator queries become catalog work. | Stronger namespace separation. Expensive before the product has a tenant record at all. |
| Database per tenant | Each tenant has a database and credentials. | Backups, migrations, and connection management scale with tenants. | Matches a later contractual data-residency sale. It is a poor default for the first control plane, which also needs operator-level plans and a global policy floor. |

### Recommendation

Use **one shared schema, `tenant_id` on every tenant-owned row, and forced row-level security**.

Reasons:

1. The library has no persistence. The first system of record should be one place the control plane can migrate.
2. Platform administration (plans, the global floor, operator audit) is naturally cross-tenant. A shared catalog serves that without a second storage engine.
3. Application bugs that forget a `WHERE tenant_id = ...` still return no foreign rows when RLS is forced and the application role does not own the tables or have `BYPASSRLS`.
4. The current `organization_id` string on `FederatedAuditPayload` maps onto `tenant_id` without a second tenancy concept.
5. Schema-per-tenant and database-per-tenant solve residency and noisy-neighbour problems the README's sovereign positioning may need later. They do not need to be the first isolation mechanism.

Reserve the choice. `tenants.isolation_tier` is `shared` for every row Phase 1 creates. Later promotion to `dedicated_schema` or `dedicated_db` is a backlog item. The API does not branch on it until that item is built.

### Session contract

The application connects as role `govagent_app` (`NOBYPASSRLS`, not the table owner).

At the start of every transaction:

```sql
BEGIN;
SELECT set_config('app.actor_scope', 'tenant', true);  -- or 'platform'
SELECT set_config('app.tenant_id', '<uuid>', true);    -- empty for platform metadata calls
```

`set_config(..., true)` is transaction-local, so a pooled connection cannot leak the setting. After `COMMIT` or `ROLLBACK` the setting is gone.

Tenant policies on tenant-owned tables. `NULLIF` avoids casting an empty setting to `uuid`, which would abort the statement when a platform session has no tenant selected:

```sql
CREATE POLICY tenant_isolation ON <table>
  USING (
    (
      current_setting('app.actor_scope', true) = 'platform'
      AND current_setting('app.platform_break_glass', true) = 'on'
    )
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  )
  WITH CHECK (
    tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  );
```

Platform reads of tenant **payload** tables require `app.platform_break_glass = on`, which the API sets only inside a break-glass grant that has already been written to `audit_events`. Ordinary operator list calls use catalog tables (`tenants`, `plans`) that have their own policies and do not contain task text.

`audit_events` allows `INSERT` for the current tenant and for platform scope. It does not allow `UPDATE` or `DELETE` to `govagent_app`.

### Tables and columns

Primary keys are UUID. Timestamps are `timestamptz`. JSON documents are `jsonb`.

`plans`

- `id`, `code` unique, `name`, `max_agents`, `monthly_tco_ceiling_usd`, `retention_days`, `features jsonb`, `created_at`

`tenants`

- `id`, `slug` unique, `display_name`, `status` (`active`, `suspended`), `plan_id` FK, `isolation_tier` (`shared` only in Phase 1), `region`, `created_at`, `suspended_at`

`identities`

- `id`, `email` unique, `display_name`, `password_hash` nullable, `external_subject` nullable, `status`, `created_at`

`platform_role_bindings`

- `identity_id` FK, `role_id` FK, `created_at`
- primary key (`identity_id`, `role_id`)

`tenant_memberships`

- `tenant_id` FK, `identity_id` FK, `status` (`invited`, `active`, `revoked`), `created_at`
- primary key (`tenant_id`, `identity_id`)

`roles`

- `id`, `scope` (`platform` or `tenant`), `tenant_id` nullable FK, `code`, `is_system`
- unique (`scope`, `tenant_id`, `code`)

`role_permissions`

- `role_id` FK, `permission`
- primary key (`role_id`, `permission`)

`membership_roles`

- `tenant_id`, `identity_id`, `role_id`, `created_at`
- primary key (`tenant_id`, `identity_id`, `role_id`)
- FK to `tenant_memberships`

`global_policies`

- `id`, `version` unique integer, `document jsonb`, `checksum`, `status` (`draft`, `active`, `retired`), `activated_at`, `created_by` FK identities

`tenant_policies`

- `id`, `tenant_id` FK, `name`, `document jsonb`, `floor_version` integer, `checksum`, `status` (`draft`, `active`, `retired`), `created_by`, `created_at`
- one active row per tenant in Phase 1 (partial unique index)

`agents`

- `id`, `tenant_id` FK, `name`, `persona`, `policy_id` FK `tenant_policies`, `status`, `created_at`
- unique (`tenant_id`, `name`)

`tool_manifests`

- `id`, `tenant_id` FK, `name`, `description`, `risk_level`, `requires_approval`, `param_schema jsonb`, `oci_repository`, `artifact_digest`, `created_at`
- unique (`tenant_id`, `name`)
- these columns match `ToolManifest` in `src/govagent/registry/schemas.py` so the facade can build that model without a second schema

`approval_requests`

- `id`, `tenant_id` FK, `agent_id` FK, `trace_id`, `risk_tier`, `required_score`, `status`, `context jsonb`, `created_at`, `resolved_at`

`approval_signatures`

- `id`, `tenant_id` FK, `request_id` FK, `identity_id` FK, `role_code`, `weight`, `decision`, `created_at`
- unique (`request_id`, `identity_id`)

`execution_snapshots`

- `id`, `tenant_id` FK, `trace_id`, `parent_trace_id`, `agent_id`, `status`, `task_input`, `metrics jsonb`, `guards_evaluated jsonb`, `created_at`
- the JSON payload can hold the library snapshot. `tenant_id` stays a column, not a new required field on the Pydantic model

`fiscal_ledger_entries`

- `id`, `tenant_id` FK, `trace_id`, `amount_usd`, `model`, `tokens`, `created_at`

`telemetry_sinks`

- `id`, `tenant_id` FK, `sink_type`, `locator`, `created_at`
- `locator` is a secret reference, not an access key

`cost_centers`

- `id`, `tenant_id` FK, `code`, `gl_account`, `created_at`
- unique (`tenant_id`, `code`)
- aligns with the fields `CFOAnalyticsEngine` already reads (`cost_center`, `gl_account`)

`audit_events`

- `id`, `tenant_id` nullable, `actor_scope`, `actor_id`, `action`, `target_type`, `target_id`, `before jsonb`, `after jsonb`, `request_id`, `created_at`

`secret_refs`

- `id`, `tenant_id` nullable, `purpose`, `locator`, `created_at`

Indexes: `(tenant_id, created_at)` on snapshots, ledger entries, and audit events. Foreign keys to `tenants` are `ON DELETE RESTRICT` so a tenant with history cannot be physically removed by a status change. Suspend is a status update.

### Migration approach

- Alembic lives next to the new package, not inside `src/govagent`.
- Revision 1: extensions, roles (`govagent_owner` owns tables, `govagent_app` is the runtime role), tables, indexes, grants.
- Revision 2: `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`, policies, revoke update/delete on `audit_events` from `govagent_app`.
- Revision 3: seed the system roles, the permission rows, and one default plan. No seed tenant, so a fresh database does not invent customer data.
- Migrations are expand-only. Phase 1 creates empty tables. There is no backfill from `logs/*.jsonl` or from `policies/*.yaml` until an explicit import command exists. Those files stay the demo fixtures.
- The migrator runs as the owner. The API never uses the owner URL.
- Rollback of revision 2 drops policies before revision 1 drops tables. Production rollback of a filled database is a forward fix, not a drop.

## 11. Prioritised backlog

Size is the change surface (modules, migration risk, compatibility review). It is not a calendar estimate.

| Order | Item | Priority | Depends on | Size |
| --- | --- | --- | --- | --- |
| 0 | Owner decision on the dual registry and on whether HEAD may be published only as a new version | Blocker for any release and for wiring tools | This audit | S |
| 1 | Phase 1 control-plane foundation: package, Postgres, RLS, identity, platform vs tenant admin, audit insert | Highest product gap | Decision that Phase 1 does not modify `src/govagent` | M |
| 2 | Policy projection: map existing YAML sections onto the attributes `CircuitBreaker`, `SemanticGuard`, and `ExecutiveAgent` already read, behind tests that pin current defaults | High, because YAML ceilings and alignment are currently unbound | Owner approval; the projection changes `Policy` behaviour | M |
| 3 | Tenant-scoped tool map held on the request, built into `ToolManifest`, with Harbor called only through the existing verifier | High | Item 0, item 1 | M |
| 4 | Runtime facade: one request, rehydrate ledger, call `ExecutiveAgent` / guards, persist via a new `BaseExporter` | High | Items 1 and 2 | L |
| 5 | Durable HITL: persist `ApprovalRequest` results using `HITLManager` weights; retire the unauthenticated callback only with approval | High | Item 1 | M |
| 6 | Point `EvidencePackGenerator` and `CFOAnalyticsEngine` at stored snapshots; per-tenant sink config in front of the existing exporters | Medium | Items 1 and 4 | M |
| 7 | Use the already-declared `opentelemetry-api` for request spans tagged with `trace_id` and `tenant_id` | Medium | Item 1 | S |
| 8 | Deployment: Dockerfile, compose service for Postgres and the control plane, CI workflow. Requires replacing the empty `.github` file with a directory | Medium | Item 1 | M |
| 9 | IdP login (OIDC) and SCIM, keeping the same membership tables | Later | Item 1 | L |
| 10 | Promote `isolation_tier` to a dedicated schema or database for a contracted tenant | Later | Item 1 | L |
| 11 | Repair `docs/index.html` conflict markers and README samples that call APIs the package does not have | Small, user-visible | None, but it is a docs change outside this audit PR | S |
| 12 | Replace Harbor `PRODUCTION_BYPASS` / `mock-token` with a real Harbor API client inside `HarborVerifier` | Medium | Item 0 if the public decorator is the one that must call it | M |

Items 2 and 12 change library behaviour that callers of the published wheel can observe. They are not part of the Phase 1 file list.

## 12. Backward-compatibility risks

These are summarised here and repeated as gates in `PHASE1_PLAN.md`.

Safe without a library release:

- Adding `platform/` (or `src/govagent_platform/`) and not listing it in the `govagent` package set.
- Adding tables, RLS, and a new ASGI app.
- Adding tests under `tests/platform/`.
- Storing `tenant_id` in platform tables while leaving both `ExecutionSnapshot` models unchanged.

Needs the owner's approval before anyone implements it, because it changes the published PyPI contract or the demo gateway the current tests lock:

1. Rewiring `src/govagent/registry/__init__.py` back to `manager.py`, or deleting either registry. HEAD tests use both (`tests/test_flow.py` uses the new registry; `tests/test_harbor_registry.py` uses `manager.py`). PyPI 3.0.2 users get only the manager re-export. Either unification is a public API change.
2. Publishing the repository under version `3.0.2` again. The wheel content would not match the existing release. Ship a new version, or do not publish.
3. Making `output` required again, or adding any required field to either `ExecutionSnapshot`.
4. Changing `tool()` so that unknown keywords raise. That would be more honest and would break callers who pass `schema=` on HEAD or `oci_repository=` on PyPI, depending on which signature wins.
5. Changing `Policy.from_yaml` / `Policy.__init__` to read `fiscal_governance` and `alignment`. Correct relative to the YAML files, and a behaviour change for every embedder.
6. Changing `ExecutiveAgent.__init__` to require a tenant id, or changing `bootstrap` argument order.
7. Changing the default token, CORS, or auth on `api/server.py`. `tests/test_api_endpoints.py` sends `Bearer gov-secret-key-100x`. The UI sends the same default. `GET /api/v1/slack/callback` and `GET /api/v1/governance/state/{trace_id}` are currently unauthenticated; protecting them breaks any caller that uses them that way.
8. Importing platform models from `govagent/__init__.py` or adding the platform to the wheel. That changes what `pip install govagent` installs.
9. Registering tenant tools on `GlobalRegistry` inside a long-lived process. That is safe for a single-tenant script and unsafe for the control plane. It is also an observable behaviour change of the singleton if the control plane and the library share a process.

Phase 1, as specified in the companion plan, does none of those nine things.
