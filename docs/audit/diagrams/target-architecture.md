# GovAgent enterprise target architecture

> The control plane is no longer in this public repository. `govagent-platform` is at https://github.com/thekakodkar/govagent-platform. These diagrams are the Phase 0 proposal.

These diagrams are the Phase 0 proposal. They describe a control plane that calls the existing `govagent` library. They do not replace that library.

## Runtime and administration

```mermaid
flowchart TB
  subgraph clients [Callers]
    platformUi[Platform admin console]
    tenantUi[Tenant admin console]
    libraryCallers[Existing govagent library callers]
  end

  subgraph plane [Enterprise control plane - new package]
    gateway[Admin and session API]
    identity[Identity, membership, RBAC]
    policySvc[Policy service]
    runtime[Runtime facade]
    auditWriter[Append-only audit writer]
    secrets[Secret references]
  end

  subgraph data [PostgreSQL - shared schema]
    rls[Row-level security on tenant_id]
    catalog[Tenants, plans, identities, roles]
    records[Policies, agents, tools, approvals, ledger, audit]
  end

  subgraph library [govagent library - unchanged public API]
    agent[ExecutiveAgent and Policy]
    guards[PrivacyGuard, SemanticGuard, CircuitBreaker]
    hitl[HITLManager and adapters]
    registry[Registry and HarborVerifier]
    telemetry[TelemetryManager and exporters]
    reports[MetaGovernor, EvidencePackGenerator, CFOAnalyticsEngine]
  end

  subgraph sinks [Tenant-configured sinks]
    soc[CloudWatch, Azure Monitor, federated sinks]
  end

  platformUi --> gateway
  tenantUi --> gateway
  libraryCallers --> agent
  gateway --> identity
  gateway --> policySvc
  gateway --> runtime
  gateway --> auditWriter
  identity --> rls
  policySvc --> rls
  auditWriter --> rls
  secrets --> rls
  rls --> catalog
  rls --> records
  policySvc --> agent
  runtime --> agent
  runtime --> guards
  runtime --> hitl
  runtime --> registry
  auditWriter --> telemetry
  telemetry --> soc
  reports --> records
```

## Platform administration and tenant administration

```mermaid
flowchart LR
  subgraph operator [Platform administration]
    tenants[Tenants and lifecycle]
    plans[Plans and quotas]
    floor[Global policy floor]
    operators[Operator accounts]
    flags[Feature flags and break-glass]
  end

  subgraph tenant [Tenant administration]
    users[Tenant users and roles]
    overlay[Tenant policies that tighten the floor]
    agents[Agents]
    tools[Legislated tools]
    quorum[HITL roster and quorum]
    sinks[Telemetry sinks and cost centers]
  end

  floor --> overlay
  plans --> tenants
  tenants --> users
  overlay --> agents
  tools --> agents
  quorum --> agents
  sinks --> agents
```

## Request isolation

```mermaid
sequenceDiagram
  participant Client
  participant API as Control plane API
  participant DB as PostgreSQL
  participant Lib as govagent library

  Client->>API: Authenticated request
  API->>API: Resolve actor scope and tenant membership
  API->>DB: BEGIN; SET LOCAL app.actor_scope; SET LOCAL app.tenant_id
  DB->>DB: RLS allows only that tenant_id
  API->>Lib: Construct Policy, guards, and agent for this request
  Lib-->>API: Evaluation or snapshot
  API->>DB: Insert audit_events and ledger rows
  API->>DB: COMMIT
  API-->>Client: Response scoped to the tenant
```

## Logical data model

```mermaid
erDiagram
  PLANS ||--o{ TENANTS : assigns
  TENANTS ||--o{ TENANT_MEMBERSHIPS : has
  IDENTITIES ||--o{ TENANT_MEMBERSHIPS : joins
  TENANT_MEMBERSHIPS ||--o{ MEMBERSHIP_ROLES : grants
  ROLES ||--o{ MEMBERSHIP_ROLES : used_by
  ROLES ||--o{ ROLE_PERMISSIONS : allows
  TENANTS ||--o{ TENANT_POLICIES : owns
  GLOBAL_POLICIES ||--o{ TENANT_POLICIES : floors
  TENANTS ||--o{ AGENTS : owns
  TENANT_POLICIES ||--o{ AGENTS : governs
  TENANTS ||--o{ TOOL_MANIFESTS : legislates
  TENANTS ||--o{ APPROVAL_REQUESTS : raises
  AGENTS ||--o{ APPROVAL_REQUESTS : triggers
  APPROVAL_REQUESTS ||--o{ APPROVAL_SIGNATURES : collects
  TENANTS ||--o{ EXECUTION_SNAPSHOTS : records
  TENANTS ||--o{ FISCAL_LEDGER_ENTRIES : accumulates
  TENANTS ||--o{ TELEMETRY_SINKS : configures
  TENANTS ||--o{ COST_CENTERS : allocates
  TENANTS ||--o{ AUDIT_EVENTS : appends
  IDENTITIES ||--o{ AUDIT_EVENTS : acts
```
