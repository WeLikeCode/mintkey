# ADR‑0016: Round‑2 corrections from second adversarial pass

## Status
Accepted — 2026-05-10. Amends [ADR‑0006](0006-token-format-and-binding.md), [ADR‑0013](0013-adminjs-pin.md), and [ADR‑0014](0014-iter-1-2-corrections.md). Adds requirements to iteration‑4 contracts and a Phase‑1 milestone. Defers a longer list of medium‑severity items to [`docs/01-architecture/open-questions.md`](../open-questions.md).

## Context
The second adversarial pass on the corrected state (post ADR‑0014 / 0015) surfaced ~20 follow‑up issues. Seven need immediate resolution to keep iteration‑4 contracts coherent and Phase‑1 implementable; the rest are tracked in the open‑questions register. This ADR captures the seven decisions in one place, each as a narrow amendment.

## Decisions

### 16.1 `jti` replay denylist stored in Postgres (amends [ADR‑0014.6](0014-iter-1-2-corrections.md))

**Original**: ADR‑0014.6 has FastAPI keep an in‑memory 5‑minute `jti` denylist for AdminJS↔FastAPI signed‑request replay protection.

**Problem**: in a multi‑replica FastAPI deployment (Phase 2 HA), each replica has its own denylist; the same `jti` can be replayed against a different replica within the JWT TTL window.

**Correction**: the `jti` denylist lives in Postgres:

```sql
CREATE TABLE admin_request_jti (
  jti        UUID         PRIMARY KEY,
  expires_at TIMESTAMPTZ  NOT NULL
);
CREATE INDEX idx_admin_jti_expires ON admin_request_jti(expires_at);
```

- FastAPI does an `INSERT … ON CONFLICT (jti) DO NOTHING RETURNING jti`. Empty result = replay; rejected with 401.
- A periodic cleanup job (every 5 min) deletes rows where `expires_at < now()`.
- All FastAPI replicas share state via Postgres; cross‑replica replay impossible within the JWT TTL window.

**Trade**: one DB write per AdminJS → FastAPI call. AdminJS request volume is low (operator clicks); cost is negligible. Schema lives in Liquibase per ADR‑0015.

### 16.2 JWKS force‑refresh on unknown `kid` (amends [ADR‑0006](0006-token-format-and-binding.md))

**Original**: ADR‑0006 says verifiers cache JWKS for 5 min.

**Problem**: when the broker rotates a signing key, JWTs signed with the new `kid` arrive at verifiers (proxy plugin, MCP server) **before** the cached JWKS expires. Verifier rejects with 401 until the cache TTL elapses.

**Correction**: when a verifier sees a JWT with an unknown `kid`, it MUST:
1. Force‑refresh the JWKS once.
2. Re‑attempt verification.
3. Reject only if the refreshed JWKS still doesn't contain the `kid`.

Refresh attempts are rate‑limited per verifier instance: at most one force‑refresh per `(verifier_instance, kid)` per minute, to prevent JWKS‑hammering on truly bogus tokens.

This makes broker key rotation transparent: signing‑key rotation publishes the new public key; verifiers pick it up on first JWT signed with it. No coordinated cache flush required.

### 16.3 PlatformAdmin tenant‑scoping bypass in AdminJS (amends [ADR‑0013](0013-adminjs-pin.md))

**Original**: ADR‑0013 has every AdminJS resource `before` hook filtering by `req.session.tenant_id`. ADR‑0008 introduces `PlatformAdmin` for cross‑tenant operations, but the AdminJS path was never spelled out.

**Correction**:
- Sessions for `PlatformAdmin` operators carry `is_platform_admin = true`. The session's `tenant_id` is initially `null`; the operator can pin to a single tenant via the tenant selector or stay in "All Tenants" mode.
- Resource `before` hooks check the flag: if `is_platform_admin && tenant_id == null`, **skip the application‑layer tenant filter**.
- AdminJS list views show a `Tenant` column when in "All Tenants" mode.

**RLS policy update** (Liquibase changeset, per [ADR‑0015](0015-liquibase-schema-source-of-truth.md)) — every domain table's policy is amended to OR in the platform‑view escape:

