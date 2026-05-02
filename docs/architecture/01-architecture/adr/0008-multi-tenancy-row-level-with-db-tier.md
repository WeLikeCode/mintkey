# ADR‑0008: Multi‑tenancy — row‑level isolation by default, DB‑per‑tenant as opt‑in high‑isolation tier

## Status
Accepted — 2026-05-10. Promoted from [`docs/proposal/P-007-multi-tenancy.md`](../../proposal/P-007-multi-tenancy.md), Option E.

## Context
Mintkey must be **multi‑tenant by architecture, single‑tenant by default**. The full analysis (five options compared, architectural implications across every container, threat‑model additions, three new quality‑attribute scenarios) lives in [P‑007](../../proposal/P-007-multi-tenancy.md). This ADR captures the accepted decision and is the canonical pointer for downstream amendments to ADRs 0003–0007.

## Decision

### Tenancy model
- **Multi‑tenant by architecture** — every domain entity is tenant‑scoped from day one. Single‑tenant deployments are a degenerate case of the multi‑tenant model.
- **Single‑tenant by default UX** — the default `docker compose up` creates one tenant (`t_default`); the UI hides tenant selection unless the active operator has membership in more than one tenant.

### Default isolation: row‑level + Postgres RLS
- Every domain table carries `tenant_id UUID NOT NULL`.
- Every domain table has a Postgres Row Level Security policy:
  ```sql
  ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
  CREATE POLICY tenant_isolation ON <table>
    USING (tenant_id = current_setting('app.current_tenant')::uuid);
  ```
- The application sets `SET LOCAL app.current_tenant = '<uuid>'` at the start of every DB transaction. Middleware in the Admin REST API, the MCP Server, the Vault Adapter, and the Audit Service all do this.
- Application code uses a non‑superuser DB role (`mintkey_app`); RLS is bypassed only by the migration role.

### Opt‑in high‑isolation tier: database‑per‑tenant
- A deployment may set `MINTKEY_TENANT_ISOLATION=database` and provide a per‑tenant DB connection map.
- Same code; different connection strategy. Liquibase runs against each tenant DB.
- Use case: regulated tenants who require cryptographic + storage‑level isolation.

### Identity model
- New entity **`Tenant`** (id, slug, display_name, status, settings, created_at).
- New entity **`OperatorTenantMembership`** (operator_id, tenant_id, role) — one operator can belong to multiple tenants with different roles per tenant.
- Sessions are bound to a single (operator, tenant) pair at any time. Switching tenants either updates the active tenant in the session or creates a new session.
- Agents are owned by exactly one tenant. Multi‑tenant agents are explicitly out of scope.
- New role **`PlatformAdmin`** (boolean on `Operator`) — can create/delete tenants and read cross‑tenant audit. Every cross‑tenant operation it performs emits its own audit event with reason.

### JWT — `tnt` claim
The brokered JWT defined in [ADR‑0006](0006-token-format-and-binding.md) is extended with a `tnt` (tenant) claim. The Egress Proxy validates `tnt` matches the registered service's tenant on every request. A token issued in tenant A cannot validate against a service in tenant B.

```json
{
  "iss": "mintkey/broker",
  "sub": "agent_01HX…",
  "aud": "svc_crm",
  "tnt": "t_acme",
  "scope": "read:contacts",
  "jti": "01HX…",
  "iat": 1715000000,
  "exp": 1715000600
}
```

### Vault Adapter contract
- Credentials are tagged with `tenant_id`.
- `get_credential(tenant_id, service_id, key_version) → (plaintext, auth_scheme, expires_at?)`.
- KEK strategy:
  - **v1 (default)**: shared KEK across tenants; DEK per credential.
  - **Phase 2 opt‑in**: per‑tenant KEK for the high‑isolation tier — each tenant has its own KEK source (separate keyfile, env var, or KMS key); cryptographic tenant isolation.

### Egress Proxy plugin
- Plugin reads JWT's `tnt` claim, looks up service's tenant, denies on mismatch.
- Cache key changes from `(service_id, key_version)` to `(tenant_id, service_id, key_version)`.
- Audit emissions include `tenant_id`.
- Kong‑syncer scopes its declarative YAML by tenant slug.

### URL conventions
Both supported; explicit form is canonical:
- **Explicit (canonical)**: `/v1/tenants/{tenant_id}/services` — used in OpenAPI, audit, documentation, machine‑to‑machine calls.
- **Implicit (convenience)**: `/v1/services` — resolves via the session's active tenant.

### Keycloak / OIDC integration
- **Default**: single Keycloak realm `mintkey`; tenant memberships live in our DB. After OIDC login, we resolve the operator's tenant memberships and prompt for tenant selection (auto‑select if one).
- **Opt‑in**: realm‑per‑tenant. Mintkey detects the realm from OIDC `iss` claim and maps to the corresponding tenant.

### Audit
- Every audit event carries `tenant_id`.
- Audit query is tenant‑scoped (`Auditor` in tenant A cannot see tenant B).
- `PlatformAdmin` cross‑tenant queries themselves emit audit events.

## Consequences

