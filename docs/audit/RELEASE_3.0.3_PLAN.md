# govagent 3.0.3 library fix plan

Status: plan only. Do not bump `pyproject.toml`, do not build a wheel, and do not publish to PyPI or TestPyPI as part of this document.

This release is the first publish after PyPI `govagent==3.0.2` (2026-07-07). The git tree at `main` is still version `3.0.2` and is not the same code as that wheel. `3.0.3` should be a **compatible fix release**. New product modules that are not required to fix a regression wait for `3.1.0`.

The platform control plane (`platform/`, Phase 1 and Phase 2) is not part of the `govagent` wheel and is not part of this release.

## Recommendation at a glance

| Item | Release | Backward compatible? |
| --- | --- | --- |
| `execute()` calling `.get("valid")` on a bool | **3.0.3** | Yes, if success still returns a dict and bad amounts still raise |
| Two-registry drift vs published 3.0.2 | **3.0.3** shim, delete nothing | Yes for 3.0.2 callers; see the shim below |
| `FinancialTransactionIntent` | **3.0.3** (the registry fix needs it; it is additive) | Yes. New symbol |
| Optional `ExecutionSnapshot` fields already on `main` | **3.0.3** | Yes. New fields have defaults; `output` is already optional on `main` and was required in 3.0.2. Making it optional does not break callers who pass it |
| `cfo_analytics` and `evidence` | **3.1.0** | Adding the modules is compatible, but they are features, not a regression fix. Leave them out of the 3.0.3 wheel or ship the files without exporting them. Recommended: hold the public export for 3.1.0 |
| `datetime.utcnow()` warnings | **3.0.3** | Yes, if the wire string still ends in `Z` |
| README samples (`en_core_web_lg`, `RoutingMode`, `bootstrap`, `execute`) | **3.0.3** | Yes. Documentation |
| `docs/index.html` conflict markers | **3.0.3** | Yes. Documentation |
| Dockerfile and compose paths | **3.0.3** | Yes. The current compose file does not start |
| Replace the empty `.github` file with Actions | **3.0.3** | Yes for the package API. Git history must delete the file and add a directory |

## 1. `execute()` and `validate_intent_schema`

### What is wrong

`src/govagent/agent.py` (`execute`, the schema-validation block) does:

```python
validation = registry.validate_intent_schema(...)
if not validation.get("valid"):
```

On published 3.0.2, `from govagent import registry` is `registry.manager.GlobalRegistry`, and `validate_intent_schema` returns a dict (`{"valid": True/False, ...}`). That `.get` works.

On current `main`, `src/govagent/registry/__init__.py` defines a different `GlobalRegistry`. Its `validate_intent_schema` returns `True` or raises. `True.get` raises `AttributeError`. `execute` catches that and records status `error`. A governed tool call never reaches the fiscal or judiciary checks.

`tests/test_flow.py::test_pydantic_schema_enforcement` calls the public registry directly and expects `ValidationError` or `ValueError` for `execute_financial_transaction` with `amount="invalid_amt"`. It does not call `execute()`. So the suite is green while `execute()` is broken. 3.0.3 needs a test that drives `execute()` with a tool call.

### Change

Files:

- `src/govagent/agent.py`
- `src/govagent/registry/__init__.py` (only as part of the shim in section 2)
- `tests/test_execute_validation.py` (new)

In `execute()`, accept both shapes and do not turn a schema failure into a generic `error`:

```python
validation = registry.validate_intent_schema(action, params)
if isinstance(validation, dict):
    if not validation.get("valid", False):
        return await self._finalize("blocked", f"Schema Violation: {validation.get('error')}", ...)
elif validation is not True:
    return await self._finalize("blocked", "Schema Violation", ...)
```

Keep the `except GovernanceViolation` path. Do not swallow `AttributeError` from a bool into status `error` once this guard exists.

The registry method itself, after the shim, should **return a dict on success and on "tool not legislated"**, and **raise `ValidationError` or `ValueError` for a bad amount**. That matches 3.0.2 callers that use `.get("valid")` and matches `test_pydantic_schema_enforcement`.

