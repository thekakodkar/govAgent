# govagent-platform

This package is the Phase 1 enterprise control plane. It is **not** the `govagent` distribution published on PyPI and it is not imported by `govagent`.

It stores tenants, identities, policy documents, and an append-only audit log in Postgres. Evaluation still belongs to the `govagent` library. The only library call in this phase is `govagent.policy.Policy(document)`, used to reject a document the library cannot construct. Fiscal ceilings are compared here, in `govagent_platform.services.policy_floor`, because `Policy` does not currently project `fiscal_governance`.

## Local database

`docker-compose.yml` starts Postgres 16 on host port **54329**. The `postgres` / `postgres` password is a local default only.

```bash
docker compose -f platform/docker-compose.yml up -d
```

Apply migrations with a superuser URL. The migration creates `govagent_owner` and `govagent_app` (login, `NOBYPASSRLS`, not superuser). Default local passwords are `govagent_owner_local` and `govagent_app_local`. Override them with `PLATFORM_OWNER_PASSWORD` and `PLATFORM_APP_PASSWORD` before the first migration if you need different ones.

```bash
export PLATFORM_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:54329/govagent_platform
export PLATFORM_APP_DATABASE_URL=postgresql+psycopg://govagent_app:govagent_app_local@127.0.0.1:54329/govagent_platform
export PLATFORM_SESSION_SECRET=replace-with-a-long-random-string
export PLATFORM_ENVIRONMENT=local
poetry -C platform run alembic -c alembic.ini upgrade head
poetry -C platform run python -m govagent_platform.cli bootstrap-operator --email you@example.com
poetry -C platform run uvicorn govagent_platform.api.main:create_app --factory --host 127.0.0.1 --port 8070
```

The CLI reads the password from the terminal. It refuses to run when an operator binding already exists, and it will not accept the password as an argument.

Missing `PLATFORM_DATABASE_URL`, `PLATFORM_APP_DATABASE_URL`, or `PLATFORM_SESSION_SECRET` stops the API at startup. There is no built-in bearer token.

## Tests

Platform tests are skipped at collection unless `PLATFORM_TEST_DATABASE_URL` is set, so the library suite does not require Postgres. Point that URL at `govagent_app`, not at a superuser.

```bash
export PLATFORM_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:54329/govagent_platform
export PLATFORM_TEST_DATABASE_URL=postgresql+psycopg://govagent_app:govagent_app_local@127.0.0.1:54329/govagent_platform
export PLATFORM_APP_DATABASE_URL="$PLATFORM_TEST_DATABASE_URL"
export PLATFORM_SESSION_SECRET=test-session-secret
poetry -C platform run pytest ../tests/platform -v --tb=short
```

The original library suite, from the repository root and without `PLATFORM_TEST_DATABASE_URL`, remains:

```bash
poetry run pytest -v --tb=short --asyncio-mode=auto
```

Platform tests are not collected unless `PLATFORM_TEST_DATABASE_URL` is set, so that command still reports 22 tests.

## Evaluate

`POST /tenant/v1/agents/{agent_id}/evaluate` runs `TenantExecutiveAgent`, a subclass of `ExecutiveAgent`. The loop matches govagent 3.0.3 `execute`. Schema checks call `GlobalRegistry.validate_intent_schema` with a private object that holds only that request's tool map. The process-global registry is not modified.

This package is version 0.4.0. It is not published to PyPI. Customers get a container image tagged `govagent-platform:0.4.0` or an install from a private index. The image installs `govagent[enterprise]>=3.0.3,<3.2.0` from PyPI. Do not add a job that uploads this package to `upload.pypi.org`.

## Moving this directory into its own repository

`platform/` is the standalone root. It already has `pyproject.toml`, `README.md`, `Dockerfile`, `docker-compose.yml`, `migrations/`, `govagent_platform/`, and `ui/`. The tests currently live at `../tests/platform` so the library suite can ignore them unless `PLATFORM_TEST_DATABASE_URL` is set.

To make a private repo whose root is this package:

1. Copy the contents of `platform/` to the new repository root.
2. Move `tests/platform/` to `tests/` in that repository. `tests/platform/conftest.py` already accepts both layouts: this monorepo, and a repo whose root contains `govagent_platform/` and `alembic.ini`.
3. Replace the path dependency in `pyproject.toml` with `govagent = ">=3.0.3,<3.2.0"`, matching `Dockerfile`.
4. Leave this copy in place until that repository exists. Do not publish the package to PyPI.

`PLATFORM_LLM_PROVIDER` defaults to `scripted`. Set it to `ollama` to use `OllamaClient` (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`). Constructing an agent loads Presidio, which expects the `en_core_web_lg` spaCy model, and SentenceTransformers from the `govagent[enterprise]` extra.

Votes are `POST /tenant/v1/approvals/{id}/votes` with `{"decision": "APPROVED"}` or `REJECTED`. The caller's HITL role is assigned with `PUT /tenant/v1/hitl-assignments/{identity_id}` and must be one of the roles in `HITLManager.voter_weights`.

## Notes versus the Phase 1 plan

- Alembic connects as the database superuser in `PLATFORM_DATABASE_URL`. `govagent_owner` and `govagent_app` are created by the first migration, so they cannot be the migrator. The API and the tests connect as `govagent_app` (`NOBYPASSRLS`, not a superuser, not the table owner). The sample URL that used `govagent_owner` would still pass forced RLS, and it would also be able to update `audit_events` because the owner has every privilege.
- Local passwords `govagent_owner_local` and `govagent_app_local` exist so TCP login works. They are development defaults. Set `PLATFORM_OWNER_PASSWORD` and `PLATFORM_APP_PASSWORD` before the first migration to choose different ones.
- `plans` and `global_policies` are granted `UPDATE` as well as `INSERT`. Activation retires the previous row instead of editing its document.
- Login sets `app.actor_scope=authenticate` only long enough to read memberships and tenant status. That scope is not a cookie value and its policies do not allow writes.
- Platform sessions can read `audit_events` whose `tenant_id` is null, which is how operator actions are recorded. Reading another tenant's payload tables still requires `app.platform_break_glass=on`.
- `tenants`, `plans`, and `global_policies` have row-level security forced on, so the catalog policies apply to the table owner as well.