### Positive
- The system is *uniformly* tenant‑aware from day one. No retrofit cost later.
- Default deployment is operationally simple (single Postgres, single Kong, single Keycloak realm).
- High‑isolation tenants get DB‑per‑tenant without a fork.
- RLS at the DB layer is a safety net for any code path that forgets the tenant filter.

### Costs
- Every new feature must thread `tenant_id` through. Iteration 4 contracts and Phase 5 patterns make this systematic; in early Phase 1 it is discipline.
- Two connection‑management modes (shared pool vs. per‑tenant pool); engineers must remember the abstraction.
- Migration tooling runs once in the default mode and per‑tenant in the high‑isolation mode.

### Risks
- **RLS bypass via superuser**: mitigated by using the `mintkey_app` role for application code; superuser is reserved for migrations and operations.
- **Forgotten `SET LOCAL`**: mitigated by middleware that always sets it; tested by a CI integration test that asserts queries without the setting return zero rows.
- **Cross‑tenant cache poisoning** (e.g., a plugin caches without `tenant_id`): mitigated by an architecture test asserting all cache keys include `tenant_id`.

## Cross‑cutting amendments to prior ADRs

This ADR is the canonical source for the following amendments. Prior ADRs remain immutable; their `Related` sections gain a forward‑link to this ADR.

| ADR | Amendment summary |
|---|---|
| [ADR‑0003 credential storage](0003-credential-storage-strategy.md) | Credentials carry `tenant_id`; Vault Adapter contract becomes `get_credential(tenant_id, service_id, key_version)`; per‑tenant KEK is a Phase 2 opt‑in. |
| [ADR‑0004 egress proxy Kong](0004-egress-proxy-kong.md) | Plugin cache key gains `tenant_id`; JWT `tnt` claim enforced; audit emits `tenant_id`; Kong‑syncer scopes by tenant. |
| [ADR‑0005 admin tech stack](0005-admin-tech-stack.md) | Sessions are (operator, tenant); `OperatorTenantMembership` table; tenant selector in AdminJS; Keycloak realm‑per‑tenant becomes an opt‑in; new `tenants` resource. |
| [ADR‑0006 token format](0006-token-format-and-binding.md) | JWT gains `tnt` claim; broker reads tenant from agent record; proxy enforces `tnt` matches service's tenant. |
| [ADR‑0007 proxy topology](0007-proxy-deployment-topology.md) | Optional virtual‑host alias becomes `<service-slug>.<tenant-slug>.proxy.local`; URL conventions documented above; per‑tenant routing isolation. |

## Quality attributes
Three new scenarios are documented in [`03-quality-attributes.md`](../03-quality-attributes.md):
- **S‑MT‑1** — Strict tenant isolation.
- **S‑MT‑2** — Tenant onboarding ≤ 60 s.
- **S‑MT‑3** — Noisy‑neighbor isolation at the application layer.

## Threat model
The cross‑tenant section in [`05-threat-model.md`](../05-threat-model.md) enumerates: cross‑tenant data leakage, token replay, privilege escalation, backup snooping (high‑isolation tier), audit cross‑contamination, noisy‑neighbor DoS.

## Implications

### Phase 1 (per [Roadmap](../../00-vision/06-roadmap.md))
Tenant scaffolding lands in milestone 1.0 (Foundation skeleton). The seed job creates `t_default`. Multi‑tenant smoke test (1.12) is part of the Phase 1 exit criteria.

### Iteration 2
- Liquibase changelogs include `tenant_id` columns and RLS policies on every domain table.
- The change‑channel transport ([P‑009](../../proposal/P-009-change-channel-transport.md)) carries events with `tenant_id` for tenant‑scoped invalidation.

### Iteration 4 contracts
- All endpoints in `docs/contracts/rest/` use the explicit `/v1/tenants/{tenant_id}/...` form as canonical.
- All MCP tools in `docs/contracts/mcp/` resolve tenant from the agent's authentication context (no `tenant_id` parameter on tools).
- All event schemas in `docs/contracts/events/` include `tenant_id`.

### Phase 5 / Kiro readiness
- Test fixtures include multiple tenants from the start.
- The "add an X" pattern library always shows the tenant‑aware variant.

## Open follow‑ups
- `PlatformAdmin` UI — how the cross‑tenant view looks in AdminJS (a separate "Platform" view? a tenant switcher with an "All tenants" option?).
- Slug vs. UUID in URLs — recommend slug for UX with UUID fallback.
- Tenant deletion / soft‑delete / data retention policy.
- Tenant data export (GDPR‑style portability).
- Per‑tenant resource limits (rate limits on token issuance, credential count, agent count) — Phase 2.
- Cross‑tenant audit query for `PlatformAdmin` — UI patterns and audit‑of‑audit semantics.

## Related
- [P‑007 multi‑tenancy](../../proposal/P-007-multi-tenancy.md) — Accepted (this ADR).
- All prior ADRs (0003–0007) — receive amendments noted above.
- [Roadmap](../../00-vision/06-roadmap.md) — Phase 1 exit criteria include multi‑tenant smoke test.
- [Kiro readiness](../../00-vision/07-kiro-readiness.md) — patterns and fixtures must be tenant‑aware.