### Tests

`tests/test_execute_validation.py`:

- Build `ExecutiveAgent` with a router whose `route_and_generate` returns one tool call `execute_financial_transaction` / `{amount: "invalid_amt"}`. Assert the snapshot status is `blocked`, not `error`, and the output mentions the schema failure.
- Same agent, `{amount: 10}` and a legislated tool, asserts the call does not raise `AttributeError` and status is not `error` solely because validation returned a bool.
- Call `validate_intent_schema` for an unknown tool and assert the result is a dict with `valid` false (3.0.2 contract).
- Call it for `execute_financial_transaction` and `"invalid_amt"` and assert `ValidationError` or `ValueError` (current `main` contract).

### Compatibility

Compatible for 3.0.2 users: they already receive a dict. Compatible for current `main` tests: invalid amounts still raise. Not compatible with a caller that required the return value to be the bool `True`. That caller exists only on unpublished `main`, and `test_flow.py` does not assert the return type. No signature change to `execute` or `bootstrap`.

## 2. Two registries

### What is on each side

Published 3.0.2 `govagent/registry/__init__.py` does `from .manager import GlobalRegistry, tool` and `registry = GlobalRegistry()`. `tool(name, description=None, risk_level="low", oci_repository=None, artifact_digest=None)` registers a `ToolManifest` and `verify_and_resolve_tool` runs `HarborVerifier`.

Current `main` `src/govagent/registry/__init__.py` defines a second class. `from govagent import tool, registry` does **not** see Harbor. `tool(name=None, schema=None, **kwargs)` stores `schema` and `risk_level`. `oci_repository` is accepted by `**kwargs` and then dropped. `src/govagent/registry/manager.py` still has the 3.0.2 class. `tests/test_harbor_registry.py` imports it from `govagent.registry.manager` on purpose. `tests/test_flow.py` uses the public registry.

### Resolution without breaking 3.0.2

`from govagent import tool, registry` in 3.0.3 resolves to **one facade object** that is what 3.0.2 already exposed, extended so the `main` tests keep passing:

| Caller | 3.0.3 behavior |
| --- | --- |
| `tool(name=..., risk_level=..., oci_repository=..., artifact_digest=...)` | Registers on the facade. `verify_and_resolve_tool` still calls `HarborVerifier` in `manager.py`. This is the 3.0.2 path. |
| `tool(name=..., schema=FinancialTransactionIntent)` | Same registry. `schema` is stored and used by `validate_intent_schema`. This is the `main` path. |
| `registry.validate_intent_schema` | Returns `{"valid": True, "status": "AUTHORIZED"}` or `{"valid": False, "error": "..."}`. Raises `ValidationError` / `ValueError` for a non-numeric amount on `execute_financial_transaction` or when `schema` is set. |
| `registry.verify_and_resolve_tool` | Present, delegated to the current `manager.GlobalRegistry` logic. Do not copy Harbor. |
| `registry.tools` | Dict whose values expose `risk_level` (what `Policy.validate_registry` reads on `main`) and the manifest (what 3.0.2 stored). A small wrapper dict is enough. Do not return a bare manifest that makes `.get("risk_level")` fail, and do not drop the manifest. |
| `from govagent.registry.manager import GlobalRegistry, tool` | Stays importable. Docstring notes it is the Harbor implementation used by the facade. No runtime warning in 3.0.3 if tests import it; a one-line comment is enough. A `DeprecationWarning` on **constructing** a second empty `GlobalRegistry()` from `manager` while also using the facade is optional and noisy. Skip the warning in 3.0.3. |
| The class currently written inline in `registry/__init__.py` | Remove it from the public module so there are not two singletons. Move any behavior it has that the facade must keep (schema validation, `PermissionError` from `validate_against_policy` if a test depends on it) into the facade. |