```sql
CREATE POLICY tenant_isolation ON services
  USING (
    tenant_id = current_setting('app.current_tenant', true)::uuid
    OR current_setting('app.platform_admin_view', true) = 'on'
  );
```

The application sets `SET LOCAL app.platform_admin_view = 'on'` in addition to `app.current_tenant` for `PlatformAdmin` cross‑tenant queries. The tenant_isolation policy passes either condition. Every cross‑tenant read by a `PlatformAdmin` emits an audit event with `actor_type=platform_admin` and the resource(s) touched.

The RLS architecture test ([ADR‑0014.8](0014-iter-1-2-corrections.md)) is updated to recognize this pattern as legitimate (the OR clause is an allowed deviation from "tenant_id = …").

### 16.4 Permission `constraints` is a closed schema (iteration 4 contract change)

**Original**: subagent left `Permission.constraints` as `additionalProperties: true` (open ABAC).

**Problem**: Kiro generates sloppy validation if the field is open. Operators have no documented rules to follow.

**Correction**: iteration‑4 OpenAPI defines a closed `Constraints` schema. v1 ABAC dimensions:

```yaml
Constraints:
  type: object
  additionalProperties: false
  properties:
    rate_limit:
      type: object
      additionalProperties: false
      properties:
        requests_per_second: { type: integer, minimum: 1 }
        burst:               { type: integer, minimum: 1 }
    time_window:
      type: object
      additionalProperties: false
      properties:
        timezone:    { type: string, description: "IANA tz name, e.g., Europe/Bucharest" }
        days:        { type: array, items: { type: string, enum: [Mon, Tue, Wed, Thu, Fri, Sat, Sun] } }
        start_local: { type: string, pattern: "^[0-2][0-9]:[0-5][0-9]$" }
        end_local:   { type: string, pattern: "^[0-2][0-9]:[0-5][0-9]$" }
    request_path_prefix:
      type: array
      items: { type: string }
      description: "Allowed path prefixes within the registered service."
    source_ip_allowlist:
      type: array
      items: { type: string, format: cidr }
```

New constraints in future iterations require an explicit ADR + contract version bump.

### 16.5 `mtls` auth scheme (iteration 4 contract change)

**Original**: glossary lists mTLS as a credential type; subagent's enum had 6 values without `mtls`.

**Correction**: add `mtls` to the `Credential.auth_scheme` enum in OpenAPI, MCP `describe_service` output, change events, audit events, and `vault.proto`'s enum.

Credential value for `mtls` is a base64‑encoded PEM bundle containing both the **client certificate** and the **client private key**. The Vault Adapter envelope‑encrypts both as one blob; the Egress Proxy plugin uses them to establish mTLS to the backend per‑request (private key never serialized to logs).

Iteration‑4 contracts: enum addition + `MtlsCredentialValue` schema variant + audit event payloads include `auth_scheme: mtls` examples.

### 16.6 `internal_auth.enabled` and other admin settings — toggle endpoints (iteration 4 contract change)

**Original**: ADR‑0005 says internal‑auth is "operator‑toggleable" but no admin endpoint existed.

**Correction**: iteration‑4 OpenAPI adds a small admin‑settings surface (PlatformAdmin only, every change emits `settings.updated`):

```
GET    /v1/admin/settings
PATCH  /v1/admin/settings
```

Closed schema:
```yaml
AdminSettings:
  type: object
  additionalProperties: false
  properties:
    internal_auth:
      type: object
      additionalProperties: false
      properties:
        enabled:         { type: boolean }
        can_be_disabled: { type: boolean, readOnly: true }   # false until first OIDC login validated
    oidc:
      type: object
      additionalProperties: false
      properties:
        issuer:               { type: string }
        client_id:            { type: string }
        auto_provision_role:  { type: string, enum: [Admin, Auditor, AgentOwner, none] }
    audit:
      type: object
      additionalProperties: false
      properties:
        retention_days_security_relevant: { type: integer, minimum: 30 }
        retention_days_proxy_hits:        { type: integer, minimum: 1 }
```

