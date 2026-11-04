# govagent-platform changelog

## 0.4.0

- SCIM users on the existing identity and membership tables. Group writes are not implemented.
- Operator promotion of one tenant into a dedicated schema. Dedicated databases are refused.
- Retention purge archives old execution snapshots and does not delete audit or ledger rows.

Platform versions are independent of the `govagent` library on PyPI. This package is not published to PyPI.

## 0.3.0

- Request-local tool validation. Tenant tools are not inserted into the process-global registry.
- Plan quotas: `max_agents` and `monthly_tco_ceiling_usd`.
- Compliance export and CFO risk overview from stored snapshot and ledger rows.
- OpenTelemetry spans on evaluate and vote.
- OIDC start and callback for providers whose secret locator is `stub://`.
- Create rejects `dedicated_schema` and `dedicated_db`.
- Release image `platform/Dockerfile` pins `govagent[enterprise]==3.0.3`.
