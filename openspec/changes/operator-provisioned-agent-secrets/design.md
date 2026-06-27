# Design — Operator-Provisioned Agent Secrets

> Full brainstorm record and single source of design truth: `docs/superpowers/specs/2026-06-14-operator-provisioned-agent-secrets-design.md`. This file captures the OpenSpec-level decisions and the contract-first ordering.

## Context

Phase 1 built agent self-service secrets (`secret_put/get/list/delete`, `vault.agent_secrets`, `AgentSecretsVault` gRPC, operator metadata + sharing REST). This change adds the operator-as-provisioner direction with no change to the agent surface. The hard parts are (a) a new operator **write** path that admin-api does not have today, (b) giving admin-api a vault client + put/delete scopes it does not currently hold, and (c) keeping every operator-facing response plaintext-free.

## Decisions

### D1 — Write path lives in admin-api (the audit chokepoint), not the MCP server
The MCP server is the agent data plane (auth = `mk_agent_` key). Operators have no agent key, so routing operator writes through MCP is the wrong trust boundary. admin-api already owns `DELETE` + grants for these secrets and is the audit chokepoint and the BFF's only upstream. So `POST`/`PUT` extend the existing `agent_secrets` router; admin-api gains an `AgentSecretsVault` gRPC client (mirroring the MCP server's) and the `vault.secret.put` + `vault.secret.delete` scopes for `svcid_admin_api`.

### D2 — Reveal-once is client-side; admin-api responses stay metadata-only
The operator types the value, so the browser already has it. The create/update **response is metadata-only** (no `value`), preserving the phase-1 invariant "no operator-facing response carries plaintext." The Admin UI renders the just-entered value once (Copy, then discard on dismiss/unmount). This is strictly safer than echoing the stored value back through the BFF. Consequence: there is **no** server path by which an operator re-reads a stored value.

### D3 — Create rejects duplicate names (no silent clobber)
`POST` rejects a name already present for `(tenant_id, agent_id)` with `409 name_already_exists`, so an operator cannot silently overwrite a secret the agent created itself. Rotation is the explicit `PUT` path. (Contrast: the agent's own `secret_put` overwrites with `version++` — that is the agent acting on its own namespace and is unchanged.)

### D4 — Operator delete purges ciphertext
Because admin-api now holds `vault.secret.delete`, `DELETE` calls `DeleteAgentSecret` to remove the `vault.agent_secrets` blob in addition to the metadata row, closing the phase-1 orphaned-blob TODO. Idempotent; cascades grants as before.

### D5 — Operator identity from the session; new `created_by`
Per ADR-0019 the effective identity (tenant GUC, audit `actor_id`) comes from the validated session, not the signed-request JWT body. This change threads `operator_id` into the agent-secrets handlers so `agent_secret.created`/`.updated` carry `actor_type=operator` with a real `actor_id`, and a new nullable `public.agent_secrets.created_by` records the provisioning operator (NULL when the agent self-created via `secret_put`). The same threading populates the grant `created_by` (fixing the phase-1 nil-UUID placeholder).

### D6 — Audit schema: operator actor for created/updated
`audit-event.schema.json` currently constrains `agent_secret.created`/`.updated` to agent actor. This change widens those two event definitions to also accept `actor_type: operator`. `agent_secret.read` stays agent-only (operators never read). Payloads remain identifier/metadata-only (no value, no fingerprint).

### D7 — No contract change to the agent surface or the vault proto
`mcp/tools.yaml` and `vault.proto` are untouched: the agent reads a provisioned secret through the existing `secret_get` (it is the `owner`, `agent_id` = the target agent), and `PutAgentSecret`/`DeleteAgentSecret` already exist.

### D8 — Contract-first ordering
Land in this order, each gated by the repo validators: (1) openapi.yaml + audit-event.schema.json + ADR-0026 + this OpenSpec change; (2) Liquibase 028 + SQLAlchemy mirror; (3) admin-api code + openapi snapshot; (4) admin-ui; (5) security gates; (6) e2e.

### D9 — Security invariants (CI-enforced)
1. Metadata-only operator responses (no `value`/ciphertext field anywhere in admin-api responses).
2. Writes require `mintkey_session` cookie **and** Ed25519 `x-mintkey-signed-request` agreeing on operator/tenant (ADR-0019).
3. `value` ≤ 65536 bytes; name `^[A-Za-z0-9._-]{1,128}$`.
4. Zero plaintext in logs/audit/OTel spans on the operator create/update path — phase-1 red-team canary extended; admin-api + BFF must not log request bodies.
5. RLS tenant isolation on all touched rows; identity from session.

## Testing strategy

- **admin-api unit** (test-first): create happy / 409 dup / oversize / invalid-name / cross-tenant-agent; create+update responses contain no `value`; `agent_secret.created`/`.updated` emitted with operator actor + `created_by`; vault `Put` invoked; `PUT` increments version; `DELETE` invokes `DeleteAgentSecret`; tenant isolation.
- **Red-team canary**: a known canary value provisioned via the new path appears in zero log lines, span exports, and audit payloads.
- **admin-ui**: handler tests assert writes use `apiWrite`(signed-request); render tests assert the reveal-once modal shows the value exactly once and the list/show never render a value; BFF route test asserts cookie/CSRF forwarded and body not logged.
- **Architecture gates**: openapi snapshot diff, audit-coverage, RLS coverage, SQLAlchemy mirror.
- **Live e2e** (isolated compose project, backup first): operator `POST` create → agent `secret_get` returns plaintext (access owner) → operator `PUT` rotate (version++) → operator `DELETE` → agent `secret_get` → uniform `secret_not_found`; vault blob absent post-delete.

## Risks & mitigations

- **admin-api gains write access to the secret vault** → scope limited to `vault.secret.put`/`.delete`; no `GetAgentSecret` scope for admin-api (operators still cannot read values); covered by the metadata-only response gate + red-team canary.
- **Plaintext in the create request body transiting BFF→admin-api→vault** → TLS in transit; body-logging disabled on both hops; `x-mintkey-sensitive` marker; span denylist already covers `*_secret`/`*_password` — ensure the field is never placed on a span.
- **Operator overwriting agent-owned data** → 409 on duplicate name; rotation is an explicit, audited action.