`Policy.validate_against_policy` on `main` raises `PermissionError` for a tool that is not in the policy. The 3.0.2 manager method only prints. The facade should **keep the raising behavior from `main`**, because that is what current tests and `Policy.validate_registry` expect, and 3.0.2 callers who only saw a print were not promised an exception. Document it in the changelog as a stricter check. If the owner wants zero behavior change for 3.0.2, the facade should print like 3.0.2 and the raise stays opt-in. **Recommended:** keep the raise. It is the safer governance behavior and `main` already ships it. Call it out in the changelog so 3.0.2 users who registered extra tools are not surprised.

Do not delete `harbor_verifier.py`. Do not register platform tenant tools on this singleton. That rule is about the control plane, not this release.

### Files

- `src/govagent/registry/__init__.py` (facade, public `tool` and `registry`)
- `src/govagent/registry/manager.py` (Harbor `verify_and_resolve_tool` stays here and is called by the facade)
- `src/govagent/__init__.py` (re-export the facade; the names in `__all__` stay `tool` and `registry`)
- `tests/test_registry_facade.py` (new)
- `tests/test_harbor_registry.py` (keep; it should still pass against `govagent.registry.manager`)
- `tests/test_flow.py` (keep; it should still pass against the public registry)

### Tests

`tests/test_registry_facade.py`:

- `tool(..., oci_repository="bizzteq/malicious-db-utils", artifact_digest="sha256:x")` then `registry.verify_and_resolve_tool` raises `GovernanceViolation` (3.0.2 Harbor path through the public object).
- `tool(..., schema=FinancialTransactionIntent)` then invalid `amount` raises (current `main` path).
- After both registrations, `id(registry) is id(govagent.registry.registry)`.
- `from govagent import tool as public_tool, registry as public_registry` is the facade, and `public_registry.verify_and_resolve_tool` exists.

### Compatibility

3.0.2 `from govagent import tool, registry` keeps Harbor and dict validation results. `schema=` is additive. Returning a dict instead of `True` is the 3.0.2 contract; unpublished `main` code that compared with `is True` would break. Nothing in the repo does that. The stricter `PermissionError` on shadow tools is the one intentional behavior change and must be named in the changelog.

## 3. What waits for 3.1.0

These are already on `main` and are **not** in the 3.0.2 wheel. They are backward compatible to *add*, and they are still features.

| Symbol | Where | Recommendation |
| --- | --- | --- |
| `FinancialTransactionIntent` | `src/govagent/registry/schemas.py` | Ship in **3.0.3**. The facade test needs it, it is a new class, and old constructors do not pass it. Export it from `govagent.registry` only. Do not add it to `govagent.__all__` in 3.0.3. |
| Optional `ExecutionSnapshot` fields (`selected_model`, `cost_center`, `gl_account`, `requested_exposure_usd`, `total_tokens`, and the other defaults in `registry/schemas.py`) | `src/govagent/registry/schemas.py` | Keep them in **3.0.3**. They have defaults. 3.0.2 required `output`; `main` defaults it to `None`. That is compatible. Do not add a new required field. |
| `govagent.governance.cfo_analytics` | new module, not in `governance/__init__.py` `__all__` | **3.1.0.** Leave the file on disk if it is already on `main`, but do not export `CFOAnalyticsEngine` from `govagent.governance` or document it as stable until 3.1.0. |
| `govagent.governance.evidence` | same | **3.1.0**, same treatment. `EvidencePackGenerator` is used by `api/server.py`, which is not in the wheel. The wheel can contain the module as an unadvertised file in 3.0.3 only if cutting the release from `main` is easier than deleting it. Recommended: **do not document or export it in 3.0.3.** A 3.1.0 note adds it to `governance/__init__.py` `__all__` and to the README. |

`api/server.py`, `src/app/`, and `platform/` stay out of `[tool.poetry] packages`. 3.0.3 does not start shipping the FastAPI app inside the wheel.

### Tests for the snapshot fields

`tests/test_snapshot_compat.py` (new, small):

- Construct `govagent.registry.schemas.ExecutionSnapshot` with only `trace_id`, `status`, `output`, and `metrics` (the 3.0.2 required set, `output` still passed). Assert it validates.
- Construct it without `output` and assert the default is accepted (current `main`).
- Assert a 3.0.2-style constructor does not need `cost_center`.