`can_be_disabled` is a server‑set guard: internal auth cannot be disabled until at least one operator has successfully logged in via OIDC and has the `Admin` role.

### 16.7 MCP behavior on tenant or agent deletion (iteration 4 contract clarification)

**Original**: subagent flag — semantics undefined when an agent's tenant is deleted, or the agent itself is revoked, mid‑call.

**Correction** (added to MCP tool documentation in iteration‑4 contracts):

**Active sessions** when an agent is revoked or its tenant is deleted:
- HTTP/SSE: server emits a final error frame with code `auth.revoked` or `tenant_deleted`, then closes the connection.
- stdio: server prints the same error frame, then EOF.

**New tool calls** bearing the agent's API key after revocation/deletion: `401 Unauthorized` with `mintkey:code = agent_revoked` or `tenant_deleted`. No further tool execution.

**In‑flight tool calls** already past authentication:
- Read‑only tool calls (`list_services`, `describe_service`, `get_openapi`): complete with current snapshot; no new state changes occur regardless.
- State‑changing tool calls (`request_token`): abort with `503 Service Unavailable` and `mintkey:code = tenant_deleted`.

**Cascade on tenant deletion** (additional iteration‑4 audit‑event behavior):
- Tenant → all agents revoked (one `agent.revoked` event each).
- Tenant → all services soft‑deleted (one `service.removed` event each).
- Tenant → all credentials revoked (one `credential.revoked` event each).
- Tenant → final `tenant.deleted` event with payload `cascade_count: { agents, services, credentials, permissions }`.
- Audit chain retained per the retention policy in [ADR‑0014.7](0014-iter-1-2-corrections.md) (chain stays after tenant purge — this is the canonical record).

## Consequences

### Positive
- All seven 🟡 high items from the second adversarial pass are now resolved.
- iteration‑4 contracts have a closed permission‑constraints schema, the `mtls` auth scheme, and an admin‑settings surface — Kiro can generate clean code without guessing.
- AdminJS PlatformAdmin path is concrete; the RLS escape is documented and tested.
- JWT key rotation is genuinely transparent.

### Costs
- One DB write per AdminJS→FastAPI request for `jti` denylist insert (negligible).
- RLS policies on every domain table become slightly more complex (OR clause). The arch test recognizes the pattern.
- The audit‑settings endpoint is one more PlatformAdmin surface to test and audit.

### Risks
- **PlatformAdmin RLS escape**: the OR clause is the failure point. A bug that sets `app.platform_admin_view = 'on'` outside a PlatformAdmin context = global cross‑tenant exposure. Mitigation: middleware sets it only for authenticated PlatformAdmin sessions; integration test fuzzes with non‑PlatformAdmin sessions trying to set the flag and asserts the middleware refuses.
- **`internal_auth.can_be_disabled` race**: an admin disables internal auth before validating their OIDC login. The `can_be_disabled` server guard handles this — disable rejected until the precondition is true.

## Implications
- **iteration 4 contracts** require touch‑ups to OpenAPI (new endpoints, new schemas, new enum value), to MCP tools doc (deletion semantics), to audit‑event schema (`tenant.deleted` payload, `settings.updated`), and to vault.proto (`mtls` enum).
- **Liquibase changelogs** add the `admin_request_jti` table and the platform‑admin RLS escape on every domain table.
- **RLS architecture test** is updated to accept the OR escape and to verify PlatformAdmin middleware sets the flag only for valid PlatformAdmin sessions.

## Related
- [ADR‑0006 token format](0006-token-format-and-binding.md) — JWKS refresh behavior.
- [ADR‑0013 AdminJS pin](0013-adminjs-pin.md) — PlatformAdmin path.
- [ADR‑0014 iter 1+2 corrections](0014-iter-1-2-corrections.md) — `jti` denylist storage; RLS arch test.
- [ADR‑0015 Liquibase schema](0015-liquibase-schema-source-of-truth.md) — schema changes.
- [open‑questions register](../open-questions.md) — items not in this ADR.
