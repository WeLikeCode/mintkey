# ADR-0025: Agent-Stored Secrets

## Status
Proposed — 2026-06-10

## Context

Agents can consume operator-registered credentials through Mintkey today, but they have nowhere safe to keep secrets they themselves hold — a database username/password, a Google service-account JSON, an SSH private key. Agents either keep these in their own context (leaky, unaudited) or operators must register them as full Mintkey services even when no proxying is wanted.

The existing S-SEC-1 quality-attribute scenario states that the plaintext credential never appears in any log, audit payload, OTel span attribute, or response visible to the agent. That guarantee was designed for **operator-registered** credentials where the agent is a consumer that never supplied the plaintext. A distinct credential class is needed: secrets an **agent itself owns** and must be able to read back (HashiCorp Vault KV model). For this class, the agent supplied the plaintext, so read-back is a documented and deliberate design choice, not a violation.

This ADR covers the wire contract additions required: new ID prefixes, new MCP tools, new admin-api REST paths, new gRPC service in the vault-adapter, new audit event types, and new error codes. It also formally records the plaintext read-back deviation and the conditions that make it safe.

### Existing machinery reused

- Vault-adapter envelope encryption: per-write AES-256-GCM DEK wrapped by the process KEK (ADR-0003, ADR-0021).
- Postgres `vault` schema storage (ADR-0021 Liquibase changelog `018`).
- RLS multi-tenancy: `tenant_id UUID NOT NULL` + `tenant_isolation` policy (ADR-0008).
- Audit hash chain (ADR-0014.7).
- Agent-key auth path at the MCP server (ADR-0009).
- Email-tools precedent for a new MCP tool family (ADR-0024).

### ID extension precedent

ADR-0017.11 establishes the ULID-with-prefix canonical wire form. ADR-0018 adds `svckey_` as the first post-baseline prefix extension. This ADR follows the same extension path.

## Decision

### D1 — Storage: new `vault.agent_secrets` + new gRPC service; do not reuse `vault.credentials`

`vault.credentials` is keyed `(tenant, service, key_version)` with one current credential per service, an `AuthScheme` branch in `GetCredential`, and service-table JOINs — agent secrets are `(tenant, agent, name)` with many secrets per agent and no service row. A new sibling gRPC service `AgentSecretsVault` (precedent: `SSHVaultAdapter` in ADR-0022) gets `PutAgentSecret` / `GetAgentSecret` / `DeleteAgentSecret`, keyed by `(tenant_id, secret_id)`. It reuses `crypto.Seal/Open`, `kek.Load`, and the Postgres store mechanics (`set_config('app.current_tenant', …)`, `pg_advisory_xact_lock`). New adapter scopes `vault.secret.read` / `vault.secret.put` / `vault.secret.delete`; new boot identity `svcid_mcp` for the MCP server. No `ListAgentSecrets` RPC: listing is metadata-only and served from `public.agent_secrets` by SQL.

### D2 — Plaintext read-back is a documented deliberate deviation from S-SEC-1 conventions

S-SEC-1 states: "The plaintext credential never appears in any log, audit payload, OTel span attribute, or response visible to the agent." That guarantee was designed for operator-registered credentials where the agent is a consumer that never supplied the plaintext.

Agent-stored secrets are a different credential class: **the agent supplied the plaintext**. The KV model (as in HashiCorp Vault KV, the established industry precedent) provides read-back to the owner by design. This ADR formally deviates from the S-SEC-1 "never visible to agent" convention for this class.

**Conditions that make this safe:**