## 4. `datetime.utcnow()`

### Files

- `src/govagent/telemetry/exporters/federated.py` (`FederatedAuditPayload.timestamp`, about line 18)
- `src/govagent/governance/meta.py` (`PolicyAmendmentProposal.timestamp`, about line 16)

### Change

Replace `datetime.utcnow().isoformat() + "Z"` with a timezone-aware value whose string still ends in `Z`:

```python
datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
```

Do not switch to `isoformat()` alone. Aware `isoformat()` uses `+00:00`, which is a wire-format change for anyone parsing the suffix.

### Tests

Extend `tests/test_cross_org_telemetry.py` and `tests/test_meta_governor.py` with one assertion each that the timestamp string ends with `Z` and does not contain `+00:00`. The existing assertions stay.

### Compatibility

Yes, if the suffix stays `Z`. The deprecation warning goes away. No signature change.

## 5. README

### File

`README.md` only. Do not rewrite the architecture essay.

### Fixes

| Current text | Replacement |
| --- | --- |
| `python -m spacy download en_core_web_sm` | `python -m spacy download en_core_web_lg`. Presidio's default `AnalyzerEngine` requests `en_core_web_lg`. `en_core_web_sm` does not satisfy it. |
| `RoutingMode.LOCAL_PREFERRED` in the quickstart | `RoutingMode.LOCAL_ONLY` (or `HYBRID`). The enum in `src/govagent/llm/router.py` is `LOCAL_ONLY`, `CLOUD_ONLY`, `HYBRID`. |
| `ExecutiveAgent(..., policy_path=..., router=...)` | `Policy.from_yaml(...)` passed as `policy=`, or `ExecutiveAgent.bootstrap(policy_path, router_client)`. `bootstrap`'s second argument is `router_client`, not `llm=`. |
| Any `agent.run(...)` | `await agent.execute(...)`. |

Also state that `poetry install --with dev --extras "crewai enterprise"` is what the test suite needs, and that `sentence-transformers` is required to construct `ExecutiveAgent` because `SemanticGuard` loads in `__init__`.

### Tests

No code test. A docs review checklist in the PR is enough. Optional: `tests/test_readme_contract.py` that reads `README.md` and fails if it contains `LOCAL_PREFERRED`, `policy_path=`, or `en_core_web_sm`. That test is cheap and worth adding in 3.0.3.

### Compatibility

Documentation only.

## 6. `docs/index.html`

### File

`docs/index.html`

### Change

