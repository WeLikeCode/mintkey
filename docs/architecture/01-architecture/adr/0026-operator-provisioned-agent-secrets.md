# ADR-0026: Operator-Provisioned Agent Secrets

## Status
Proposed — 2026-06-14

## Context

ADR-0025 introduced agent-stored secrets: an agent stores its own secrets via MCP (`secret_put`) and reads them back in plaintext. The S-SEC-1 deviation there is justified by "**the agent supplied the plaintext**" — the agent is reading back what it wrote.

The common provisioning direction is the reverse. An operator holds a credential a specific agent needs (a database password, a service-account JSON, an SSH key) and wants to hand it to that agent. Under phase 1 the only creation path is the agent calling `secret_put` itself, which requires the plaintext to reach the agent's context out-of-band first — defeating the purpose of a broker. ADR-0025 anticipated this and lists "Admin UI screens for operator secret management" as an open follow-up.

This ADR records the decisions for **operator-provisioned** agent secrets: an operator creates/rotates/deletes a secret in a target agent's namespace from the Admin UI, and the agent reads it back through the **existing** `secret_get`. The change is additive — the agent MCP surface and the vault proto are unchanged. The two questions this ADR must settle are (a) how the operator write path reaches the secret vault, and (b) how the S-SEC-1 posture is preserved when an **operator** supplies the plaintext.

### Existing machinery reused
- `AgentSecretsVault` gRPC (`PutAgentSecret` / `GetAgentSecret` / `DeleteAgentSecret`) and `vault.agent_secrets` envelope storage (ADR-0025 §D1).
- admin-api as the audit chokepoint (ADR-0014.7) and the admin-ui's only upstream (ADR-0019).
- Signed-request write auth: `mintkey_session` cookie + Ed25519 `x-mintkey-signed-request` (ADR-0019).
- `agents.created_by` attribution precedent and the metadata-only operator REST surface (ADR-0025 §D7, sharing spec).

## Decision

### D1 — The operator write path lives in admin-api, which gains a vault client and put/delete scopes

`POST /v1/tenants/{tenant_id}/agent-secrets` (create in a target agent's namespace) and `PUT /v1/tenants/{tenant_id}/agent-secrets/{secret_id}` (update/rotate) extend the existing admin-api `agent_secrets` router. admin-api gains an `AgentSecretsVault` gRPC client (mirroring the MCP server's) and the `vault.secret.put` + `vault.secret.delete` scopes for `svcid_admin_api`. admin-api is **not** granted `vault.secret.read` — operators still cannot read a stored value. The existing operator `DELETE` is extended to call `DeleteAgentSecret`, purging the ciphertext blob (closing the phase-1 orphaned-blob TODO).

Routing operator writes through the MCP server was rejected: that is the agent data plane (auth = `mk_agent_` key); operators have no agent key, so it is the wrong trust boundary.

### D2 — Reveal-once is client-side; admin-api responses are metadata-only

Because the operator types the value, the browser already holds it. The create/update **response carries no value** — it is metadata-only, identical in shape to the phase-1 list/get responses. The Admin UI displays the just-entered value **exactly once**, rendered client-side from the submitted form, and discards it on dismissal. There is **no server path by which an operator re-reads a stored value.** This preserves the phase-1 invariant "no operator-facing response carries plaintext" and is strictly safer than echoing the stored value back through the BFF.

### D3 — The S-SEC-1 posture is unchanged for operators; the agent read-back deviation is extended to operator-supplied plaintext

ADR-0025 §D2 deviates from S-SEC-1 for secrets the agent supplied. This ADR extends that deviation to cover plaintext an **operator** supplied for the consuming agent. The justification is the same, plus a trust argument:

- The provisioning operator is already trusted to manage credentials, services, and sharing grants for the tenant; handing a credential to an agent is within that authority.
- The agent that reads the secret is the **intended consumer**; read-back is the entire point of provisioning.
- All ADR-0025 §D2 safety conditions hold unchanged: encryption at rest, every agent read audited (`agent_secret.read`), anti-enumeration on the agent surface, zero plaintext in telemetry (`x-mintkey-sensitive` + span denylist + red-team canary), no proxy injection.
- For operators specifically, S-SEC-1 is **not** deviated from at all: operators never receive a stored plaintext in any response.

### D4 — Create rejects duplicate names; rotation is the explicit PUT