1. **Encryption at rest** — same AES-256-GCM envelope as operator credentials; KEK rotation covers these secrets identically.
2. **Every read is audited** — `agent_secret.read` events carry `secret_id`, `version`, `reader_agent_id`, and an `access` marker (`owner` or `shared`, matching the tool-surface vocabulary). No audit payload carries the value.
3. **Anti-enumeration** — `secret_get` and `secret_delete` return a uniform not-found for both nonexistent and not-visible secrets, preventing cross-agent probing.
4. **Zero plaintext in telemetry** — `x-mintkey-sensitive: true` on the output field; canary red-team test in the CI suite verifies zero matches in logs, audit payloads, and span exports.
5. **No proxy injection** — agent secrets are never injected into egress HTTP calls; the plaintext path is read-back to the owning agent only.
6. **Span-attribute denylist** — already CI-enforced for `*_token`, `*_secret`, `*_password`, `*_passphrase` (ADR-0017.6); these cover agent secret values by pattern.

### D3 — New wire ID prefixes: `sec_` and `secgrant_`

Following ADR-0017.11 and the ADR-0018 extension precedent:

| Prefix       | Resource                  | Pattern                            |
|---|---|---|
| `sec_`       | AgentSecret               | `^sec_[0-9A-HJKMNP-TV-Z]{26}$`    |
| `secgrant_`  | AgentSecretGrant          | `^secgrant_[0-9A-HJKMNP-TV-Z]{26}$` |

These prefixes are added to the prefix table in `openapi.yaml` `info.description`, the `$defs` comment block in `tools.yaml`, and `$defs/secret_id` / `$defs/secgrant_id` in `audit-event.schema.json`.

### D4 — Six new audit event types and two new target types

New event types (all emit identifier-only payloads — no secret values):

| Event type                      | Actor         | Target type            |
|---|---|---|
| `agent_secret.created`          | agent         | `agent_secret`         |
| `agent_secret.updated`          | agent         | `agent_secret`         |
| `agent_secret.read`             | agent         | `agent_secret`         |
| `agent_secret.deleted`          | agent         | `agent_secret`         |
| `agent_secret_grant.created`    | operator      | `agent_secret_grant`   |
| `agent_secret_grant.revoked`    | operator      | `agent_secret_grant`   |

New target types: `agent_secret`, `agent_secret_grant`.

The `agent_secret.read` event is unusual in that it audits a read, not a write. This is the correct behaviour: plaintext read-back is a sensitive operation that must be traceable. Precedent: the SSH proxy audits session starts and session I/O per ADR-0022.

Idempotent no-op deletes/revokes (the row was already gone) do NOT emit an audit event: nothing changed state, and the schema-required identifiers (recipient, owner) are unknowable once the row is deleted. This deliberately deviates from the email-permission-grants precedent of emitting on the already-gone path.

### D5 — New error code: `secret_not_found`

The agent-facing surface (`secret_get`, `secret_delete`) applies the anti-enumeration rule: "secret does not exist" and "secret exists but caller has no access" are indistinguishable. A single error code `secret_not_found` covers both cases, added to the `x-mintkey-error-codes` list in `openapi.yaml` and the `error_code` enum in `tools.yaml`.

The operator-facing grant endpoints (admin-api REST) keep distinct 404/409/422 responses because operators legitimately see the tenant's full inventory and have no enumeration risk.

### D6 — MCP server as audit emission point for the agent data plane

ADR-0014.7 states that the audit chokepoint is the FastAPI Admin REST API. The MCP server is a FastAPI application (ADR-0009) and already emits `token.denied` audit events in-process via `mintkey_models.audit.audit_emit` (the existing `request_token.py` handler). This ADR formalises the MCP server as an audit emission point for the **agent data plane** — tools that the agent calls directly, without a downstream proxy in the write path.

The `mintkey_models.audit.audit_emit` chokepoint helper is the same helper used by admin-api, so the invariants (hash chain, prev_hash, per-tenant chain) are preserved.

### D7 — Sharing authorization: any active tenant operator may grant; `agents.created_by` added for attribution

"Only the creating operator may share" is currently unenforceable — the `agents` table has no creator column and `agent.created` audits with `actor_id = None`. Phase 1 allows any tenant operator to manage grants (consistent with `permission_grants` and `email_permission_grants`). A nullable `agents.created_by` column is added, populated on agent creation from the session operator, enabling future tightening without schema work.

### D8 — Agent surface scopes: `write:secrets`, `read:secrets`, `delete:secrets`

