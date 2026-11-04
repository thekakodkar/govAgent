# Phase 3 plan: private platform distribution, quotas, and tenant evidence

Status: plan only. This commit does not add runtime code, a CI change, or a package publish.

`govagent-platform` will **not** be published to PyPI. Customers receive it as a container image and, if they want a Python install, from a **private package index**. The open-source library stays on PyPI as `govagent`.

## Prerequisite that is not on main

As of `105a21c` (`origin/main`, tag `v3.0.3`), GitHub `main` has Phase 1 and the 3.0.3 library fix. It does **not** have Phase 2.

Missing from `main`, present on `cursor/phase1-platform-foundation-5c7a` (PRs #4 and #5 merged into that branch only):

- `docs/audit/PHASE2_PLAN.md`
- `platform/govagent_platform/runtime/`
- `platform/govagent_platform/api/runtime.py`
- `platform/migrations/versions/20261105_0004_hitl_assignments.py`
- `tests/platform/test_evaluate.py`, `test_hitl_votes.py`, `test_runtime_rls.py`, `test_tool_map.py`, `runtime_support.py`

Phase 3 implementation starts only after that set is on `main`. The sections below assume it is the baseline: tenant evaluate, the per-request tool map, durable HITL, and migration `0004`. This document does not merge that branch.

## What Phase 3 is for

Phase 1 on `main` stores tenants, plans, policies, and audit rows. Phase 2 (side branch) evaluates a task and stores snapshots, ledger rows, and votes. Phase 3 makes that control plane something a customer can run without putting it on PyPI, and fills the gaps still open in `docs/audit/PHASE0_AUDIT.md`:

- enforce the plan quotas that are already columns
- build per-tenant evidence and CFO views from stored rows
- a policy console for the APIs that already exist
- request traces tagged with `tenant_id`
- OIDC beside the password session
- a written promotion path for `isolation_tier`, not a second database yet

Library work that changes published behavior stays behind an approval gate. It is listed at the end and is not part of the default Phase 3 file set.

## Distribution

### Library build already excludes `platform/`

`pyproject.toml` packages only the library:

```toml
packages = [
    { include = "govagent", from = "src" }
]
```

A local build of the tree at `105a21c` (`poetry build -o /tmp/govagent-dist`) produced:

| Artifact | Entries | Paths containing `platform/` or `govagent_platform` |
| --- | --- | --- |
| `govagent-3.0.3-py3-none-any.whl` (54399 bytes) | 43 | 0 |
| `govagent-3.0.3.tar.gz` (48734 bytes) | 43 | 0 |

Wheel top-level members are `govagent/` and `govagent-3.0.3.dist-info/`. The sdist top-level member is `govagent-3.0.3/`. `api/`, `src/app/`, and `platform/` are not in either archive. `cfo_analytics.py` and `evidence.py` are inside `govagent/governance/` because they live under `src/`. `governance/__init__.py` still exports only `MetaGovernor`. That matches the 3.0.3 plan: the files can sit in the wheel; they are not advertised API.

### CI guard to add

This commit does not add the guard. Phase 3 adds one step to `.github/workflows/ci.yml` after the library tests, and a matching test so a local `pytest` fails the same way:

- File: `tests/test_wheel_layout.py`
- Build with `poetry build -o` a temp directory (or inspect an already built `dist/` if present).
- Fail if any archive member contains `platform/`, `govagent_platform`, `src/app/`, or `api/server.py`.
- Fail if `govagent/governance/__init__.py` inside the wheel imports `CFOAnalyticsEngine` or `EvidencePackGenerator`.

The workflow step runs `poetry build` and `pytest tests/test_wheel_layout.py`. It does not publish.

### Stay in this repo, or move the platform

The GitHub repository is public. Keeping `platform/` here means the control-plane source is public even though it is not on PyPI. That is the situation today.

| Choice | What you gain | What you give up |
| --- | --- | --- |
| Recommended for now: keep `platform/` in this repo, never publish that package to PyPI | One history. Platform tests import the library from `../src`. A library fix and a platform fix can land together. The wheel guard above is sufficient to keep PyPI clean. | Anyone who can read the GitHub repo can read the control plane. |
| Move `platform/` and `tests/platform/` to a private repository | Customer source is not on the public repo. The public repo is only the library, docs for the library, and the wheel guard. | The private repo pins a released `govagent` version instead of a path dependency. Library fixes are not visible to the platform until they are tagged. Two CI systems. Phase plans split across repos. Cross-repo reviews when a guard return shape changes. |

Do not keep a public copy and a private copy of the same tree. If a customer contract requires private source, delete `platform/` from the public repo in the same change that creates the private repo, and leave a one-line pointer in `platform/README.md`'s replacement: the control plane is distributed as an image, not as a public package.

Phase 3 does not do that split unless the owner asks. The packaging below works in either layout.

### How a customer gets the platform

Package name: `govagent-platform`. Its version is **not** the library version. Phase 3 images use `0.3.0` (platform generation 3), while the library stays `3.0.3` until a later library release.

Dependency pin in `platform/pyproject.toml` for **release** builds:

```toml
govagent = ">=3.0.3,<3.1.0"
```

The upper bound stays until `3.1.0` exists and the platform suite has been run against it. Developer checkouts may keep `{ path = "..", extras = ["enterprise"], develop = true }`. The release Dockerfile must not use the path dependency. It installs `govagent` from PyPI at the pin above, then installs `govagent-platform` from the private index or from the image build context.

Release steps, none of which run in this commit:

1. Land Phase 2 on `main`.
2. Bump only `platform/pyproject.toml` to `0.3.0`. Add `platform/CHANGELOG.md`. Do not bump the library.
3. Build the library wheel guard (section above) so the public artifact still has no `platform/`.
4. Build `govagent-platform:0.3.0` from `platform/Dockerfile` (new). Tag also `govagent-platform:0.3`.
5. Push the image to the customer's registry. Do not `docker push` to a public Docker Hub repo unless the owner explicitly wants a public image.
6. Optional: `poetry publish -r customer` where `customer` is a private index configured outside the repo (`poetry config repositories.customer <url>`). Do not add `https://upload.pypi.org/legacy/` for this package. Put `package-mode` private by omitting any PyPI publish job. A CI job that fails if the publish URL host is `pypi.org` is part of this step.
7. Do not tag the library repo for a platform release. Platform image tags are the platform version.

### Image contents

New file `platform/Dockerfile`, separate from the repo-root `Dockerfile` (that file is the library dev image and stays that way):

- `python:3.12-slim`
- `pip install govagent[enterprise]==3.0.3` (or the pin range resolved by Poetry)
- `python -m spacy download en_core_web_lg` documented as a build step, because `PrivacyGuard` needs it
- copy `platform/` only
- `poetry install` of `govagent-platform` without a path dependency
- command: `uvicorn govagent_platform.api.main:create_app --factory --host 0.0.0.0 --port 8070`
- no `src/govagent` copy, so the image cannot drift from the PyPI pin

`platform/docker-compose.yml` gains an `platform-api` service that builds that Dockerfile and still depends on the existing Postgres 16 service. Local compose may keep the path install via a compose override; the published image must not.

## Functional work

### Quotas the plan table already describes

`plans.max_agents`, `plans.monthly_tco_ceiling_usd`, and `plans.retention_days` are unused. Phase 3 enforces the first two.

- `platform/govagent_platform/services/quotas.py`
- `create_agent` returns 409 when the tenant already has `max_agents` active agents
- `evaluate_agent` returns `blocked` when the calendar-month sum of `fiscal_ledger_entries.amount_usd` plus the projected step would pass `monthly_tco_ceiling_usd`
- No new table. The ledger is the usage record.
- Tests: `tests/platform/test_quotas.py`

`retention_days` is documented as a later purge job. Phase 3 does not delete ledger rows.

### Per-tenant evidence and CFO

Phase 2 stores `execution_snapshots`. The library builders `EvidencePackGenerator` and `CFOAnalyticsEngine` read a JSONL file and an in-memory list. Phase 3 does not change those classes.

- `platform/govagent_platform/services/evidence_export.py` loads this tenant's snapshot rows and feeds attribute-compatible objects to `CFOAnalyticsEngine.record_execution` / `analyze`.
- The evidence dossier is built by importing `govagent.governance.evidence` and filling `ComplianceDossier` from those rows. That module is importable and not in `__all__`. Phase 3 may call it. Promoting it to `__all__` is a 3.1.0 library change and needs a separate approval. Until then the platform treats the import as private and pins `<3.1.0`.
- Routes on the existing tenant router: `GET /tenant/v1/compliance/export` (`tenant.audit.read`), `GET /tenant/v1/financials/risk-overview` (`tenant.audit.read`).
- Tests: `tests/platform/test_tenant_exports.py`. Beta's session must not see alpha's dossier. That is the same RLS already on `execution_snapshots`.

Sinks: `POST /tenant/v1/sinks` and `GET /tenant/v1/sinks` write `telemetry_sinks` (table exists). `locator` remains a reference, not a secret value. The evaluate exporter, after writing the SQL row, constructs the existing `CloudWatchExporter` or `AzureMonitorExporter` only when the locator resolves and credentials exist. It does not reimplement `BaseExporter`. Tests use `MockSOCExporter` or a fake that records `export()` calls. No cloud credentials in CI.

### Policy console

Phase 1 already has draft and activate routes. Phase 3 adds a UI that is not `src/app` (that app is the demo gateway and stays on the old token).

- New tree: `platform/ui/` (Next.js). It is outside `src/`, so the library wheel guard ignores it.
- Screens: platform operator tenant list; tenant policy list; draft editor; activate button that shows the floor 409 reasons; agent and tool lists; evaluate form; approval vote buttons.
- It calls `/platform/v1` and `/tenant/v1` with the existing session cookie. No new auth scheme.
- Tests: a small Playwright or HTTP contract is optional. Required test is still the API suite. Add `platform/ui` build (`npm run build`) to the platform image CI, not to the library wheel CI.

### Observability

`opentelemetry-api` is already a library dependency and is unused in `src/govagent`. Phase 3 does not instrument the library.

- `platform/govagent_platform/telemetry.py` starts a tracer from `opentelemetry-api` and wraps evaluate and vote routes.
- Span attributes: `tenant_id`, `trace_id`, `govagent.status`. No task text on the span.
- Dependency added only in `platform/pyproject.toml`: `opentelemetry-sdk` for the image. The library `pyproject.toml` is unchanged.
- Test: `tests/platform/test_spans.py` uses an in-memory exporter and asserts a span exists for evaluate without asserting a cloud collector.

### OIDC

Password login stays. `identities.external_subject` already exists.

- Table `oidc_providers` in migration `20261106_0005_oidc_providers`: `id`, `tenant_id` nullable, `issuer`, `client_id`, `client_secret_locator` (a secret ref, not the secret), `created_at`.
- RLS: platform scope reads all rows; a tenant session reads rows with its `tenant_id` or `tenant_id IS NULL` (a platform-wide IdP). Writes require `platform` scope or the matching tenant with `tenant.users.write`.
- Route: `GET /platform/v1/session/oidc/start` and `POST /platform/v1/session/oidc/callback`. The callback sets the same HTTP-only cookie as password login.
- Test: `tests/platform/test_oidc.py` with a stub token that maps `external_subject` to an existing identity. No live IdP.

### Isolation tier

`tenants.isolation_tier` exists. Every create path writes `shared`. Phase 3 does not add a database per tenant.

- API rejects `dedicated_schema` and `dedicated_db` on create with 422 and a stable error code `isolation_tier_not_available`.
- Test: `tests/platform/test_isolation_tier.py`.
- A later phase may promote a tenant. That needs owner approval because it changes connection routing and backup scope. It does not change the PyPI library. It is not in the Phase 3 file list beyond the rejection.

## Files Phase 3 would add or edit

Create:

| Path | Role |
| --- | --- |
| `tests/test_wheel_layout.py` | Library CI guard described above |
| `platform/Dockerfile` | Release image, PyPI-pinned `govagent` |
| `platform/CHANGELOG.md` | Platform versions only |
| `platform/govagent_platform/services/quotas.py` | Plan limits |
| `platform/govagent_platform/services/evidence_export.py` | Dossier and CFO from SQL rows |
| `platform/govagent_platform/telemetry.py` | Spans |
| `platform/ui/` | Policy and evaluate console |
| `platform/migrations/versions/20261106_0005_oidc_providers.py` | IdP table and RLS |
| `tests/platform/test_quotas.py` | Agent cap and monthly ceiling |
| `tests/platform/test_tenant_exports.py` | Dossier isolation |
| `tests/platform/test_spans.py` | In-memory spans |
| `tests/platform/test_oidc.py` | Stub OIDC |
| `tests/platform/test_isolation_tier.py` | Non-shared tiers rejected |

Edit:

| Path | Change |
| --- | --- |
| `.github/workflows/ci.yml` | Run the wheel-layout test. Do not publish. |
| `platform/pyproject.toml` | Version `0.3.0`. Release dependency `govagent>=3.0.3,<3.1.0`. Dev path dependency may remain for local tests. |
| `platform/docker-compose.yml` | Add the API service. Postgres service stays. |
| `platform/govagent_platform/services/agents.py` | Call the quota check. |
| `platform/govagent_platform/services/runtime.py` | Call the monthly ceiling check before the agent runs. |
| `platform/govagent_platform/api/runtime.py` | Export, financials, and sink routes. |
| `platform/govagent_platform/api/platform_admin.py` | OIDC start and callback. |
| `platform/README.md` | State that this package is not on PyPI. Image tag and private index only. |

Do not edit in the default Phase 3 set:

- `src/govagent/**`
- library `pyproject.toml` version (stays 3.0.3 until a real library release)
- `api/server.py` and `src/app/**`
- `governance/__init__.py` (`__all__` stays `MetaGovernor`)

## Approval gates

These are not approved by this plan. Phase 3 can ship without them.

| Change | Why it needs a yes | If deferred |
| --- | --- | --- |
| `Policy.__init__` reads `fiscal_governance` and `alignment` | 3.0.3 callers still see the code default daily budget of `10.0` when those keys are only nested. Changing that is a library behavior change. The 3.0.3 plan held it for 3.1.0. | Keep `hydrate_policy` in the platform. |
| Export `CFOAnalyticsEngine` and `EvidencePackGenerator` from `govagent.governance` | Additive, but it freezes a public API. Held for 3.1.0. | Platform imports the modules as private. Pin `<3.1.0`. |
| Real Harbor HTTP client instead of `mock-token` / `PRODUCTION_BYPASS` | Changes when a tool with OCI coordinates is allowed. | Keep calling `HarborVerifier` as it shipped in 3.0.3. |
| Delete or lock down `api/server.py` bearer default, CORS, or the open Slack callback | Breaks `tests/test_api_endpoints.py` and `src/app`. | Leave the demo gateway. The customer path is `/platform/v1` and `/tenant/v1`. |
| Implement `dedicated_schema` or `dedicated_db` | New operational contract, not a PyPI change. | Reject those values with 422. |
| Move `platform/` to a private repo | Removes public source. Breaks path dependency and single-repo CI. | Stay in this repo. Wheel guard keeps PyPI clean. |
| Register tenant tools on the process-global registry | Cross-tenant leakage. Forbidden since Phase 1. | Keep the per-request map. |

No Phase 3 item adds a required field to either `ExecutionSnapshot`, changes `ExecutiveAgent` or `bootstrap` signatures, or republishes `3.0.3`.

## Order

1. Land the Phase 2 files on `main` (not done in this commit).
2. Wheel-layout test and CI step.
3. Platform version `0.3.0`, pin, Dockerfile, changelog. No PyPI publish job.
4. Quotas, then evidence and CFO routes, then spans.
5. Policy console under `platform/ui/`.
6. OIDC.
7. Isolation-tier rejection only.

Library suite on `main` must stay at the 3.0.3 result: 34 collected, 33 passed, 1 skipped (`test_slack_interaction` without Slack credentials). Platform suite grows with the new tests and still skips collection when `PLATFORM_TEST_DATABASE_URL` is unset.
