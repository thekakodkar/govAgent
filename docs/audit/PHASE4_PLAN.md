# Phase 4 plan: SCIM, dedicated schema, and retention

Status: plan, committed before the implementation. This file does not change runtime behavior by itself.

Phase 3 on `main` is platform `0.3.0`. It enforces quotas, exports evidence from stored rows, and rejects `dedicated_schema` and `dedicated_db` on create. Phase 4 stays in this repository. It does not publish `govagent-platform` to PyPI, does not move the library tag, and does not change `src/govagent`.

## SCIM on the membership tables

SCIM users are identities plus `tenant_memberships`. There is no second user table.

- Routes under `/tenant/v1/scim/v2`, authorized by the existing session cookie and `tenant.users.write`.
- `POST /Users` creates an identity when the email is new, then an active membership in the caller's tenant. `externalId` is stored on `identities.external_subject` when that column is empty. A password is optional. SCIM does not delete an identity.
- `GET /Users` and `GET /Users/{id}` list memberships in the caller's tenant. `userName eq "..."` is the only filter. `active` follows the membership status, not a global lockout of an identity that also belongs to another tenant.
- `PUT /Users/{id}` with `active: false` sets that membership to `revoked`. `active: true` sets it back to `active`.
- `GET /Groups` returns an empty list. Creating a group is not implemented. A group write would have to invent a mapping onto `membership_roles` and is listed under approval.

## Dedicated schema, and the dedicated database that is not built

Create still rejects a non-shared tier. Promotion is a separate operator call.

- Migration `20261107_0006_isolation_and_retention` adds `tenants.schema_name` and `isolation_promotions`. It does not drop or rewrite existing rows.
- `POST /platform/v1/tenants/{id}/isolation` with `dedicated_schema` creates a schema, copies that tenant's `cost_centers` into it, removes those rows from `public.cost_centers`, and turns row-level security on in the new schema. Later requests for that tenant set `search_path` to the schema and then `public`. Ledger and audit rows stay in `public`.
- `dedicated_db` returns 422 `dedicated_db_not_available`. A dedicated database needs its own connection URL, backup schedule, and migration runner. That routing is not in this phase. The promotion row is not written for a refused tier.

`govagent_app` is granted `CREATE` on the database so the promotion can run on the request connection and see the same transaction. It is still `NOBYPASSRLS`.

## Retention

`plans.retention_days` is the hot-row window.

- `retention_archives` stores a JSON copy before a hot row is removed. The app role may insert and select. It may not update or delete the archive.
- `POST /platform/v1/retention/purge` copies `execution_snapshots` older than the tenant's plan window into the archive, then deletes those snapshot rows. It runs with platform break-glass so every tenant is visible.
- The job never deletes or updates `audit_events` or `fiscal_ledger_entries`. `audit_events` already has no update or delete grant. The ledger stays even though the role could delete it. Both are the immutable record. The archive is the export-before-purge path for snapshots.

## Files

| Path | Role |
| --- | --- |
| `platform/migrations/versions/20261107_0006_isolation_and_retention.py` | Expand-only schema |
| `platform/govagent_platform/services/scim.py` | Users on memberships |
| `platform/govagent_platform/services/isolation.py` | Schema promotion |
| `platform/govagent_platform/services/retention.py` | Archive then delete snapshots |
| `tests/platform/test_scim.py` | Provision and revoke |
| `tests/platform/test_dedicated_schema.py` | Promotion and cross-tenant read |
| `tests/platform/test_retention.py` | Archive, snapshot removed, ledger and audit kept |

## Not in this phase

| Item | Why it waits |
| --- | --- |
| Provision a dedicated database | New connection and backup contract |
| SCIM group writes | Would freeze a mapping onto role grants |
| Delete or rewrite audit or ledger rows | Breaks the immutability guarantee |
| Any change under `src/govagent` | Published library behavior |
| Move `platform/` to a private repository | Owner asked to leave it here |
