# Phase 2 plan: tenant runtime, tool map, and durable HITL

> The control plane is no longer in this public repository. `govagent-platform` is at https://github.com/thekakodkar/govagent-platform. Paths below that begin with `platform/` or `tests/platform/` describe the tree before that move.

Status: plan only. This pull request does not add runtime code.

Base: Phase 1 control plane on `cursor/phase1-platform-foundation-5c7a` ([PR #3](https://github.com/thekakodkar/govAgent/pull/3)). The Phase 0 backlog is the one written in [PR #2](https://github.com/thekakodkar/govAgent/pull/2) (`docs/audit/PHASE0_AUDIT.md` on that branch). Items 3, 4, and 5 from that backlog are this phase. Item 2 (changing `Policy` so it reads `fiscal_governance` and `alignment`) is deliberately not in the implementation set. The reasons are in the compatibility section.

## 1. Goals

A tenant member with `tenant.runtime.evaluate` can:

1. Register agent and tool **metadata** for their tenant.
2. `POST` an evaluate request for one active agent.
3. Have that request redacted by the existing `PrivacyGuard`, checked by the existing `SemanticGuard` and `CircuitBreaker`, and, when the tool is high-risk, paused for human votes.
4. Cast votes whose quorum is decided by the existing `HITLManager` weight table and tier thresholds.
5. Read back only their tenant's executions, ledger rows, and approvals, including when the SQL has no `tenant_id` predicate.

The library package stays the governance engine. Phase 2 does not publish a new `govagent` wheel and does not edit `src/govagent`, `api/server.py`, or `src/app`.

## 2. Scope

In scope:

- Tenant CRUD for agents and tool manifests, using the tables Phase 1 already created.
- A per-request tool map held on the facade. It is discarded at the end of the request.
- A runtime facade that constructs `ExecutiveAgent` (via a platform subclass), calls the guards and telemetry the agent already owns, and persists through a new `BaseExporter`.
- `POST /tenant/v1/agents/{agent_id}/evaluate`.
- Durable HITL: approval rows, one vote per identity, tally by calling `HITLManager.secure_approval`.
- One migration for HITL role assignment and one new permission.
- Tests against real Postgres, same opt-in rule as Phase 1 (`PLATFORM_TEST_DATABASE_URL` unset means the library suite still collects 22 tests).

Out of scope, and why:

| Left out | Why it waits |
| --- | --- |
| Changing `Policy`, `ExecutiveAgent`, `bootstrap`, either `ExecutionSnapshot`, or `registry/__init__.py` | Compatibility gates below. Phase 2 has an additive path around each one. |
| Demo gateway auth, CORS, or the Slack callback in `api/server.py` | Would break `tests/test_api_endpoints.py` and the Next.js app. |
| Executing arbitrary tenant-supplied Python | `tool_manifests` stores legislation (name, risk, schema, OCI coordinates), not code. The map authorizes a named action. It does not `exec`. |
| Registering tools on `govagent.registry.registry` or `registry.manager.GlobalRegistry` | Those objects are process-wide. One tenant's registration would be visible to every tenant. |
| MetaGovernor writing YAML, evidence-pack rebuild, CFO rollup from SQL, OpenTelemetry, OIDC, real Harbor HTTP, schema-per-tenant | Backlog items 6 through 10 and 12. They sit on top of a working evaluate path. |
| A second pricing engine or a second circuit breaker | The facade calls `PricingEngine` and `CircuitBreaker.check_financial_risk`. |

### Why the facade does not call `ExecutiveAgent.execute`

`ExecutiveAgent.execute` is the wrong entry point on the current tree, and fixing it inside the library is a compatibility change.

- With `router is None` it returns success immediately and skips the guards (`agent.py`, the sandbox branch).
- On a tool call it does `registry.validate_intent_schema(...).get("valid")`. The public registry method returns a `bool` (`src/govagent/registry/__init__.py`). A bool has no `.get`. The inherited loop raises `AttributeError`, which `execute` then records as status `error`.
- `perform_action` does not call a legislated function. It returns the string `Action {name} executed with params ...`.
- `ExecutiveAgent.evaluate` does not call `SemanticGuard.evaluate_alignment`. `CircuitBreaker.evaluate` only runs the fiscal check. The semantic object is built in `ExecutiveAgent.__init__` and then left unused by `evaluate`.
- `Policy` stores `alignment`, `oversight`, and `fiscal_governance` on `self.config` only. `ExecutiveAgent` reads `policy.alignment` once, at init, via `getattr`, so a normal `Policy(document)` builds an empty `SemanticGuard`.

Phase 2 still **constructs** `ExecutiveAgent` and uses the objects it already creates: `guard.privacy`, `semantic_guard`, `guard.check_financial_risk`, `telemetry`, and `HITLManager`. A platform subclass owns the short loop so it can pass the per-request tool map and avoid the public registry. That is reuse. Copying the redaction, cosine check, ceiling math, or weight table is not allowed.

## 3. How the library is reused

| Need | Call this | Do not write |
| --- | --- | --- |
| Load a policy document | `govagent.policy.Policy` | A second policy parser. Phase 1 `ensure_library_accepts` stays. |
| Bind ceilings and alignment the library already reads | Set attributes on the `Policy` **instance** before `ExecutiveAgent(...)` | A change to `Policy.__init__` |
| PII redaction | `agent.guard.privacy.redact_task` | A new recognizer |
| Intent check | `agent.semantic_guard.evaluate_alignment` | A new embedding stack |
| Spend ceiling | `agent.guard.check_financial_risk` after `reset_fiscal_ledger` / `update_shared_spend` | A new ledger |
| Price a model call | `govagent.pricing.PricingEngine.calculate_cost` | The gateway's private `MODEL_RATES` table |
| Quorum and tier | `HITLManager.secure_approval` and `HITLManager.voter_weights` | The numbers 3.0, 2.0, 1.5, 1.0, 0.5 or the 1000 / 5000 cuts |
| Financial param check | `govagent.registry.schemas.FinancialTransactionIntent` when the manifest says so | A hand-rolled amount parser |
| OCI gate | `govagent.registry.harbor_verifier.HarborVerifier.verify_tool_artifact` | A second Harbor client. The current verifier is still a mock. Call it anyway. |
| Persist the trace | A new class extending `govagent.telemetry.exporters.base.BaseExporter`, registered with `TelemetryManager.add_exporter` | A second export interface |
| LLM call | `PolicyBasedRouter` plus `OllamaClient` or a platform `BaseLLMClient` | A new router |

`ExecutiveAgent.__init__` always constructs `SemanticGuard`, which imports `sentence-transformers`, and `PrivacyGuard`, which constructs Presidio's `AnalyzerEngine` (default model `en_core_web_lg`). The platform distribution should depend on `govagent` with the `enterprise` extra. Evaluate tests need that model present, the same way the Phase 0 suite did. That is a dependency of the platform package, not a change to the library's `pyproject.toml`.

The global registry is not consulted. A regression test imports `govagent.registry.registry` and `govagent.registry.manager.GlobalRegistry` before and after evaluate and asserts both `tools` mappings are unchanged.

## 4. Runtime shape

```text
POST /tenant/v1/agents/{id}/evaluate
  session tenant GUC already set by Phase 1 auth
  load agent, active tenant policy, tool rows
  hydrate Policy instance attributes from the stored document
  reset_fiscal_ledger(); update_shared_spend(opening balance)
  TenantExecutiveAgent(persona, hydrated policy, router, telemetry, hitl)
  privacy.redact_task
  router.route_and_generate          # one library router call per step, cap 3
  tool name must be in the request map
  FinancialTransactionIntent or required-key check
  semantic_guard.evaluate_alignment  # 0.0 blocks
  check_financial_risk for all-time sum, then again for today's sum
  high risk -> insert approval_requests pending, return PENDING
  otherwise perform the authorized action record (no code exec)
  TelemetryManager.finalize -> TenantDatabaseExporter.export
```

`TenantExecutiveAgent` lives in `platform/govagent_platform/runtime/agent.py` and subclasses `ExecutiveAgent`. It overrides `execute` and `perform_action`. It calls `super().__init__` with the existing signature `(persona, policy, router, telemetry=..., hitl_manager=...)`. It does not add a `tenant_id` parameter to the library constructor. The tenant id stays in the SQLAlchemy session and in `begin_tenant`.

Step cap is 3 on the subclass, not the library's 10. Three steps is enough to prove a tool call plus a completion without a long spend loop. Raising it later is a platform constant.

### Policy hydration

`platform/govagent_platform/runtime/policy_binding.py` builds the instance the agent will read:

- `policy = Policy(document)` so the library still rejects a document it cannot construct, and so `routing_mode` / `default_provider` keep coming from `infrastructure`, which `Policy` already copies.
- Then, before `ExecutiveAgent` is constructed, set `policy.alignment` from `document["alignment"]` when that key is a dict. `ExecutiveAgent.__init__` reads it immediately.
- Set `policy.oversight` from `document["oversight"]`.
- Replace `policy.global_limits` with `daily_budget_usd` and `recursive_tco_ceiling` taken from `document["fiscal_governance"]["global_limits"]`. The YAML files call the swarm cap `recursive_tco_limit`. The breaker reads `recursive_tco_ceiling`. The binder copies `recursive_tco_limit` into `recursive_tco_ceiling` on the instance. Keys the floor does not mention stay at the library defaults already placed by `Policy`.

This does not change what `Policy(document)` does for any other caller. The floor check in `services/policy_floor.py` keeps reading `fiscal_governance` only. Hydration is a runtime view, not a second stored document.

### Fiscal rehydration

`contextvars` do not survive the next HTTP request. At the start of evaluate:

1. `reset_fiscal_ledger()`.
2. `all_time` = sum of `fiscal_ledger_entries.amount_usd` for this tenant.
3. `today` = the same sum where `created_at` is on or after today's UTC midnight.
4. Call `check_financial_risk` twice: once with the context var set to `all_time`, once with it set to `today`. The breaker adds the projected cost of this step and compares with `min(recursive_tco_ceiling, daily_budget_usd)`. Two calls with two opening balances reuse that comparison for both windows.
5. The exporter inserts **this step's** incremental cost, not the cumulative total, so the next request does not double count.

`PricingEngine.calculate_cost` supplies the incremental amount from the router's token count. `OllamaClient` does not set `estimated_cost_usd`; the facade must not read that missing key and invent a third rate table.

### Tool map

Loaded inside the request:

```text
{name: ToolManifestRow} for this tenant only
```

Rules:

- A tool call whose name is absent is `blocked` with reason `tool_not_legislated`. It is not a success string from `perform_action`.
- `requires_approval` or `risk_level == "high"` pauses for HITL.
- If `oci_repository` and `artifact_digest` are both set, call `HarborVerifier.verify_tool_artifact`. A `verified: false` result blocks. Do not pass the manifest through `GlobalRegistry.register_tool`.
- `param_schema == {"model": "FinancialTransactionIntent"}` validates `params` with that library class. Any other schema is a list of required keys under `{"required": ["..."]}`. Missing keys block. There is no new schema language.

The map is a local dict. It is not assigned to `govagent.registry.registry`.

### Durable HITL

`HITLManager.secure_approval` both chooses the tier and tallies. Those thresholds are not a public function. Phase 2 gets them by calling `secure_approval` with a platform adapter whose `notify` returns the persisted votes and nothing else. It does not open Slack and it does not return a bare bool (a bool skips the weight table).

- Evaluate, zero votes: call `secure_approval` with `notify` returning `[]`. Ignore the `False` result. Read `manager.history[-1].required_score` and `risk_tier`. Insert `approval_requests` with status `pending` and that score. Return HTTP `PENDING`. Do not treat "no votes yet" as a rejection.
- Vote: insert the caller's signature, then call `secure_approval` with `notify` returning every signature on that request as `{voter_role, decision}`. The role string is the caller's assignment, not the JSON body. `voter_weights` supplies the numeric weight written on the row. A body field named `weight` is ignored.
- `decision == "REJECTED"` from any voter is a veto, because that is what `secure_approval` does.
- `True` stores `approved` and sets `resolved_at`. `False` with only `APPROVED` votes stores `pending` until the score is met. `False` with a `REJECTED` vote stores `rejected`.

Allowed `hitl_role` values are exactly the keys of `HITLManager.voter_weights`: `C-Suite`, `Director`, `Auditor`, `Lead`, `Clerk`. Anything else is 422. An identity with no row cannot vote.

The library's `ApprovalRequest` (the Pydantic one in `hitl/manager.py`) is not the SQL row. The SQL table `approval_requests` already exists. Do not add a required field to the Pydantic model.

Slack Socket Mode stays available to library callers. Phase 2 does not make it the vote of record. A later item can notify Slack that a row is pending. That notifier must not accept a Slack `action_id` as a role.

## 5. API routes

All tenant routes use the Phase 1 session cookie. The tenant id comes from the actor, never from the body. Permissions are the Phase 1 strings plus `tenant.hitl.vote`.

| Method and path | Permission | Behavior |
| --- | --- | --- |
| `POST /tenant/v1/agents` | `tenant.agents.write` | Body: `name`, `persona`, `policy_id`. Policy must be an **active** policy of this tenant. Status `active`. |
| `GET /tenant/v1/agents` | `tenant.agents.write` | List this tenant's agents. |
| `POST /tenant/v1/tools` | `tenant.tools.write` | Body: `name`, `description`, `risk_level`, `requires_approval`, `param_schema`, `oci_repository`, `artifact_digest`. |
| `GET /tenant/v1/tools` | `tenant.tools.write` | List this tenant's manifests. |
| `POST /tenant/v1/agents/{agent_id}/evaluate` | `tenant.runtime.evaluate` | Body: `task` (string, required). Returns `trace_id`, `status` (`success`, `blocked`, `pending`, `error`), `output`, `approval_request_id`. |
| `GET /tenant/v1/approvals/{request_id}` | `tenant.runtime.evaluate` | Status, `risk_tier`, `required_score`, signatures (identity id, role, weight, decision). No task text from another tenant; RLS hides the row. |
| `POST /tenant/v1/approvals/{request_id}/votes` | `tenant.hitl.vote` | Body: `decision` = `APPROVED` or `REJECTED`. 409 if this identity already signed. |
| `PUT /tenant/v1/hitl-assignments/{identity_id}` | `tenant.hitl.configure` | Body: `hitl_role`. Identity must already have an active membership. |
| `GET /tenant/v1/executions/{trace_id}` | `tenant.audit.read` | One snapshot: status, metrics, guards. 404 when the trace is not visible. |

No new platform-admin routes. No changes to `/api/v1/governance/*`.

Evaluate is synchronous for the guard path and returns `pending` without waiting for a human. There is no long-poll on this route in Phase 2.

## 6. Data model and RLS

Phase 1 already has `agents`, `tool_manifests`, `approval_requests`, `approval_signatures`, `execution_snapshots`, and `fiscal_ledger_entries`, with forced RLS. Phase 2 fills them. It does not add columns to the published Pydantic snapshots. The exporter stores the library metrics dict inside `execution_snapshots.metrics` and the guard names inside `guards_evaluated`. `tenant_id` is the SQL column set from `current_setting('app.tenant_id')`, not a new Pydantic field.

### Migration `20261105_0004_hitl_assignments`

Revision id `20261105_0004`, `down_revision = 20261104_0003`.

Table `tenant_hitl_assignments`:

| Column | Notes |
| --- | --- |
| `tenant_id` | PK, FK `tenants`, `ON DELETE RESTRICT` |
| `identity_id` | PK, FK `identities`, `ON DELETE RESTRICT` |
| `hitl_role` | `varchar(32)`, not null. Check constraint listing the five library role names. |
| `created_at` | `timestamptz`, default `now()` |

Foreign key `(tenant_id, identity_id)` to `tenant_memberships`, same pattern as `membership_roles`.

Privileges: `GRANT SELECT, INSERT, UPDATE, DELETE` to `govagent_app`. Owner `govagent_owner`.

RLS, enabled and forced:

```sql
CREATE POLICY hitl_assignments_isolation ON tenant_hitl_assignments
FOR ALL
USING (
    current_setting('app.actor_scope', true) IN ('platform', 'authenticate')
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
)
WITH CHECK (
    current_setting('app.actor_scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
);
```

`authenticate` can read assignments during login later. Phase 2 vote handling runs as `tenant`, after `begin_tenant`. `WITH CHECK` does not let `authenticate` write.

Also insert the permission `tenant.hitl.vote` into `role_permissions` for the seeded `tenant_admin` role (`22222222-2222-4222-8222-222222222222`). Do not grant it to `tenant_auditor`. Add the constant to `TENANT_PERMISSIONS` so new process seeds and the migration stay aligned. The migration is the path that updates databases already seeded by `20261104_0003`.

No other policy changes. Existing payload policies already cover executions, tools, agents, approvals, and ledger rows.

Downgrade drops the policy, disables RLS, drops the table, and deletes that one permission row.

## 7. Files

Create:

| File | Responsibility |
| --- | --- |
| `platform/govagent_platform/runtime/__init__.py` | Empty marker. |
| `platform/govagent_platform/runtime/policy_binding.py` | `hydrate_policy(document) -> Policy`. |
| `platform/govagent_platform/runtime/tool_map.py` | Load manifests for the current tenant. `authorize(name, params)`. Calls `FinancialTransactionIntent` and `HarborVerifier`. |
| `platform/govagent_platform/runtime/ledger.py` | Opening balances and `reset_fiscal_ledger` / `update_shared_spend`. |
| `platform/govagent_platform/runtime/exporter.py` | `TenantDatabaseExporter(BaseExporter)` writing `execution_snapshots` and `fiscal_ledger_entries` on the request session. |
| `platform/govagent_platform/runtime/hitl_adapter.py` | Adapter whose `notify` returns the vote list it was given. |
| `platform/govagent_platform/runtime/agent.py` | `TenantExecutiveAgent(ExecutiveAgent)`. |
| `platform/govagent_platform/runtime/llm.py` | `ScriptedLLMClient(BaseLLMClient)` for tests and for `PLATFORM_LLM_PROVIDER=scripted`. Optional branch that builds `OllamaClient` when `PLATFORM_LLM_PROVIDER=ollama`. |
| `platform/govagent_platform/services/agents.py` | Create and list agents. Audit `agent.create`. |
| `platform/govagent_platform/services/tools.py` | Create and list manifests. Audit `tool.create`. Does not call `govagent.registry.tool`. |
| `platform/govagent_platform/services/runtime.py` | `evaluate` orchestration. |
| `platform/govagent_platform/services/approvals.py` | Assign HITL roles, record votes, call `HITLManager`. |
| `platform/govagent_platform/api/runtime.py` | The routes in section 5. |
| `platform/migrations/versions/20261105_0004_hitl_assignments.py` | Table, RLS, permission insert. |
| `tests/platform/test_tool_map.py` | Unknown tool blocked. Global registries unchanged. |
| `tests/platform/test_evaluate.py` | Scripted tool call persists a snapshot and a ledger row. Fiscal ceiling from `fiscal_governance` blocks without editing `Policy`. |
| `tests/platform/test_hitl_votes.py` | Amount 1500 requires 2.5. Director 2.0 plus Lead 1.0 approves. Clerk 0.5 stays pending. One `REJECTED` vetoes. Second vote by the same identity is 409. |
| `tests/platform/test_runtime_rls.py` | Beta's cookie does not see alpha's execution, tool, or approval. Insert with the other tenant id fails `WITH CHECK`. |

Modify:

| File | Change |
| --- | --- |
| `platform/govagent_platform/api/main.py` | `include_router` for the runtime router. |
| `platform/govagent_platform/authz/permissions.py` | `TENANT_HITL_VOTE = "tenant.hitl.vote"` on the tenant-admin tuple. |
| `platform/govagent_platform/domain/models.py` | `TenantHitlAssignment` mapped to the new table. |
| `platform/pyproject.toml` | Depend on the parent `govagent` extra `enterprise` so `SemanticGuard` can construct. Do not edit the library `pyproject.toml`. |
| `platform/README.md` | Evaluate route, `PLATFORM_LLM_PROVIDER`, and the spacy model requirement. |

Do not modify:

- `src/govagent/**`
- `api/server.py`
- `src/app/**`
- library `pyproject.toml` and `poetry.lock`
- `tests/test_*.py` and `tests/conftest.py`
- Phase 1 migrations `20261104_0001` through `0003`

## 8. Tests to keep green

Library suite, `PLATFORM_TEST_DATABASE_URL` unset:

```bash
poetry run pytest -v --tb=short --asyncio-mode=auto
```

Expected: 22 collected, 21 passed, 1 skipped (`test_slack_interaction` when Slack credentials are absent).

Platform suite, app role, not a superuser:

```bash
export PLATFORM_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:54329/govagent_platform
export PLATFORM_TEST_DATABASE_URL=postgresql+psycopg://govagent_app:govagent_app_local@127.0.0.1:54329/govagent_platform
export PLATFORM_APP_DATABASE_URL="$PLATFORM_TEST_DATABASE_URL"
export PLATFORM_SESSION_SECRET=test-session-secret
export PLATFORM_LLM_PROVIDER=scripted
poetry -C platform run pytest ../tests/platform -v --tb=short
```

Phase 1's 8 tests stay in that run. The scripted client returns a fixed tool call so evaluate tests do not need Ollama. One test constructs a real `SemanticGuard` only if the sentence-transformer model is already downloaded; if the model cannot load, that single test fails loudly rather than skipping the fiscal and HITL tests. Presidio still loads for any test that constructs `ExecutiveAgent`.

`git diff -- src/govagent api src/app pyproject.toml` must be empty at the end of Phase 2.

## 9. Sequence and size

Size is the change surface, not a calendar estimate.

| Step | Work | Size | Depends on |
| --- | --- | --- | --- |
| 1 | Migration `0004`, model, permission, HITL assignment routes | S | Phase 1 merged |
| 2 | Agent and tool CRUD, audit rows, RLS test for those tables | S | Step 1 not required |
| 3 | `hydrate_policy`, ledger rehydration, `TenantDatabaseExporter` | M | Phase 1 session |
| 4 | `TenantExecutiveAgent`, scripted LLM, `POST evaluate` | L | Steps 2 and 3 |
| 5 | Vote route via `HITLManager.secure_approval` | M | Steps 1 and 4 |
| 6 | Global-registry non-interference test and full platform suite | S | Steps 4 and 5 |

Steps 2 and 3 can be written together. Step 4 is the one that needs the spacy model and the enterprise extra.

## 10. Open questions

These do not block the additive design. Defaults are the ones the plan uses if the owner does not answer.

1. **Default HITL role for `tenant_admin`.** Default: none. An admin must `PUT` an assignment before anyone can vote. Alternative: seed assignment is out of band. Silent Director rights for every admin would make a single admin meet the 2.0 weight and almost meet tier 2 (2.5). That is a product choice, not a library choice.
2. **Scripted provider as the default.** Default: `PLATFORM_LLM_PROVIDER=scripted` so a fresh install does not call a network model. Production sets `ollama` and `OLLAMA` base URL through the existing `OllamaClient`. A cloud provider waits until there is a library client, which there is not today.
3. **Slack notify-only.** Default: no Slack call in Phase 2. The vote of record is the authenticated route.
4. **What "perform" means.** Default: the snapshot records the authorized name and params. It does not run a webhook. A webhook locator would be a secret ref and a new side effect. Leave it for the item that introduces real tool code.
5. **Multi-step budget.** Default: 3 router calls. The library loop allows 10. The subclass constant is the platform choice.

## 11. Backward-compatibility decisions

Phase 2 can be implemented and shipped **without any of these**. Each recommendation is the option that keeps `pip install govagent` behavior stable.

### D1. Registry unification

`src/govagent/registry/__init__.py` and `registry/manager.py` are two registries. The public `validate_intent_schema` returns `True`. `ExecutiveAgent.execute` expects a dict. PyPI 3.0.2 re-exports the manager registry instead.

| Option | Impact |
| --- | --- |
| Recommended: do not unify in Phase 2. The facade never calls `validate_intent_schema` or `register_tool`. | No PyPI change. Harbor tests and flow tests stay valid. Tool gating is the tenant table. |
| Unify on `manager.py` and make `validate_intent_schema` return a dict. | Restores the PyPI 3.0.2 object and makes `execute` able to run. Breaks HEAD callers of the new `tool(schema=...)` and `FinancialTransactionIntent` path that `tests/test_flow.py` uses. Needs a new library version, not a reupload of 3.0.2. |
| Unify on the HEAD registry and teach `execute` to accept a bool. | Library change. PyPI users who depend on `verify_and_resolve_tool` via `from govagent import registry` stay broken until they upgrade, and the upgrade must be explicit. |

Phase 2 proceeds additively without D1. Unification remains the right **library** fix later, as its own change with an owner-approved version bump.

### D2. `Policy` reading `fiscal_governance` and `alignment`

| Option | Impact |
| --- | --- |
| Recommended: hydrate the instance in the platform after `Policy(document)`. | Embedders who call `Policy` themselves see the same attributes they see today. The platform evaluate path enforces the YAML ceilings and the prohibited list. Two readers of one document (floor service and binder) must keep using `fiscal_governance` as the stored shape. |
| Change `Policy.__init__` to project those sections. | Correct for every embedder, and it changes the ceiling `CircuitBreaker` sees. Today a document that only sets `fiscal_governance.global_limits.daily_budget_usd` still leaves `policy.global_limits["daily_budget_usd"]` at the code default `10.0`. Existing tests pass because of that default. Shipping this is a minor-or-major library release with tests that pin both the old default and the new projection. |

Phase 2 proceeds additively without D2. The owner should still approve D2 as a later library release so the shim can be deleted. Until that release, the shim is the supported platform behavior.

### D3. `ExecutiveAgent` / `bootstrap` signature

| Option | Impact |
| --- | --- |
| Recommended: platform subclass, same `super().__init__` arguments. Tenant id stays in the database session. | No caller of `ExecutiveAgent` or `bootstrap` changes. `execute` on the base class stays as it is, including the sandbox branch. |
| Add `tenant_id` to `__init__` or `bootstrap`. | Every embedder and the README samples break. The library has no database to put that id in. |

Phase 2 proceeds additively without D3.

### D4. Demo gateway auth and CORS

| Option | Impact |
| --- | --- |
| Recommended: leave `api/server.py` alone. New routes live under `/tenant/v1`. | `tests/test_api_endpoints.py` and the UI keep sending `Bearer gov-secret-key-100x`. The unauthenticated state and Slack callback stay as they are. |
| Require a real session on the demo gateway, or remove the default token. | Breaks those tests and the dashboard. It does not make the platform multi-tenant. The demo process has one in-memory dict. |

Phase 2 proceeds additively without D4. The platform cookie is already a separate authenticator.

### D5. Versioning and republishing

| Option | Impact |
| --- | --- |
| Recommended: do not release the library as part of Phase 2. `govagent-platform` stays an unpublished in-repo distribution. | PyPI `govagent==3.0.2` stays the bytes uploaded on 2026-07-07. |
| Republish the git tree as `3.0.2`. | Replaces an existing release with different registry code and extra modules. Rejected in Phase 1 and still rejected. |
| If D1 or D2 is later approved, publish `3.1.0` (or the next minor the owner picks), not a rebuild of `3.0.2`. | Callers opt in. The platform shim can stay until it is deleted in that same release. |

Phase 2 proceeds additively without D5.

### Also refused inside Phase 2

These were gates on the Phase 1 work and they stay closed:

- A new required field on either `ExecutionSnapshot`.
- Putting platform modules on the `govagent` wheel or in `govagent/__init__.py`.
- Any call to `govagent.registry.tool` or `GlobalRegistry.register_tool` from the multi-tenant process.

## 12. Done when

Phase 2 the implementation, not this plan, is done when:

- The new platform tests pass on `govagent_app` with forced RLS.
- The library suite is still 21 passed and 1 skipped with platform collection disabled.
- `git diff` of `src/govagent`, `api/server.py`, `src/app`, and the library `pyproject.toml` is empty.
- An evaluate that names a tool outside the tenant map is `blocked`, and neither global registry grew an entry.
- A 1500 USD action stays `pending` until a Director vote and a Lead vote exist, and those weights came from `HITLManager.voter_weights`.
