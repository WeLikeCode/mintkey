# Design — Agent-Stored Credentials (Phase 1: Postgres)

## Context

Mintkey brokers operator-registered credentials to agents without ever revealing plaintext (S-SEC-1). This change adds a second, deliberately different credential class: secrets an **agent itself owns** and must be able to read back (HashiCorp Vault KV model). Existing machinery to reuse: vault-adapter envelope encryption (per-write AES-256-GCM DEK wrapped by a process KEK, ADR-0003), Postgres `vault` schema storage (ADR-0021), RLS multi-tenancy (ADR-0008), the audit hash chain (ADR-0014.7), the agent-key auth path at the MCP server, and the email-tools precedent for adding an MCP tool family.

User-confirmed decisions (2026-06-10): KV-style plaintext read-back for the owner; plaintext read for shared recipients; phase 1 in Postgres; phase 2 (external providers) is design-only after phase 1 ships.

## Goals / Non-Goals

**Goals:**
- Agents store/read/list/delete named secrets via MCP tools using only their `mk_agent_` key.
- Encryption at rest with the same envelope-crypto guarantees as operator credentials.
- Operator-managed read-only sharing between agents in the same tenant.
- Every operation — including plaintext reads — audited; zero plaintext in logs/audit/spans.
- Easy-to-test API contract (every spec scenario maps to a test).

**Non-Goals:**
- External providers (HashiCorp Vault, Azure Key Vault) — phase 2, design-only follow-up.
- Secret version-history reads (KV v2 style) — phase 1 overwrites in place with a version counter.
- Agent-to-agent sharing without an operator.
- Proxy injection of agent secrets into egress calls.
- Admin UI screens (operator surface is REST; UI can follow later).

## Decisions

**D1 — Storage: new `vault.agent_secrets` table + new gRPC surface; do not reuse `vault.credentials`.**
`vault.credentials` is keyed (tenant, service, key_version) with one current credential per service, an AuthScheme branch in `GetCredential`, and service-table JOINs — agent secrets are (tenant, agent, name) with many secrets per agent and no service row. A new sibling gRPC service `AgentSecretsVault` (precedent: `SSHVaultAdapter`) gets `PutAgentSecret` / `GetAgentSecret` / `DeleteAgentSecret`, keyed by (tenant_id, secret_id). It reuses `crypto.Seal/Open`, `kek.Load`, and the Postgres store mechanics (per-tx `set_config('app.current_tenant', …)`, advisory locks). New adapter scopes `vault.secret.read` / `vault.secret.put` / `vault.secret.delete`; new boot identity `svcid_mcp` for the MCP server. No `ListAgentSecrets` RPC: listing is metadata-only and served from `public.agent_secrets` by SQL.

**D2 — Split metadata from ciphertext.**
`public.agent_secrets` holds metadata (id, tenant_id, agent_id owner FK, name, content_type, size_bytes, version, timestamps; UNIQUE(tenant_id, agent_id, name)); `vault.agent_secrets` holds (secret_id, tenant_id, key_version, wrapped_dek, enc_payload). The MCP server reads/writes metadata directly under RLS (it already has DB access) and calls the adapter for blob seal/unseal. Non-atomicity between the DB transaction and the adapter call is handled write-first-blob / commit-metadata-second; an orphaned blob from a failed commit is overwritten on retry and unreachable without a metadata row (alternative — distributed transaction — rejected as overkill).

**D3 — Agent surface is the MCP server, with in-handler authorization.**
Tools `secret_put`, `secret_get`, `secret_list`, `secret_delete` follow the email-tool skeleton: 401 guard → `set_tenant_context` → owner-or-shared check by SQL → action → `audit_emit` in the same transaction. Unlike email, there is **no downstream proxy to enforce scope**, so the handler itself is the policy decision point: owner check is `agent_secrets.agent_id == ctx.agent_id`; shared-read check is a grant-row lookup. Secrets do NOT ride `mintkey_request_token` / brokered JWTs on the agent side (a secrets pseudo-service would pollute service discovery; rejected). The MCP server authenticates to the vault-adapter with its own service identity over gRPC.

**D4 — Audit from the MCP server via the shared chokepoint helper.**
Agent-initiated writes/reads emit through `mintkey_models.audit.audit_emit` in-process (precedent: `token.denied` from `request_token.py`). Operator sharing emits from admin-api handlers as usual. New event types: `agent_secret.created/.updated/.read/.deleted`, `agent_secret_grant.created/.revoked`; new target types `agent_secret`, `agent_secret_grant`. ADR-0025 states explicitly that the MCP server (FastAPI) is an audit emission point for the agent data plane.

