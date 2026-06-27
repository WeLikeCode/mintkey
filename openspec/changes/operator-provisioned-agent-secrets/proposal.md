# Operator-Provisioned Agent Secrets

## Why

Phase 1 (agent-stored-credentials, PR #213) lets an agent store and read back its **own** secrets via MCP. But the common provisioning direction is the reverse: an **operator** holds a credential the agent needs (a DB password, a service-account JSON, an SSH key) and wants to hand it to a specific agent. Today the only way is to have the agent call `secret_put` itself, which means the plaintext must first reach the agent's context out-of-band — defeating the point. Operators need to seed a credential **into an agent's namespace from the Admin UI**, after which the agent reads it back through the existing `secret_get` API. This is additive to phase 1; the agent MCP surface does not change.

## What Changes

- New operator REST write surface in admin-api: `POST /v1/tenants/{tenant_id}/agent-secrets` (create a secret in a target agent's namespace) and `PUT /v1/tenants/{tenant_id}/agent-secrets/{secret_id}` (update/rotate the value). Requests carry the plaintext `value` (marked `x-mintkey-sensitive`); **responses are metadata-only** — no admin-api endpoint ever returns a stored value.
- admin-api gains an `AgentSecretsVault` gRPC client and the `vault.secret.put` + `vault.secret.delete` scopes for `svcid_admin_api`. The existing operator `DELETE` is extended to **purge the ciphertext blob** (closing the phase-1 orphaned-blob TODO).
- New Admin UI surface (AdminJS BFF): a top-level `agent-secrets` resource (metadata-only list, filterable by agent) plus create / update-rotate / delete / sharing-grant actions, reached via a "Manage secrets" action on the agent show page. The create/update flow shows the just-entered value **exactly once, client-side** (reveal-once), then discards it — the value is never re-readable through the UI.
- `agent_secret.created` and `agent_secret.updated` audit events gain `actor_type: operator` (phase 1 modelled them as agent-actor). Operator identity is resolved from the validated session and recorded as the audit `actor_id` and in a new `agent_secrets.created_by` column; the same threading fixes the phase-1 grant-handler `created_by` nil-UUID placeholder.
- New ADR-0026 records the operator-as-provisioner model and confirms the S-SEC-1 posture is unchanged for operators (they never see a stored value) while the consuming agent reads its own provisioned secret via the phase-1 read-back deviation (ADR-0025).

## Capabilities

### New Capabilities
- `agent-secret-provisioning`: operator-initiated creation, update/rotation, ciphertext-purging deletion, and operator attribution of secrets in an agent's namespace, with metadata-only responses, client-side reveal-once, signed-request write auth, and audit of every operation.

### Modified Capabilities
<!-- none archived in openspec/specs yet; phase-1 capabilities live in their change folder. This change adds a sibling capability and references phase-1 behavior (agent read-back, sharing) without redefining it. -->

## Impact

- **Contracts (canonical, edit first)**: `docs/architecture/contracts/rest/openapi.yaml` (new `POST /agent-secrets`, `PUT /agent-secrets/{secret_id}`, `CreateAgentSecretRequest` / `UpdateAgentSecretRequest` schemas with `x-mintkey-sensitive: true` on `value`, metadata-only responses, `x-mintkey-error-codes` `name_already_exists`); `docs/architecture/contracts/events/audit-event.schema.json` (allow `actor_type: operator` for `agent_secret.created` / `agent_secret.updated`); new `docs/architecture/01-architecture/adr/0026-operator-provisioned-agent-secrets.md` (+ `adrs/` symlink + `adr/README.md` index row). **No change** to `mcp/tools.yaml` or `vault-adapter/vault.proto`.
- **DB**: Liquibase changelog `028-agent-secrets-created-by.yaml` — add `public.agent_secrets.created_by UUID NULL`; SQLAlchemy mirror update; no RLS change (same table/policy).
- **Services**: admin-api (`AgentSecretsVault` gRPC client + `svcid_admin_api` `vault.secret.put`/`.delete` scopes + compose env; `POST`/`PUT` handlers; `DELETE` blob purge; session→operator_id threading + grant `created_by` fix; audit; openapi snapshot regen). admin-ui (`agent-secrets` resource + create/update/delete/grant components + BFF write wiring + reveal-once).
- **Tests**: admin-api unit (create happy / 409 dup / oversize / bad-name / metadata-only response / operator-actor audit / vault Put called; update version++; delete purges blob; tenant isolation); red-team canary on the new operator path; admin-ui handler + render + BFF tests; architecture gates (openapi snapshot, audit coverage, RLS); live e2e create→read-as-agent→rotate→delete→not-found.
- **Out of scope**: operator re-reveal of stored values; typed credential schemes; external secret providers (phase-2 design-only); changes to the agent MCP surface; per-secret version history.

## Issue Intake (remediation gate)

1. **Problem statement**: Operators cannot provision a credential into an agent's namespace; the only creation path is agent-side `secret_put`, requiring the plaintext to reach the agent out-of-band first.
2. **User-visible symptom**: No Admin UI to view or create an agent's secrets; no operator REST endpoint to create/rotate an agent secret.
3. **Expected behavior**: Operator creates/rotates a secret for an agent in the UI (value entered once, shown once, never re-readable); agent retrieves it via the existing `secret_get`; operator can list metadata, delete (purging ciphertext), and manage sharing.
4. **Evidence**: admin-api `agent_secrets.py` exposes only list/get/delete + grants — no create/update; admin-ui has no agent-secrets surface (explored 2026-06-14); ADR-0025 §D2 + phase-1 sharing spec ("operators never see secret values").
5. **Scope**: openapi.yaml + audit schema + ADR-0026; Liquibase 028; admin-api create/update/delete-purge + vault client + scopes + operator_id threading; admin-ui resource + actions; tests + gates + e2e.
6. **Out of scope**: see "Out of scope" above.
7. **Risk level**: HIGH — credential handling + new write surface + new vault scope for admin-api. Requires orchestrator pattern + independent review per chunk.
8. **Verification target**: all repo validators green (openapi-spec-validator, redocly, jsonschema, openspec validate --strict, RLS + audit-coverage + sqlalchemy mirror + openapi snapshot, red-team canary) and a live e2e proving create→agent-read→rotate→delete→not-found with zero plaintext in logs/audit/spans.
9. **Owner decisions**: resolved in brainstorm 2026-06-14 — reveal-once (client-side); scope = create+update+delete+grants; dup name → 409; freeform value; opportunistic grant `created_by` fix approved.