`POST` rejects a `name` already present for `(tenant_id, agent_id)` with `409 name_already_exists`, so an operator cannot silently clobber a secret the agent created itself. Rotation is the explicit, audited `PUT` path, which overwrites the ciphertext and increments `version`. (The agent's own `secret_put` overwrite-with-version semantics are unchanged — that is the agent acting on its own namespace.)

### D5 — `agent_secret.created`/`.updated` accept an operator actor; new `agent_secrets.created_by`

The `agent_secret.created` and `agent_secret.updated` audit event definitions are widened to accept `actor_type: operator` (phase 1 modelled them as agent-actor). `agent_secret.read` stays agent-only. A nullable `public.agent_secrets.created_by` (Liquibase changelog `028`) records the provisioning operator (NULL when the agent self-created via `secret_put`). Per ADR-0019, the effective identity (tenant GUC, audit `actor_id`, `created_by`) comes from the validated **session**, not the signed-request JWT body. Threading `operator_id` into these handlers also populates the grant `created_by`, fixing the phase-1 nil-UUID placeholder. Audit payloads remain identifier/metadata-only — no value, no fingerprint.

### D6 — No change to the agent MCP surface or the vault proto

`mcp/tools.yaml` and `vault-adapter/vault.proto` are untouched. The agent reads a provisioned secret through the existing `secret_get` (it is the `owner`; `agent_id` = the target agent), and `PutAgentSecret` / `DeleteAgentSecret` already exist. The only contract edits are `openapi.yaml` (two new operator paths + request schemas) and `audit-event.schema.json` (operator actor on two event types).

### D7 — Operator writes require signed-request authentication

Every state-changing call in this surface (create, update, delete, grant create/revoke) requires both the `mintkey_session` cookie and a valid Ed25519 `x-mintkey-signed-request` whose claims agree with the session (`sub == operator_id`, `tnt == tenant_id`), per ADR-0019. The admin-ui BFF and admin-api must not log request bodies for these routes, and `value` must never be placed on an OTel span.

## Consequences

| Good | Bad / Cost |
|---|---|
| Operators can provision credentials to agents without the plaintext touching the agent's context out-of-band | admin-api becomes a writer to the secret vault (new `vault.secret.put`/`.delete` scopes) — broader blast radius, mitigated by no read scope + metadata-only responses |
| Operator-facing plaintext exposure is zero (reveal-once is client-side; no read path) | The create/update request body carries plaintext on the browser→BFF→admin-api→vault path — mitigated by TLS, no body logging, `x-mintkey-sensitive`, span denylist |
| Closes the phase-1 orphaned-blob TODO (delete now purges ciphertext) | One more Liquibase changeset + SQLAlchemy mirror update |
| Delivers ADR-0025's "Admin UI screens for operator secret management" follow-up | Net-new admin-ui surface to maintain |
| Audit gains operator attribution + fixes the grant `created_by` placeholder | Widens two audit event definitions |

## Alternatives Considered

| Option | Why not |
|---|---|
| Route operator create through the MCP server (it already has the vault client + scopes) | Wrong trust boundary — MCP auth is the `mk_agent_` key; operators have no agent key |
| Echo the stored value back in the create/update response (server-side reveal-once) | Unnecessary plaintext round-trip through the BFF; the operator already typed the value — client-side reveal-once is strictly safer |
| Overwrite on duplicate name (match agent `secret_put`) | Lets an operator silently clobber a secret the agent created; explicit 409 + `PUT` rotation is safer |
| Give admin-api `vault.secret.read` for a re-reveal feature | Re-introduces operator-facing plaintext and an enumeration surface; rejected (out of scope) |

## Amends

- **ADR-0025** §D2: the agent read-back deviation now also covers operator-supplied plaintext consumed by the agent (same safety conditions). §D4: `agent_secret.created`/`.updated` accept `actor_type: operator`. Resolves the open follow-up "Admin UI screens for operator secret management."
- **ADR-0019**: confirms signed-request write auth applies to the new operator secret-provisioning endpoints; identity from session.
- **ADR-0021**: admin-api becomes a second writer (put/delete) to `vault.agent_secrets`, alongside the MCP server.

## Open Follow-ups
- Tighten provisioning/sharing authority to "creating operator only" once `agents.created_by` / `agent_secrets.created_by` are populated in production.
- Optional typed credential schemes (API key / SSH key / JSON) with light validation in the create form.
- Phase 2 external providers (ADR-0025) apply unchanged to operator-provisioned secrets.

## Related
- ADR-0025: Agent-stored secrets (read-back deviation, vault service, prefixes)
- ADR-0019: Admin UI BFF + write auth (signed request)
- ADR-0021: Vault storage backend (Postgres)
- ADR-0014.7: Audit hash chain + chokepoint
- ADR-0008: Multi-tenancy (RLS)
- ADR-0017.6: Span-attribute denylist
