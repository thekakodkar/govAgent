# Phase 4 plan: SCIM, dedicated schema, and retention

> The control plane is no longer in this public repository. `govagent-platform` is at https://github.com/thekakodkar/govagent-platform (`main` `f153f6e`). Paths below that begin with `platform/` or `tests/platform/` describe the tree before that move.

Status: implemented, then moved to the private repository. `dedicated_db` stays unavailable. This is a settled decision: the control plane keeps one shared database plus optional `dedicated_schema` promotion, and it will not provision a database per tenant.

## SCIM on the membership tables

SCIM users are identities plus `tenant_memberships`. There is no second user table.

- Routes under `/tenant/v1/scim/v2`, authorized by the existing session cookie and `tenant.users.write`.
- `POST /Users` creates an identity when the email is new, then an active membership in the caller's tenant. `externalId` is stored on `identities.external_subject` when that column is empty. A password is optional. SCIM does not delete an identity.
- `GET /Users` and `GET /Users/{id}` list memberships in the caller's tenant. `userName eq "..."` is the only filter. `active` follows the membership status, not a global lockout of an identity that also belongs to another tenant.
- `PUT /Users/{id}` with `active: false` sets that membership to `revoked`. `active: true` sets it back to `active`.
- `/Groups` is a tenant role. System roles `tenant_admin` and `tenant_auditor` are visible and assignable. Custom groups are roles with `scope = tenant` and this tenant's id. Member changes write `membership_roles` for this tenant only. Deleting a system role returns 403. `display_name` and `external_id` on `roles` are the only added columns.

## Dedicated schema, and the dedicated database that is not built

Create still rejects a non-shared tier. Promotion is a separate operator call.

- Migration `20261107_0006_isolation_and_retention` adds `tenants.schema_name` and `isolation_promotions`. It does not drop or rewrite existing rows.
- `POST /platform/v1/tenants/{id}/isolation` with `dedicated_schema` creates a schema, copies that tenant's `cost_centers` into it, removes those rows from `public.cost_centers`, and turns row-level security on in the new schema. Later requests for that tenant set `search_path` to the schema and then `public`. Ledger and audit rows stay in `public`.
- `dedicated_db` returns 422 `dedicated_db_not_available`. The owner settled this on 2026-11-05: do not add a connection, backup, or migration runner per tenant.

`govagent_app` is granted `CREATE` on the database so the promotion can run on the request connection and see the same transaction. It is still `NOBYPASSRLS`.

## Retention

`plans.retention_days` is the hot-row window.

- `retention_archives` stores a JSON copy before a hot row is removed. The app role may insert and select. It may not update or delete the archive.
- `POST /platform/v1/retention/purge` copies `execution_snapshots` older than the tenant's plan window into the archive, then deletes those snapshot rows. It runs with platform break-glass so every tenant is visible.
- The job never deletes or updates `audit_events` or `fiscal_ledger_entries`. Migration `20261108_0007` revokes `UPDATE` and `DELETE` on `fiscal_ledger_entries` from `govagent_app`, and does the same for copies of `fiscal_ledger_entries` or `audit_events` inside any `tenant_<uuid>` schema. Postgres now enforces the append-only ledger the way it already enforces the audit log. Snapshot archive-and-purge is the only retention delete.

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

| Item | Decision |
| --- | --- |
| Provision a dedicated database | Settled no. `dedicated_db` stays 422 `dedicated_db_not_available`. |
| SCIM group writes | Settled yes. Groups are tenant roles and `membership_roles`. |
| Delete or rewrite audit or ledger rows | Settled never. `20261108_0007` revokes those privileges. |
| Library 3.1.0 | Approved separately. Policy projection, governance exports, and the Harbor client are in `src/govagent` and are not tagged or published. |
| Move `platform/` out of this repo | Done. The source is https://github.com/thekakodkar/govagent-platform. |
