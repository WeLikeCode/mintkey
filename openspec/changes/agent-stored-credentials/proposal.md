# Agent-Stored Credentials

## Why

Agents can consume operator-registered credentials through Mintkey today, but they have nowhere safe to keep secrets they themselves hold — a database username/password, a Google service-account JSON, an SSH private key. Agents either keep these in their own context (leaky, unaudited) or operators must register them as full Mintkey services even when no proxying is wanted. A first-class, agent-owned secret store (HashiCorp Vault KV model) closes this gap with encryption at rest, tenant isolation, full audit, and operator-controlled sharing.

## What Changes

- New agent-facing MCP tools: `secret_put`, `secret_get`, `secret_list`, `secret_delete` — an agent authenticated with its `mk_agent_` API key stores named secrets and reads them back in plaintext (owner-only by default).
- New encrypted storage: secrets are envelope-encrypted (per-secret AES-256-GCM DEK wrapped by the process KEK) by the vault-adapter in a new `vault.agent_secrets` table; metadata lives in `public.agent_secrets`. Phase 1 backend is Postgres (ADR-0021 parity).
- New operator sharing surface in admin-api REST: an operator can grant another agent in the same tenant read-only access to a secret, and revoke it. Recipients read plaintext via `secret_get`; they cannot update, delete, or re-share. Operators never see plaintext.
- New audit events for every state change AND every plaintext read: `agent_secret.created`, `agent_secret.updated`, `agent_secret.read`, `agent_secret.deleted`, `agent_secret_grant.created`, `agent_secret_grant.revoked`. Payloads carry identifiers only — never secret material.
- New wire ID prefixes `sec_` (secret) and `secgrant_` (share grant) per ADR-0017.11 extension rules; new ADR-0025 covers the contract additions and the deliberate plaintext-read-back deviation from the "returned only once" credential convention.
- `agents.created_by` column added (nullable) so agent-creator attribution exists going forward.
- **Deviation called out**: unlike operator-registered credentials (S-SEC-1: never visible to agents), agent-stored secrets are readable in plaintext by the owning agent and explicitly-granted recipient agents. The agent supplied the plaintext; the guarantee that matters here is encryption at rest, audit of every read, and zero plaintext in logs/audit/spans.

## Capabilities

### New Capabilities
- `agent-secret-storage`: agent-owned named secrets — store, plaintext read-back, list, delete, versioned overwrite, encryption at rest, size limits, anti-enumeration, audit of every operation including reads.
- `agent-secret-sharing`: operator-managed read-only share grants of one agent's secret to another agent in the same tenant — create, list, revoke, recipient plaintext read, audit.

### Modified Capabilities
<!-- none — this is a new surface; no existing spec's requirements change -->

## Impact

- **Contracts (canonical, edit first)**: `docs/architecture/contracts/mcp/tools.yaml` (4 new tools), `docs/architecture/contracts/rest/openapi.yaml` (operator share/metadata endpoints + schemas + prefix table + AuditEventType/TargetType enums), `docs/architecture/contracts/events/audit-event.schema.json` (6 new `ev_agent_secret_*` defs + `agent_secret`/`agent_secret_grant` target types), `docs/architecture/contracts/vault-adapter/vault.proto` (new `AgentSecretsVault` RPCs), new `docs/architecture/01-architecture/adr/0025-agent-stored-secrets.md` (+ `adrs/` symlink).
- **DB**: Liquibase changelog `027-agent-secrets.yaml` — `public.agent_secrets`, `public.agent_secret_grants`, `vault.agent_secrets`, `agents.created_by`; RLS `tenant_isolation` policies in the same changesets; SQLAlchemy mirror models; `tests/architecture/test_rls_coverage.py` TENANT_SCOPED registration.
- **Services**: vault-adapter (new gRPC service + scopes + `svcid_mcp` identity), mcp-server (4 tool modules + gRPC client + jsonrpc/landing/bootstrap registration), admin-api (new `agent_secrets` router + `main.py` registration + openapi snapshot).
- **Tests**: unit (admin-api + mcp-server), Go (envelope/store), architecture gates (audit coverage, RLS, sqlalchemy mirror, openapi parity), red-team canary-secret leak test, live e2e store→read→share→read-as-recipient→revoke→delete.
- **Out of scope (phase 2, design-only follow-up)**: external providers (HashiCorp Vault, Azure Key Vault) behind the same adapter interface; per-secret version history reads (KV v2); agent-to-agent sharing without operator involvement.