These are MCP-server internal authorization scopes, not brokered JWT scopes (agent secrets do not ride `request_token` / brokered JWTs). They are enforced by the MCP server handler against the calling agent's identity. They are not stored in the `permission_grants` table — secrets are an agent-private surface.

### D9 — Phase 2 (external providers) explicitly deferred

HashiCorp Vault KV v2 and Azure Key Vault behind the same `AgentSecretsVault` adapter interface are out of scope for Phase 1. Phase 2 will need: provider config model (per-tenant vs per-deployment), credential bootstrap for the providers themselves, migration semantics between backends, and per-secret version history reads. These are tracked as open follow-ups below.

## Consequences

### Positive

- Agents have a safe, audited, encrypted-at-rest place to store secrets they own.
- No new token type; brokered JWTs are not involved in the agent secret path.
- Full audit trail for every read, not just writes.
- Operator-managed sharing without agent-to-agent coordination.
- Phase 2 (external providers) can swap the adapter implementation without touching the wire contract.

### Costs

- New `vault.agent_secrets` table + `public.agent_secrets` + `public.agent_secret_grants` tables (Liquibase 027).
- New gRPC service with three RPCs in vault-adapter.
- Four new MCP tool handlers in mcp-server.
- New admin-api router with five REST paths.
- `agents.created_by` nullable column (Liquibase 027, no backfill).

### Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Plaintext read-back is a new threat surface | Medium | Encryption at rest; every read audited; anti-enumeration; canary red-team; `x-mintkey-sensitive` markers; span denylist CI-enforced |
| Metadata/blob write spans two systems without a distributed transaction | Low | Blob-first write order; orphan blobs overwritten on retry; delete idempotent both sides |
| Audit from MCP server vs admin-api chokepoint | Low | Formalised in this ADR; `token.denied` is the established precedent; same `audit_emit` helper |
| Any-tenant-operator sharing broader than "creating operator" | Low | Matches existing grant surfaces; `created_by` lands now for future tightening |

## Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| Reuse `vault.credentials` | Different key structure (tenant, agent, name) vs (tenant, service, key_version); conflating the two adds accidental complexity to `GetCredential` |
| Secrets as pseudo-services in `services` table | Pollutes service discovery; agents would see their own secrets in `list_services` |
| Brokered JWT for secret access | No downstream proxy in path; a secrets pseudo-service adds enumeration risk |
| No read-back (write-only) | Breaks the KV model; agents cannot validate what they stored; impractical |

## Amends

- ADR-0003 / ADR-0021: `AgentSecretsVault` is a second vault gRPC service using the same envelope-crypto primitives; `vault.agent_secrets` is a second table in the `vault` schema.
- ADR-0014.7: MCP server is a second audit emission point for the agent data plane, in addition to admin-api.
- ADR-0017.11: Adds `sec_` and `secgrant_` to the wire prefix table.
- ADR-0017.10: Adds `secret_not_found` to the `mintkey:code` closed enum.

## Open Follow-ups

- Phase 2: HashiCorp Vault KV v2 / Azure Key Vault backend behind `AgentSecretsVault` adapter interface.
- Phase 2: Per-secret version history reads (KV v2 style).
- Phase 2: Agent-to-agent sharing without operator involvement.
- Follow-up: Tighten sharing to "creating operator only" once `agents.created_by` is populated in production.
- Follow-up: Admin UI screens for operator secret management.

## Related

- ADR-0003: Credential storage strategy (envelope encryption)
- ADR-0008: Multi-tenancy (RLS)
- ADR-0009: MCP Server stack
- ADR-0014.7: Audit hash chain + chokepoint
- ADR-0017.10: `mintkey:code` closed enum
- ADR-0017.11: ULID-with-prefix canonical wire form
- ADR-0018: `svckey_` prefix extension precedent
- ADR-0021: Vault storage backend (Postgres)
- ADR-0022: SSH bastion (audit of reads precedent)
- ADR-0024: Email proxy (MCP tool family precedent)