Remove the conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`). Keep a single sample that imports symbols that exist:

```python
from govagent import ExecutiveAgent, tool
```

Delete the sample that imports `Governor`, `AgentWorkflow`, and `GuardrailBoundary`. Those names are not in the package. One version string: `3.0.3` after the bump, not a mix of `1.0.0`, `3.0.0`, and `3.0.2`.

### Tests

The optional README contract test can also fail if `docs/index.html` contains `<<<<<<<`.

### Compatibility

Documentation only.

## 7. Docker Compose and Dockerfile

### What is wrong

`docker-compose.yml` builds `dockerfile: Dockerfile`. That file is not in the repo. The web service `working_dir` is `/app/dashboard`. There is no `dashboard/` directory. The Next.js app is the repo root (`package.json`, `src/app`).

### Files

- `Dockerfile` (new)
- `docker-compose.yml` (change the web service only)

### Dockerfile

Multi-stage is unnecessary. One Python image is enough for 3.0.3:

- Base `python:3.12-slim`
- Install Poetry, `poetry install --only main` (no requirement to bake Presidio models into the image in this patch; document `en_core_web_lg` as a run step)
- `PYTHONPATH=/app/src`
- Command `uvicorn api.server:app --host 0.0.0.0 --port 8000` only if FastAPI is installed. It is a dev dependency today. **Do not move FastAPI into the library's runtime dependencies in 3.0.3.** The image should `poetry install --with dev` **or** the compose file should stay documented as a repo dev stack, not as the PyPI package. Recommended: the Dockerfile is a repo dev image (`poetry install --with dev --extras enterprise`) and the changelog says it is not the minimal wheel.

### Compose

- Keep the API service build.
- Change `govagent-dashboard` `working_dir` from `/app/dashboard` to `/app`.
- Leave the port map `3000:3000` and `8000:8000`.

### Tests

No unit test. The PR notes a local `docker compose config` check (validates the file) and does not require a full image build in CI for 3.0.3. CI cost of Presidio and spaCy images is high; section 8's workflow does not build the image.

### Compatibility

The previous compose file does not run. Pointing the UI at `/app` matches the repo. No Python API change.

## 8. `.github` and CI

### What is wrong

`.github` is a 0-byte file, not a directory. GitHub Actions cannot see workflows. The README claims Actions runs.

### Files

- Delete `.github` (the file)
- Add `.github/workflows/ci.yml`

Git cannot hold a file and a directory of the same name. The PR must remove the file in the same commit that adds the workflow.

### Workflow

On pull request and push to `main`:

1. Python 3.12.
2. `pip install poetry` and `poetry install --with dev --extras "crewai enterprise"`.
3. `poetry run python -m spacy download en_core_web_lg`.
4. `poetry run pytest -v --tb=short --asyncio-mode=auto`.

Do not set `PLATFORM_TEST_DATABASE_URL`. The platform suite must stay uncollected so this workflow does not need Postgres. Expected result on current `main`: 22 collected, 21 passed, 1 skipped (`test_slack_interaction` without Slack tokens).

Cache the Hugging Face model only if the semantic test proves flaky without it. `SemanticGuard` downloads `all-MiniLM-L6-v2` on first construct. The workflow needs network for that download once.

### Tests

The workflow is the test. No extra Python test.

### Compatibility

No import or wheel change. Forks gain a required check only after the owner turns it on in branch protection. Do not turn that on inside this plan's implementation unless the owner asks.

## 9. Release steps (do not run them yet)

When the owner approves the code changes in a later PR:

1. Branch from `main` after the fix commits are reviewed. Do not retag `3.0.2`.
2. Set `version = "3.0.3"` in `pyproject.toml` only. Do not change the package set. `packages` stays `{ include = "govagent", from = "src" }`.
3. Add `changelog.md` section `## [3.0.3]` with: the `execute()` fix, the registry facade, the stricter shadow-tool `PermissionError` if that option is kept, the timestamp helper, and the docs/Docker/CI notes. State that `cfo_analytics` and `evidence` are not stable API in this release.
4. Run the CI command locally, including the new tests in sections 1, 2, 3, and 4.
5. `poetry build`. Inspect the wheel: `govagent/registry/__init__.py` is the facade; `api/`, `src/app/`, and `platform/` are absent; `cfo_analytics.py` is either absent or not imported from `governance/__init__.py`.
6. `poetry publish -r testpypi` using TestPyPI credentials the owner provides out of band. Do not put tokens in the repo. Install the TestPyPI artifact in a clean venv with `--extra-index-url https://test.pypi.org/simple/` and run:
   - `from govagent import tool, registry, ExecutiveAgent`
   - `registry.validate_intent_schema("missing", {})` returns a dict
   - the new `tests/test_execute_validation.py` against that install
7. Only after that install check, `poetry publish` to PyPI. The owner does this. This plan does not.

If TestPyPI shows a different `registry` object than section 2, do not publish.

## 10. Explicit non-goals for 3.0.3

- No `tenant_id` argument on `ExecutiveAgent` or `bootstrap`.
- No change to `api/server.py` auth, CORS, or the default bearer token.
- No rewrite of `Policy` to read `fiscal_governance` or `alignment`. That remains the platform shim until a later minor release, and it changes the ceiling embedders see today.
- No deletion of `registry/manager.py`.
- No required field added to either `ExecutionSnapshot`.
- No publish and no version bump in the PR that adds this document.
