# Phase 1 implementation plan

> The control plane is no longer in this public repository. `govagent-platform` is at https://github.com/thekakodkar/govagent-platform. Paths below that begin with `platform/` or `tests/platform/` describe the tree before that move.

Companion to [PHASE0_AUDIT.md](PHASE0_AUDIT.md) and [diagrams/target-architecture.md](diagrams/target-architecture.md).

Phase 1 builds the enterprise foundation beside the existing library: a database, forced tenant isolation, identity, the split between platform administration and tenant administration, and an append-only audit log. It does not reimplement guards, the fiscal ledger, HITL weight math, telemetry exporters, or the demo gateway.

No item in this plan is implemented in the Phase 0 pull request.

## Goal

A new process can:

1. Create a tenant and a plan as a platform operator.
2. Add an identity to that tenant and grant a tenant role.
3. Store a tenant policy document and refuse to activate it when it grants a higher fiscal ceiling than the active global floor.
4. Read back only that tenant's rows when the database session is tagged with that tenant, including when the query omits `WHERE tenant_id = ...`.
5. Write an `audit_events` row for each of those actions, and fail if application code tries to update or delete that row.

## Non-goals

- No edits under `src/govagent/`.
- No edits to `api/server.py`, `src/app/`, `policies/`, `examples/`, or the existing tests.
- No change to `govagent.__all__`, `tool`, `registry`, `Policy`, `ExecutiveAgent`, or either `ExecutionSnapshot`.
- No second implementation of `PrivacyGuard`, `SemanticGuard`, `CircuitBreaker`, `HITLManager`, `PricingEngine`, `MetaGovernor`, `EvidencePackGenerator`, `CFOAnalyticsEngine`, `HarborVerifier`, or the exporters.
- No runtime execution facade yet. Calling `ExecutiveAgent` per tenant is backlog item 4 in the audit, after the policy-projection decision.
- No OIDC, no Harbor client, no Dockerfile replacement, no repair of `docs/index.html`.
- No import of existing YAML or JSONL into the database.

## Compatibility rules

The new code lives in a top-level `platform/` tree and is a separate distribution. `pyproject.toml` of `govagent` does not gain a package include and does not gain a runtime dependency on SQLAlchemy, Alembic, or Postgres drivers.

`platform/pyproject.toml` depends on `govagent` as an installed library so the policy service can construct `govagent.policy.Policy` from a stored document. In Phase 1 that call is a round-trip check (the document loads, and the floor comparison uses the document JSON the control plane stores). It does not rely on `Policy` projecting `fiscal_governance` or `alignment`, because those attributes are not populated today. The floor check is explicit in the control plane:

- Read the active `global_policies.document`.
- Read the candidate `tenant_policies.document`.
- Compare the numeric ceilings and the required guard list with a small function in `platform/govagent_platform/services/policy_floor.py`.
- Also call `Policy(document)` so a document the library cannot construct is rejected.

That comparison function reads the same keys the YAML files already use (`fiscal_governance.global_limits`). It does not patch `Policy`.

The control plane must not call `govagent.registry.tool` or `GlobalRegistry.register_tool` during requests. Tool rows stay in `tool_manifests` until the registry decision in the audit is approved.

## Files to create

### Package

| File | Responsibility |
| --- | --- |
| `platform/pyproject.toml` | Distribution name `govagent-platform`. Depends on `govagent`, `fastapi`, `uvicorn`, `sqlalchemy>=2`, `alembic`, `psycopg[binary]`, `pydantic>=2`, `pwdlib` or `bcrypt` for password hashes. Dev group: `pytest`, `pytest-asyncio`, `httpx`. |
| `platform/govagent_platform/__init__.py` | Version string only. Does not import `govagent` at import time, so a missing optional extra cannot break process start. |
| `platform/govagent_platform/config.py` | Settings from the environment: `PLATFORM_DATABASE_URL`, `PLATFORM_APP_DATABASE_URL` (the `govagent_app` role), `PLATFORM_SESSION_SECRET`, `PLATFORM_ENVIRONMENT`. No default token. Missing URL or secret raises at startup. |
| `platform/govagent_platform/db.py` | Engine, session factory, `begin_tenant(session, tenant_id)` and `begin_platform(session)` which `SET LOCAL` the GUCs from the audit. |
| `platform/govagent_platform/security/passwords.py` | Hash and verify. |
| `platform/govagent_platform/security/context.py` | `Actor` dataclass: `identity_id`, `scope` (`platform` or `tenant`), `tenant_id`, `permissions`. |
| `platform/govagent_platform/security/sessions.py` | Sign a session cookie. Phase 1 login is email plus password for seeded identities. |
| `platform/govagent_platform/security/dependencies.py` | FastAPI dependencies: load the session, require a permission, open the DB transaction with the matching GUC. |
| `platform/govagent_platform/authz/permissions.py` | The permission string constants from the audit. |
| `platform/govagent_platform/domain/models.py` | SQLAlchemy 2 models for the tables in the audit. Table and column names match that list. |
| `platform/govagent_platform/services/tenants.py` | Create and suspend tenants. Insert `audit_events`. |
| `platform/govagent_platform/services/memberships.py` | Create identity, membership, role grant. Insert `audit_events`. |
| `platform/govagent_platform/services/policy_floor.py` | Compare tenant document to global floor. Construct `govagent.policy.Policy` as a load check. |
| `platform/govagent_platform/services/policies.py` | Draft and activate global and tenant policies. One active tenant policy. Insert `audit_events`. |
| `platform/govagent_platform/api/main.py` | FastAPI app factory. Routers only. No CORS wildcard. |
| `platform/govagent_platform/api/platform_admin.py` | `/platform/v1/...` routes below. |
| `platform/govagent_platform/api/tenant_admin.py` | `/tenant/v1/...` routes below. |
| `platform/alembic.ini` | Script location `platform/migrations`. |
| `platform/migrations/env.py` | Uses `PLATFORM_DATABASE_URL` (owner) and `target_metadata` from the models. |
| `platform/migrations/versions/20261104_0001_catalog.py` | Roles, tables, indexes, grants. |
| `platform/migrations/versions/20261104_0002_rls.py` | Enable and force RLS, create policies, revoke `UPDATE`/`DELETE` on `audit_events`. |
| `platform/migrations/versions/20261104_0003_seed_roles.py` | System roles, permission rows, default plan `community`. No tenant. |
| `platform/README.md` | How to boot Postgres, migrate, and run the app. States that this package is not `govagent` on PyPI. |