**D5 — Sharing authorization: any active operator of the tenant may grant; `agents.created_by` added for attribution only.**
"Only the creating operator may share" is unenforceable today — `agents` has no creator column and `agent.created` audits with `actor_id=None`. Phase 1 therefore allows any tenant operator to manage grants (consistent with how `permission_grants` and `email_permission_grants` work), and adds nullable `agents.created_by` populated on agent creation from the session operator, enabling future tightening. Documented as an assumption the owner may revisit.

**D6 — Wire IDs and the anti-enumeration rule.**
New prefixes `sec_` and `secgrant_` (lowercase single tokens, Crockford ULID body) per ADR-0017.11 extension path (ADR-0018's `svckey_` is precedent). Prefix table in openapi.yaml, tools.yaml ID comment block, and audit-event `$defs` all updated. `secret_get`/`secret_delete` return a **uniform not-found** for both nonexistent and not-visible secrets (ADR-0017.5 anti-enumeration extended to intra-tenant agent privacy). Grant endpoints (operator-facing) keep distinct 404/409/422 since operators legitimately see tenant inventory.

**D7 — Value handling and limits.**
`value` is a UTF-8 string, max 65536 bytes (covers SA JSON and SSH keys); binary material is base64'd by the agent, with optional free-text `content_type` metadata as a hint. Marked `x-mintkey-sensitive: true` in tools.yaml output. mcp-server compose mem_limit is 256m and the JSON-RPC loopback doubles body memory — 64 KiB keeps worst-case well clear.

**D8 — Contract-first order.**
openapi.yaml, tools.yaml, audit-event.schema.json, vault.proto, and ADR-0025 land before/with implementation, validated by the repo's lint commands. ADR-0025 covers: new prefixes, new event types, new error codes (`secret_not_found` uniform error), the plaintext-read-back deviation, and the MCP-server audit emission point. Known pre-existing contract drift (email UUIDs on wire, missing email entries in openapi AuditEventType enum, email tools absent from jsonrpc.py) is **not copied**: secrets use prefixed ULIDs, enums get the new entries, and tools register in REST + jsonrpc + landing + tools.yaml + bootstrap markdown.

**D9 — Testing strategy (every scenario testable).**
Unit: admin-api router tests in repo-root `tests/unit/admin_api/` (the CI-executed tree) with fake sessions; mcp-server tool tests per `test_email_tools.py` pattern. Go: envelope + store tests, RLS assertions behind the `postgres` build tag. Architecture gates: new tables registered in `test_rls_coverage.py` TENANT_SCOPED; SQLAlchemy mirror models added; `openapi_snapshot.json` updated; audit-coverage satisfied. Red-team: canary-secret store/read then grep compose logs + audit payloads + span exports for the canary (zero matches). Live e2e: store → owner read → operator share → recipient read → revoke → recipient read fails → delete, against a compose stack isolated from the developer's real volumes. Note: mcp-server tests are not currently wired into CI — a CI step is added so the new tool tests actually run.

## Risks / Trade-offs

- **[Plaintext read-back is a new threat surface]** → encryption at rest unchanged from ADR-0003; every read audited; uniform not-found anti-enumeration; canary red-team test; `x-mintkey-sensitive` markers; span-attribute denylist already CI-enforced.
- **[Metadata/blob write spans two systems without a transaction]** → blob-first write order; orphan blobs unreachable and overwritten on retry; delete is idempotent both sides.
- **[Audit chokepoint purism vs MCP-server emission]** → follows the existing `token.denied` precedent; made explicit in ADR-0025 rather than left implicit.
- **[Any-tenant-operator sharing is broader than "creating operator"]** → matches every existing grant surface; `created_by` lands now so a later ADR can tighten without schema work; flagged as owner decision.
- **[mcp-server tests not in CI today]** → add the CI step in this change; otherwise the new tool tests would be dead weight.
- **[Token/scope sprawl]** → no new agent-visible token type; brokered JWTs not used for secrets; adapter scopes are internal service-identity scopes only.

## Migration Plan

Pure addition: new tables via Liquibase 027 (MARK_RAN preconditions, rollback blocks), new endpoints/tools, no changes to existing rows or flows. Rollback = revert the changesets and remove the routers/tools. No data backfill (`agents.created_by` stays NULL for pre-existing agents).

## Open Questions

- None blocking phase 1. Phase 2 (external providers) will need: provider config model (per-tenant vs per-deployment), credential bootstrap for the providers themselves, and migration semantics between backends — addressed in the phase 2 design-only change.
