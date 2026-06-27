# Design — Operator-Provisioned Agent Secrets

> **Status:** Approved (brainstorm) — 2026-06-14
> **Branch:** `feat/operator-provisioned-agent-secrets`
> **Campaign:** phase 3 of the agent-secrets campaign (phase 1 = agent self-service secrets, PR #213; phase 2 = external providers, design-only).
> **Canonical plan:** `openspec/changes/operator-provisioned-agent-secrets/` + ADR-0026. This document is the brainstorm record and the single source of design truth those artifacts reference.

---

## 1. Goal

Let an **operator provision a credential into an agent's namespace through the Admin UI**, manage it (list / update / delete / share), and have the **agent retrieve it via the existing `secret_get` API** — without weakening any of Mintkey's plaintext-handling guarantees.

This is purely additive to phase 1. The agent MCP surface (`secret_put/get/list/delete`) is **unchanged**.

## 2. Background (what already exists, phase 1 / PR #213)

- Agents self-serve their own secrets via MCP `secret_put/get/list/delete`; the **owning agent reads plaintext back** (KV model), governed by ADR-0025's deviation from S-SEC-1 *because the agent supplied the plaintext*.
- admin-api has a **metadata-only** REST surface for agent secrets: `GET` list, `GET` one, `DELETE`, plus grant `POST`/`GET`/`DELETE`. **No operator-facing response carries a plaintext value**, and **there is no operator "create secret" endpoint** — creation happens only agent-side via MCP `secret_put`.
- admin-ui has **no agent-secrets UI at all**.
- Storage: separate `vault.agent_secrets` table + `AgentSecretsVault` gRPC (`PutAgentSecret` / `GetAgentSecret` / `DeleteAgentSecret`), AES-256-GCM envelope. **Only the MCP server holds the vault client + `vault.secret.*` scopes today; admin-api does not.**
- Tables: `public.agent_secrets` (metadata, unique `(tenant_id, agent_id, name)`), `public.agent_secret_grants`, `vault.agent_secrets`, plus a nullable `agents.created_by` column added in changelog 027.

## 3. Locked decisions (from brainstorm, 2026-06-14)

| # | Decision | Choice |
|---|---|---|
| D1 | Operator plaintext visibility | **Reveal-once on create/update**, rendered **client-side** from the typed value; inventory and all admin-api responses stay **metadata-only**. |
| D2 | Operator action scope | **Create + Update/rotate + Delete + Manage sharing grants.** |
| D3 | Name collision on operator create | **Reject with HTTP 409** (`name_already_exists`); no silent clobber. |
| D4 | Credential shape | **Freeform** `name` + `value` + optional `content_type` (matches phase-1 KV model). |
| D5 | Write path location | **Extend admin-api** `agent-secrets` router; admin-api gains a vault client + `vault.secret.put`/`.delete` scopes. |
| D6 | UI placement | **Top-level `agent-secrets` AdminJS resource** (RestResource, filterable by `agent_id`) + a "Manage secrets" action on the agent show page. |
| D7 | Opportunistic fix | Thread `operator_id` from the validated session into admin-api handlers (needed for audit `actor_id` + `created_by`); this also fixes the existing grant-handler `created_by` nil-UUID placeholder. Approved in scope. |

### D1 refinement (important)
Because the **operator types the value**, the browser already holds it. Reveal-once is therefore rendered **client-side** — admin-api's create/update responses are **metadata-only and never echo a stored secret back to an operator**. This preserves the phase-1 invariant ("no operator-facing response carries plaintext"), strictly better than round-tripping the value back through the BFF. The modal shows what was just entered, offers Copy, then clears on dismiss/unmount.

## 4. Architecture & data flow

### Create (operator → agent)
```
Operator types name + value + content_type in Admin UI
  → BFF apiWrite() attaches mintkey_session cookie + Ed25519 x-mintkey-signed-request (ADR-0019)
  → POST /v1/tenants/{tnt}/agent-secrets  { agent_id, name, value, content_type? }
  → admin-api:
       resolve operator_id + tenant from validated session (identity = SESSION, not JWT body)
       validate: agent in tenant; value ≤ 65536 bytes; name ^[A-Za-z0-9._-]{1,128}$
       reject duplicate (tnt, agent, name) → 409 name_already_exists
  → vault PutAgentSecret(tnt, sec_id, value)        [AES-256-GCM envelope; vault.agent_secrets]
  → INSERT public.agent_secrets metadata (created_by = operator_id)
  → audit agent_secret.created (actor_type=operator; payload = ids/name/version/size — NO value)
  → 201 { secret_id, name, version, size_bytes, content_type, created_at }   (metadata only)
UI renders reveal-once modal from the value already in the form, then clears it.
```

### Read (agent — UNCHANGED)
```
Agent → secret_get?secret_id=sec_…  (Authorization: Bearer mk_agent_…)
  → MCP server validates key, checks ownership (agent is owner)
  → GetAgentSecret → plaintext returned to the owning agent (access: "owner")
```
No change to the agent surface, MCP tools, `tools.yaml`, or `vault.proto`.

### Update / rotate
`PUT /v1/tenants/{tnt}/agent-secrets/{secret_id}` `{ value, content_type? }` → vault `PutAgentSecret` overwrite, `version++`, metadata-only response, reveal-once client-side, audit `agent_secret.updated` (operator).

### Delete
Existing `DELETE` endpoint **+ new vault purge** (closes the phase-1 orphan-blob TODO now that admin-api has the vault client and `vault.secret.delete` scope) → audit `agent_secret.deleted` (operator).

### Sharing grants (UI over existing endpoints)
`POST`/`GET`/`DELETE` `/agent-secrets/{secret_id}/grants` already exist; this adds the UI (create grant → pick recipient agent; list; revoke).

## 5. Wire-contract changes (contract-first)

- `docs/architecture/contracts/rest/openapi.yaml` — **new** `POST /agent-secrets`, `PUT /agent-secrets/{secret_id}`; request `value` marked `x-mintkey-sensitive: true`; responses metadata-only. (`DELETE` + grants already present.)
- `docs/architecture/contracts/events/audit-event.schema.json` — allow `actor_type: operator` for `agent_secret.created` / `agent_secret.updated` (phase 1 modelled these as agent-actor).
- **No change** to `docs/architecture/contracts/mcp/tools.yaml` or `docs/architecture/contracts/vault-adapter/vault.proto`.
- `apps/admin-api/.../openapi_snapshot.json` regenerated (FastAPI ↔ YAML diff gate must pass).

## 6. Database (Liquibase only)

- **Changeset 028** — add `public.agent_secrets.created_by UUID NULL` (operator attribution; NULL when the agent self-created via `secret_put`). Same RLS policy/table (no policy change). Regenerate the SQLAlchemy mirror; CI diff must pass.

## 7. admin-api changes

- New vault client for agent secrets (mirror MCP server's `agent_secrets_client.py`); wire `PutAgentSecret` + `DeleteAgentSecret`. Identity `svcid_admin_api` granted `vault.secret.put` + `vault.secret.delete` scopes (bootstrap/identity config).
- New handlers: `POST` create (dup → 409; response metadata-only) and `PUT` update/rotate (`version++`).
- `DELETE` extended to purge the vault blob.
- Resolve `operator_id` from the validated session for audit `actor_id` + `agent_secrets.created_by`; fix the existing grant-handler nil-UUID `created_by` placeholder on the same path (D7).
- Audit: `agent_secret.created` / `agent_secret.updated` (actor_type=operator), identifier/metadata-only payloads.

## 8. admin-ui changes

- New `agent-secrets` RestResource: list = metadata only (`name`, `content_type`, `size_bytes`, `version`, `created_at`, `updated_at`, `created_by`); filter by `agent_id`.
- Custom **create form** component (freeform `name`/`value`/`content_type`) → `apiWrite` POST → **reveal-once modal** (pattern: `AgentCreatedNotice` / `ApiKeyCreate`).
- **Update/rotate** action (reveal-once, same pattern).
- **Delete** action via `ConfirmAction`.
- **Sharing-grant UI**: create grant (pick recipient agent), list grants, revoke via `ConfirmAction`.
- Entry point: "Manage secrets" action on the agent show page, deep-linking the resource pre-filtered by `agent_id`.
- All writes go through `apiWrite(..., operatorOpts)` (signed-request, ADR-0019); the BFF must not log request bodies.

## 9. Security guarantees (acceptance-level)

1. **No operator-facing response ever carries plaintext** — create/update return metadata only; reveal-once is client-side; GET/list are metadata-only.
2. **Writes require dual auth** — `mintkey_session` cookie **and** an Ed25519 `x-mintkey-signed-request` whose claims agree (`sub == operator_id`, `tnt == tenant_id`), per ADR-0019. Effective identity comes from the session.
3. **Encryption at rest** — AES-256-GCM envelope in `vault.agent_secrets`; KEK rotation covers it (same as ADR-0025 / ADR-0021).
4. **Zero plaintext in logs / audit / OTel spans** — `value` marked `x-mintkey-sensitive`; admin-api and BFF excluded from request-body logging; audit payloads are identifier/metadata-only; the phase-1 **red-team canary test** is extended to the operator create/update path (zero matches required).
5. **Tenant isolation** — RLS on all touched tables; tenant + operator come from the session, never the JWT body.
6. **Input limits** — `value ≤ 65536` bytes; `name` pattern enforced; duplicate name → 409 (no silent clobber).
7. **Anti-enumeration preserved** — the agent retrieval surface keeps the uniform `secret_not_found`.
8. **Full audit trail** — every operator state change emits an event with `actor_type=operator`.

## 10. Governance

- **ADR-0026 "Operator-provisioned agent secrets"** (canonical `docs/architecture/01-architecture/adr/` + `adrs/` symlink) extending ADR-0025: documents the operator-as-provisioner model, client-side reveal-once, admin-api gaining `vault.secret.put`/`.delete`, and that the S-SEC-1 posture is **unchanged for operators** (they never see stored plaintext) while the consuming agent reads its own provisioned secret. (ADR-0025 is still "Proposed"; a separate ADR keeps the record clean and survives 0025's independent acceptance.)
- **OpenSpec change** `openspec/changes/operator-provisioned-agent-secrets/` (proposal / design / specs delta / tasks) is the canonical implementation contract and carries the 9-field issue intake; validated with the openspec CLI.

## 11. Testing strategy (TDD per chunk)

- **admin-api unit**: create happy / dup-409 / oversize / bad-name; response carries no value; audit emitted with operator actor; vault `Put` called. Update `version++` + reveal semantics. Delete purges vault + audits. Tenant isolation + cross-tenant anti-enumeration.
- **Red-team canary**: value never appears in logs / span exports / audit payloads on the new operator path.
- **admin-ui**: handler tests (writes use `apiWrite` + signed-request) + render tests (modal shows value exactly once; list never shows value) + BFF route test (cookie/CSRF forwarded, body not logged).
- **Architecture gates**: openapi snapshot diff, audit-coverage test, RLS coverage test.
- **Live e2e** (isolated compose project): operator creates a secret → agent `secret_get` returns it → operator deletes → agent gets `secret_not_found`.

## 12. Process

- **Orchestrator pattern** (remediation-orchestrator): coordinator (Opus) owns state and dispatches; **Sonnet IMPLEMENTERs** work test-first and surgically; a **fresh Opus REVIEWER** independently verifies each chunk; PASS / FAIL / ESCALATE, 3-strike hard-stop.
- **Branch / worktree**: `feat/operator-provisioned-agent-secrets` in an isolated worktree off `main`. Pre-work backup before any docker/db step; live e2e from an isolated compose project; **never** `docker compose down -v` the `mintkey_*` volumes (`mintkey_ssh_proxy_hostkey` / `mintkey_ssh_proxy_recordings` are global names).

## 13. Out of scope

Operator re-reveal of stored values · typed credential schemes · external secret providers (phase-2 design-only) · changes to the agent MCP surface · per-secret version history.

## 14. Chunk plan (for orchestration)

1. **Contracts + ADR** — openapi.yaml (POST/PUT), audit-event.schema.json (operator actor), ADR-0026, OpenSpec change. Verify with openapi/redocly + jsonschema validators + openspec validate.
2. **DB** — Liquibase changeset 028 (`agent_secrets.created_by`); migrate against fresh PG; regenerate SQLAlchemy mirror; CI diff.
3. **admin-api** — vault client + scopes; POST/PUT handlers; DELETE vault purge; operator_id threading + grant `created_by` fix; audit; unit tests (test-first); openapi snapshot update.
4. **admin-ui** — `agent-secrets` resource; create/update/delete/grant components + BFF wiring; reveal-once; vitest (test-first).
5. **Security gates** — red-team canary on new path; RLS + audit-coverage; span/log scrubbing checks.
6. **E2E + finalize** — live cold-start verify (isolated compose project, backup first); update campaign memory; open PR.