### Tests

| File | What it proves |
| --- | --- |
| `tests/platform/conftest.py` | Starts from `PLATFORM_TEST_DATABASE_URL`, runs Alembic upgrade head, wraps each test in a transaction that rolls back. Creates a platform actor and two tenants (`alpha`, `beta`). |
| `tests/platform/test_rls_isolation.py` | As tenant alpha, `SELECT` from `tenant_policies`, `agents`, `audit_events`, and `execution_snapshots` returns only alpha rows even when the SQL has no tenant predicate. Beta rows inserted in the same test are invisible. Insert with a mismatched `tenant_id` fails the `WITH CHECK`. |
| `tests/platform/test_platform_admin_api.py` | Platform actor creates a tenant and a plan assignment. Tenant actor receives 403 on `POST /platform/v1/tenants`. |
| `tests/platform/test_tenant_admin_api.py` | Tenant admin of alpha invites a user and assigns `tenant.policies.write`. The same call with beta's session cookie receives 404 or an empty list for alpha's policy, never the document. |
| `tests/platform/test_policy_floor.py` | A tenant document whose `fiscal_governance.global_limits.daily_budget_usd` is above the active floor is rejected. A stricter ceiling activates. `Policy(...)` is called and must not raise on the stored document shape. |
| `tests/platform/test_audit_append_only.py` | After a tenant create, one `audit_events` row exists. `UPDATE` and `DELETE` as `govagent_app` raise. |

Existing `tests/test_*.py` stay untouched and must still pass with the same command as the audit:

```bash
poetry run pytest -v --tb=short --asyncio-mode=auto
```

Platform tests are opt-in on a database URL so the library suite does not require Postgres:

```bash
PLATFORM_TEST_DATABASE_URL=postgresql+psycopg://govagent_owner@localhost:54329/govagent_platform \
  poetry -C platform run pytest ../tests/platform -v --tb=short
```

### Local database file, additive

| File | Responsibility |
| --- | --- |
| `platform/docker-compose.yml` | Postgres 16 only, port `54329`, database `govagent_platform`, owner role and `govagent_app` role created by the migration rather than by inventing application behaviour in SQL init that drifts from Alembic. A root password is confined to this compose file's local development defaults and documented as local-only. |

This compose file does not replace the repository root `docker-compose.yml`, which remains the broken demo stack until a later deployment item.

## Files that must not be modified

- `src/govagent/**`
- `api/server.py`
- `src/app/**`
- `policies/**`
- `examples/**`
- `tests/conftest.py` and every existing `tests/test_*.py`
- `pyproject.toml` and `poetry.lock` of the library
- `README.md`, `changelog.md`, `docs/index.html`

A change to any of those is a different pull request and hits the approval gates below.

## API surface to add

Session:

- `POST /platform/v1/session` with email and password. Sets an HTTP-only cookie. No token in a query string.
- `DELETE /platform/v1/session`.

Platform, permission on the left:

- `platform.tenants.write` — `POST /platform/v1/tenants`, `POST /platform/v1/tenants/{id}/suspend`
- `platform.tenants.read` — `GET /platform/v1/tenants`, `GET /platform/v1/tenants/{id}` (metadata only: slug, status, plan, region, isolation tier)
- `platform.plans.write` — `POST /platform/v1/plans`, `PUT /platform/v1/tenants/{id}/plan`
- `platform.policies.write` — `POST /platform/v1/global-policies`, `POST /platform/v1/global-policies/{id}/activate`

Tenant, tenant taken from the session, never from an unverified body field:

- `tenant.users.write` — `POST /tenant/v1/identities`, `POST /tenant/v1/memberships`
- `tenant.roles.write` — `POST /tenant/v1/memberships/{identity_id}/roles`
- `tenant.policies.write` — `POST /tenant/v1/policies`, `POST /tenant/v1/policies/{id}/activate`
- `tenant.policies.write` — `GET /tenant/v1/policies`
- `tenant.audit.read` — `GET /tenant/v1/audit-events`

Phase 1 does not add agent, tool, HITL, or evaluate routes. Those tables exist so Phase 2 does not revise the first migration, and RLS tests already cover `agents` and `execution_snapshots`.

## Migration details

Revision `20261104_0001_catalog`:

1. `CREATE ROLE govagent_owner` and `CREATE ROLE govagent_app NOINHERIT`.
2. Create every table and index in audit section 10.
3. `ALTER TABLE ... OWNER TO govagent_owner`.
4. `GRANT SELECT, INSERT, UPDATE, DELETE` on tenant-owned tables to `govagent_app`, except `audit_events`, which receives `SELECT, INSERT` only.
5. Catalog tables `plans` and `global_policies` are readable by `govagent_app`. Inserts to them are granted, and the API still checks `platform.plans.write` / `platform.policies.write`. Updates to an **active** global policy are not issued by the service; activation inserts a new version and marks the previous `retired` so the floor history stays intact.

Revision `20261104_0002_rls`:

1. `ENABLE` and `FORCE` RLS on every table that has `tenant_id`, plus `audit_events`.
2. Create the tenant isolation policy quoted in the audit.
3. Create a platform catalog policy on `tenants` and `plans`: `current_setting('app.actor_scope', true) = 'platform'` for operator list and write.
4. `global_policies` is readable by any authenticated scope (tenants must see the floor to tighten it) and writable only when `app.actor_scope = platform`.

Revision `20261104_0003_seed_roles`:

- Platform role `operator` with the platform permissions listed in the audit.
- Tenant system roles `tenant_admin` and `tenant_auditor` (`tenant.audit.read` only).
- Plan `community` with a finite `max_agents` and `retention_days`.

Seed does not insert an identity. The first operator is created by a one-shot CLI in `platform/govagent_platform/cli.py`:

- `python -m govagent_platform.cli bootstrap-operator --email ...`
- Reads the password from the terminal, not from argv.
- Refuses to run when an operator binding already exists.

That CLI file is part of Phase 1.

## Order of work

1. Add `platform/pyproject.toml`, config, and SQLAlchemy models. No API yet.
2. Add Alembic revisions 1–3. Apply them to a local Postgres. Confirm `\dp` shows `govagent_app` without ownership.
3. Add `begin_tenant` / `begin_platform` and `tests/platform/test_rls_isolation.py`. This is the gate for every later route.
4. Add services (tenants, memberships, policy floor, audit insert).
5. Add the session cookie and the routes.
6. Add the API tests and the append-only test.
7. Run the platform suite and the original `poetry run pytest` suite. The original suite must stay at 21 passed, 1 skipped, for the same skip reason (missing Slack credentials), unless the environment has gained a `.env`.

## Owner approval gates

Do not start the following inside Phase 1. Each one changes a contract this audit measured.

| Gate | What would change | Who is affected |
| --- | --- | --- |
| G1 | Editing `src/govagent/registry/__init__.py` or `registry/manager.py` so there is only one `GlobalRegistry` and one `tool` | PyPI 3.0.2 importers of `govagent.tool` / `govagent.registry`, and HEAD tests that depend on the split (`tests/test_flow.py`, `tests/test_harbor_registry.py`) |
| G2 | Publishing the git tree as `govagent==3.0.2` | Anyone who already installed 3.0.2 on 2026-07-07. The registry module and `ExecutionSnapshot` fields differ, and `cfo_analytics.py` / `evidence.py` are absent from that wheel. Publish a new version or do not publish. |
| G3 | Adding a required field, or changing a default, on `govagent.registry.schemas.ExecutionSnapshot` or `govagent.telemetry.manager.ExecutionSnapshot` | `ExecutiveAgent._finalize`, `api/server.py`, and any external constructor |
| G4 | Changing `Policy.__init__` or `from_yaml` to interpret `fiscal_governance`, `alignment`, `oversight`, or `financial_accounting` | Every embedded caller, and the meaning of the existing pytest fiscal ceiling (today the breaker sees the code default `daily_budget_usd` of `10.0`) |
| G5 | Changing `ExecutiveAgent` constructor or `bootstrap` signature, including a tenant argument | README samples and all callers |
| G6 | Changing auth, the default bearer, CORS, or the unauthenticated state and Slack routes in `api/server.py` | `tests/test_api_endpoints.py` and the Next.js app, which send `Bearer gov-secret-key-100x` |
| G7 | Adding platform modules to the `govagent` wheel or to `govagent/__init__.py` | `pip install govagent` users |
| G8 | Calling the process-global registry from the multi-tenant process | Every tenant sharing that process |

Phase 1 is complete when the new tests pass, the original suite still matches the audit counts, and `git diff -- src/govagent api src/app pyproject.toml` is empty.
