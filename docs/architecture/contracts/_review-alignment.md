# Iteration 4 Contracts — ADR Alignment & Cross‑file Consistency Review

## Summary

Review covered all 16 ADRs (0001–0016), the container view, glossary, open‑questions register, all six iteration‑4 contracts, and seven iteration‑3 flow documents. The contracts post‑date ADR‑0014/0015 only partially: at least three ADR‑0014 amendments and three ADR‑0016 amendments did **not** propagate. The most damaging finding is that the change‑event schema's `x-mintkey-channels` and several OpenAPI/flow descriptions still publish on the **old per‑tenant `mintkey:<tenant_slug>:*` channels** while ADR‑0014.1 mandates global channels. The `mtls` auth scheme (ADR‑0016.5) is missing from every enum. `Permission.constraints` (ADR‑0016.4) is still open. There are no `/v1/admin/settings` endpoints, no `admin_request_jti` reference, and no `ServiceIdentity` boot‑secret API. ID prefix conventions and time format are uniformly correct. RFC 3339 use is consistent. JWT claim documentation is implicit only.

## Findings table

| ID | Sev | Cat | Locations | Reconciliation |
|----|:---:|:---:|---|---|
| A‑01 | 🔴 | A,G | `change-event.schema.json` lines 143–163; `openapi.yaml` lines 800, 1296; `F-OP-03` line 41 | Replace tenant‑scoped channel names with the four global channels per ADR‑0014.1. |
| A‑02 | 🔴 | A,B | `openapi.yaml` lines 1973–1989, 2174–2180; `tools.yaml` lines 85–93; `vault.proto` lines 79–87; `audit-event.schema.json` lines 83–93; `contracts/README.md` line 81 | Add `mtls` to every `auth_scheme` enum + add `MtlsCredentialValue` shape per ADR‑0016.5. |
| A‑03 | 🔴 | A,F | `openapi.yaml` Permission.constraints lines 2383–2389, 2411–2413; example line 1095 | Replace `additionalProperties: true` with the closed `Constraints` schema from ADR‑0016.4. |
| A‑04 | 🔴 | A,F | `openapi.yaml` (no occurrence) | Add `GET/PATCH /v1/admin/settings` + `AdminSettings` schema per ADR‑0016.6. |
| A‑05 | 🔴 | A,F | `audit-event.schema.json` (`tenant.deleted` payload lines 186–202); `tools.yaml` (no cascade docs) | Add `cascade_count` to `tenant.deleted` payload, document MCP error codes `agent_revoked`/`tenant_deleted` per ADR‑0016.7. |
| A‑06 | 🔴 | A,F | `audit-event.schema.json` (`audit.chain.verified` / `audit.chain.tampered` not present) | Add these two event types or document why omitted (ADR‑0014.7 mandates the verification job emits them). |
| A‑07 | 🔴 | A,F | `vault.proto` (no `ServiceIdentity` RPC); flows reference `/run/secrets/mintkey_service_token` without contract | Add a Vault Adapter `ValidateServiceIdentity` RPC or document the boot‑secret protocol per ADR‑0014.2. |
| A‑08 | 🟡 | B | `openapi.yaml` Service schema lines 1991–2048 vs `audit-event.schema.json` `ev_service_registered` lines 261–283 | `display_name` and `openapi_url` are required in OpenAPI but absent from the audit payload. Add them to the audit payload or relax `required` in OpenAPI. |
| A‑09 | 🟡 | B | `openapi.yaml` `tenant_id` is described as UUID (lines 20, 37) but pattern is ULID (lines 1619, 1848) | Decide one form. Either change the prose to "ULID" or change the schema to `format: uuid`. |
| A‑10 | 🟡 | B | `openapi.yaml` lines 2549, 2557 (`ChangeEvent.key_version` minimum 1) vs `change-event.schema.json` line 47 (also min 1) but `change-event.schema.json` example line 195 has actor `system_…` (system actor handling) | Check `actor_type` documentation: change event has no `actor_type` field; only the audit event does. Document this asymmetry. |
| A‑11 | 🟡 | A,B | OpenAPI (no JWT claim schema documented) | Add a JWT‑payload schema mirroring ADR‑0006 + ADR‑0008 (`iss, sub, aud, scope, jti, iat, exp, tnt, kid?`). The `request_token` MCP output should reference it. |
| A‑12 | 🟡 | E | `change-event.schema.json` line 156 (`mintkey:<tenant_slug>:agent`) lists `token.revoked` but channel is supposed to be `mintkey:agent` per ADR‑0014.1 | Bundled into A‑01. |
| A‑13 | 🟡 | A | `audit-event.schema.json` `ev_agent_permission_granted` lines 433–456 — `constraints` is `additionalProperties: true` | Tighten to the same closed `Constraints` schema as A‑03. |
| A‑14 | 🟡 | F | `audit-event.schema.json` (no `service.test_executed`); flows reference it (E2E‑01 line 30, F‑OP‑03 line 96) | Either add `service.test_executed` to the audit‑event schema or remove from flow expected‑post‑conditions. |
| A‑15 | 🟡 | F | `audit-event.schema.json` (no `tenant.bootstrap_completed`); flows reference it (E2E‑01 line 30, F‑OP‑01 lines 23, 53) | Same: add or strike. |
| A‑16 | 🟡 | F | `audit-event.schema.json` (no `settings.updated`); ADR‑0016.6 mandates one per `PATCH /v1/admin/settings` | Add. |
| A‑17 | 🟡 | A,H | OpenAPI Tenant `slug: "default"` (lines 258, 357) vs ADR‑0008 `t_default` (lines 12, 13, 123, 138) | Pick a single canonical default tenant slug. |
| A‑18 | 🟢 | A | `span-attributes.md` line 46 says `mintkey.tenant_id` is "UUID" | Match A‑09 resolution. |
| A‑19 | 🟢 | F | OpenAPI has no `POST /v1/tenants/{tid}/services/{sid}/test` endpoint that the iteration‑3 flows reference | Iteration 4 backlog item per `00-overview.md` — confirmed unresolved. |
| A‑20 | 🟢 | E | `mintkey:code` values listed in `x-mintkey-error-codes` (lines 2693–2707) drift from MCP `error_code` enum (lines 187–197) | Reconcile vocabularies: the `Cross‑file consistency` clause in `contracts/README.md` says they share vocabulary. Lots of overlap but `tenant_suspended`, `service_not_found` are in MCP only; `vault_unavailable`, `change_channel_unavailable` are in REST only. Ok if intentional, but document. |
| A‑21 | 🟢 | A,H | `OperatorRole` enum `[Admin, Auditor, AgentOwner]` (line 1912) — does not include the `PlatformAdmin` "meta‑role"; that's correctly held as a boolean on `Operator`. Glossary agrees. | No fix; documenting that the design is consistent. |
| A‑22 | 🟢 | E | OpenAPI Credential `status` enum is `[active, revoked]` (line 2130). `vault.proto` `CredentialStatus` is `UNSPECIFIED, ACTIVE, REVOKED`. | Aligns; `UNSPECIFIED` is proto3 idiomatic. |
| A‑23 | 🟢 | A | `vault.proto` line 19 mentions mTLS for the adapter's own listener but the proto doesn't define mTLS as a credential `auth_scheme`. | Bundled into A‑02. |
| A‑24 | 🟢 | C | `actor_id` examples include `system_01HX…` (change‑event line 195) — system actor convention is consistent with the spec but never explicitly documented as a prefix. Glossary has no `system_…` prefix. | Add `system_…` to the prefix table in `openapi.yaml` lines 23–33 + glossary. |
| A‑25 | 🟢 | B | Audit `ev_credential_revoked` (lines 371–390) requires `key_version` but change `ev_credential_revoked` (lines 93–102) also requires `key_version` ✓; OpenAPI `DELETE /credentials/{key_version}` aligns. | Aligned. |
| A‑26 | 🟢 | A | ADR‑0016.2 (JWKS force‑refresh on unknown `kid`) — flow F‑AG‑02 line 43 documents it, but no MCP/REST contract artifact captures this. | Documented in flow only; acceptable since this is plugin behavior. |
| A‑27 | 🟢 | A | ADR‑0016.3 PlatformAdmin RLS escape — no contract surface; pure DB/middleware concern. | No contract impact; acceptable. |
| A‑28 | 🟢 | E | OpenAPI Health `vault_backend` enum `[file, vault, sql_kms]` (line 2678) and `span-attributes.md` line 86 `mintkey.vault.backend` `file / vault / sql_kms` — agree. | Aligned. |

---

## Detailed sections

### A‑01 — Change channel names still tenant‑scoped 🔴

**Severity**: 🔴 critical (G — obsolete, A — ADR violation).

**ADR clause**: ADR‑0014.1: *"channels are global, not per‑tenant: `mintkey:service`, `mintkey:credential`, `mintkey:agent`, `mintkey:heartbeat`. Each event payload still carries `tenant_id`. Subscribers receive all events on a channel and filter at the application layer."*

**Contract location**:
- `docs/contracts/events/change-event.schema.json` lines 143–163: the `x-mintkey-channels` block lists `mintkey:<tenant_slug>:service`, `mintkey:<tenant_slug>:credential`, `mintkey:<tenant_slug>:agent` — the **pre‑correction** form.
- `docs/contracts/rest/openapi.yaml` line 800 (Credentials POST description): *"a `credential.rotated` change event is published on `mintkey:<tenant_slug>:credential`"*.
- `docs/contracts/rest/openapi.yaml` line 1296 (`/v1/tenants/{tenant_id}/changes` description): *"Subscribers of `mintkey:<slug>:*` channels call this on startup or after disconnection."*
- `docs/03-flows/F-OP-03-register-credential-and-test.md` line 41: `API->>DB: NOTIFY mintkey:credential` — already global ✓ (one out of many).

**What's wrong**: at least three contracts/flows still document per‑tenant channels. ADR‑0014.1 explicitly explains this scales O(N tenants) connection use. A subscriber that follows the contract literally will fail to LISTEN once any deployment grows to a handful of tenants. The contradicting forms in the same artifacts (E2E‑01 says `mintkey:service`; F‑OP‑02 says `mintkey:service`; the change‑event schema says `mintkey:<tenant_slug>:service`) make the source of truth ambiguous.

**Recommended fix**:
1. In `change-event.schema.json` rewrite `x-mintkey-channels`:
   ```yaml
   channels:
     - { name: "mintkey:service",    events: [service.registered, service.updated, service.removed] }
     - { name: "mintkey:credential", events: [credential.rotated, credential.revoked] }
     - { name: "mintkey:agent",      events: [agent.revoked, token.revoked] }
     - { name: "mintkey:heartbeat",  events: [], purpose: "30 s liveness ping" }
   ```
2. In `openapi.yaml` line 800 and 1296 replace `mintkey:<tenant_slug>:*` with the global channel names.
3. Add a sentence to `change-event.schema.json` description noting that `tenant_id` in the payload is the only filter authority.

### A‑02 — `mtls` auth scheme missing from every enum 🔴

**Severity**: 🔴 critical (A — ADR violation, B — drift).

**ADR clause**: ADR‑0016.5: *"add `mtls` to the `Credential.auth_scheme` enum in OpenAPI, MCP `describe_service` output, change events, audit events, and `vault.proto`'s enum. … Iteration‑4 contracts: enum addition + `MtlsCredentialValue` schema variant + audit event payloads include `auth_scheme: mtls` examples."*

**Contract location**:
- `openapi.yaml` lines 1973–1989 (`AuthScheme`): six values, no `mtls`.
- `openapi.yaml` lines 2174–2180 (`RegisterCredentialRequest.discriminator`): six mappings, no `mtls`.
- `tools.yaml` lines 85–93 (`auth_scheme`): six values.
- `vault.proto` lines 79–87 (`AuthScheme`): six values + UNSPECIFIED, no `AUTH_SCHEME_MTLS`.
- `audit-event.schema.json` lines 83–93 (`auth_scheme`): six values.
- `contracts/README.md` line 81–82 explicitly says **"Same six values; same names."** — actively codifying the bug.

**What's wrong**: every relevant enum is one short. Glossary explicitly lists "mTLS cert" as a credential type. The flow F‑OP‑03 line 13 ("an API key, OAuth client secret, basic‑auth pair, or PEM bundle for mTLS") and F‑AG‑02 line 97 ("Each `auth_scheme`: …, mtls. Each gets its own integration test") presume the enum value exists. Without it, Kiro will not generate the mTLS injection path.

**Recommended fix**:
1. Add `mtls` to all five enums.
2. In `openapi.yaml`, add `CredMtls` schema variant under `RegisterCredentialRequest` (PEM bundle: `value` is base64‑encoded combined cert+key; `auth_scheme: mtls`). Add to `discriminator.mapping`.
3. In `vault.proto`, add `AUTH_SCHEME_MTLS = 7;`.
4. In `audit-event.schema.json` `$defs/auth_scheme`, add `"mtls"`.
5. Update `contracts/README.md` line 81 to say **seven** values.
6. Add an example payload with `auth_scheme: mtls` per ADR‑0016.5.

### A‑03 — `Permission.constraints` is open ABAC 🔴

**Severity**: 🔴 critical (A).

**ADR clause**: ADR‑0016.4: *"iteration‑4 OpenAPI defines a closed `Constraints` schema. … `additionalProperties: false` on every level."*

**Contract location**:
- `openapi.yaml` lines 2383–2389 (`PermissionGrant.constraints`):
  ```yaml
  constraints:
    type: object
    additionalProperties: true
    description: |
      Free-form ABAC constraints (rate_limit, time_window, request_path_prefix, …).
      Schema is open in v1; iteration 2 will pin a closed set.
  ```
- `openapi.yaml` lines 2411–2413 (`GrantPermissionRequest.constraints`): same `additionalProperties: true`.
- Example at line 1094–1096 uses `rate_limit: { per_minute: 60 }` — but ADR‑0016.4's closed schema specifies `rate_limit.requests_per_second` and `rate_limit.burst`. So the example is inconsistent with the ADR even if the schema were tightened.

**What's wrong**: ADR‑0016.4 explicitly closed this in the iteration‑4 round. The description's "iteration 2 will pin a closed set" is now stale. The example uses a key (`per_minute`) that the closed schema doesn't accept.

**Recommended fix**:
1. Replace `PermissionGrant.constraints` and `GrantPermissionRequest.constraints` with `$ref: "#/components/schemas/Constraints"`.
2. Add the `Constraints` schema verbatim from ADR‑0016.4 (rate_limit / time_window / request_path_prefix / source_ip_allowlist), all with `additionalProperties: false`.
3. Replace the example body at line 1094 with `rate_limit: { requests_per_second: 1, burst: 60 }` (or pick a different example aligned with the closed schema).
4. Apply the same closure to `audit-event.schema.json` `ev_agent_permission_granted.payload.constraints` (currently `additionalProperties: true` at line 449).

### A‑04 — `/v1/admin/settings` endpoints missing 🔴

**Severity**: 🔴 critical (A, F).

**ADR clause**: ADR‑0016.6: *"iteration‑4 OpenAPI adds a small admin‑settings surface (PlatformAdmin only, every change emits `settings.updated`): `GET /v1/admin/settings`, `PATCH /v1/admin/settings`."*

**Contract location**: not in `openapi.yaml`. Search for `admin/settings` returns no match; only line 225 (description text mentioning `internal_auth.enabled`).

**What's wrong**: ADR‑0016.6 explicitly mandates two endpoints + a closed `AdminSettings` schema. They are absent. There is also no `settings.updated` audit event (see A‑16).

**Recommended fix**:
1. Add to `paths`: `/v1/admin/settings` with `GET` and `PATCH`. Both restricted to `PlatformAdmin`.
2. Add `AdminSettings` to `components.schemas` with the closed shape from ADR‑0016.6.
3. Add `Auth` tag note: PATCH must validate `can_be_disabled` server‑side.
4. Add `settings.updated` to `AuditEventType` enum and to `audit-event.schema.json`.

### A‑05 — Tenant deletion cascade not contractually documented 🔴

**Severity**: 🔴 critical (A, F).

**ADR clause**: ADR‑0016.7: *"Cascade on tenant deletion … `tenant.deleted` event with payload `cascade_count: { agents, services, credentials, permissions }`."* and: *"State‑changing tool calls (`request_token`): abort with `503 Service Unavailable` and `mintkey:code = tenant_deleted`."*

**Contract location**:
- `audit-event.schema.json` lines 186–202 (`ev_tenant_deleted`): payload only allows `{ "reason": "..." }`. No `cascade_count`.
- `tools.yaml` (the MCP tools file) does not document the `tenant_deleted` error code or the in‑flight call semantics. The closest is `tenant_suspended` in `error_code` (line 195).
- `openapi.yaml` `mintkey:code` enum (lines 2693–2707) does not include `tenant_deleted` (only `tenant_not_found`, `tenant_suspended`).

**What's wrong**: the deletion cascade is unobservable in the audit stream and unrepresentable as an MCP error.

**Recommended fix**:
1. Extend `ev_tenant_deleted.payload` (audit‑event.schema.json) with `cascade_count` (`{ agents, services, credentials, permissions }`, all integers, all required if cascade fired).
2. Add `tenant_deleted`, `agent_revoked` to MCP `error_code` enum (`tools.yaml` lines 187–197).
3. Add `tenant_deleted` to OpenAPI `x-mintkey-error-codes` list (line 2693).
4. Add a paragraph to MCP `tools.yaml` describing in‑flight session/tool behavior on tenant or agent deletion (per ADR‑0016.7).

### A‑06 — Audit chain verification events absent 🔴

**Severity**: 🔴 critical (A, F).

**ADR clause**: ADR‑0014.7: *"A scheduled job (default daily) walks each tenant's chain, recomputes hashes, and emits a `audit.chain.verified` event on success or `audit.chain.tampered` on discrepancy."*

**Contract location**: `audit-event.schema.json` `oneOf` (lines 752–778) and `discriminator.mapping` (lines 781–807). Neither `audit.chain.verified` nor `audit.chain.tampered` is present.

**What's wrong**: a verification job that emits no contractual event cannot be subscribed to by an alerting pipeline; nothing in the contract obliges the implementation to be observable.

**Recommended fix**:
1. Add `audit.chain.verified` (payload `{ chain_length, last_event_id, last_hash, verified_at }`) and `audit.chain.tampered` (payload `{ first_bad_event_id, expected_hash, actual_hash }`) to `audit-event.schema.json`.
2. Add both to `AuditEventType` (openapi.yaml line 2422). The associated `target_type` would be `tenant`.

### A‑07 — Service identity boot secret not in any contract 🔴

**Severity**: 🔴 critical (A, F).

**ADR clause**: ADR‑0014.2: *"Each service identity has a tenant‑aware access policy … The Vault Adapter validates each call's boot secret in constant time against a hash stored in its file backend (a special "service identity" credential type)."*

**Contract location**:
- `vault.proto`: declares only four RPCs (`GetCredential`, `PutCredential`, `RevokeCredential`, `ListVersions`). There is no service‑identity credential type, no validation RPC, and no concept of "caller" beyond the free‑text `caller_actor_id` field (lines 116–117, 188, 219, 252).
- Flow `F-OP-01` line 58: `API->>API: load Vault Adapter boot secret from /run/secrets` — referenced but not contracted.
- No mention of `svcid_admin_api`/`svcid_mcp`/`svcid_broker`/`svcid_proxy` anywhere in the contracts.

**What's wrong**: the bootstrap acyclicity guarantee in ADR‑0014.2 depends on an artifact (the validate‑boot‑secret RPC + the per‑service identity credential type) that no contract describes. Implementers will independently invent (and drift on) the protocol.

**Recommended fix**: pick one:
- (a) Add a `ValidateServiceIdentity(service_identity_id, presented_token) → (ok, scope)` RPC to `vault.proto`, plus an enum value `AUTH_SCHEME_SERVICE_IDENTITY` (or a new `Credential` type) and document the access‑policy field.
- (b) Document the protocol as an mTLS handshake (since `vault.proto` line 19 already mentions mTLS for the listener) and explicitly remove the "boot secret in the file backend" wording from ADR‑0014.2 — but this requires an ADR update, not a contract update.
- The OpenAPI surface for rotation (`POST /v1/admin/service-identities/{id}/rotate`?) is also missing if (a) is chosen.

### A‑08 — Service schema vs `service.registered` audit payload drift 🟡

**Severity**: 🟡 high (B).

**Contract location**: `openapi.yaml` `Service` (lines 1991–2048) requires `display_name` and accepts `openapi_url`, `current_key_version`, `description`. `audit-event.schema.json` `ev_service_registered.payload` (lines 261–283) has only `service_id`, `name`, `base_url`, `auth_scheme`, `actions`.

**What's wrong**: an auditor reading the audit log cannot reconstruct the registered service's `display_name` or `openapi_url`. ADR‑0014.7 (mandatory hash chain) couples audit records to the canonical record of intent — losing fields turns the audit into "something happened" rather than "X registered service Y at URL Z named W".

**Recommended fix**: add `display_name` (required) and `openapi_url` (optional) and `description` (optional) to the `service.registered` audit payload. Mirror to `service.updated` `fields_changed` enum which already has `display_name`, `description`, `openapi_url`. Same review for `agent.created` (audit has `name` but lacks `description`).

### A‑09 — `tenant_id` UUID vs ULID inconsistency 🟡

**Severity**: 🟡 high (B, H).

**Contract location**:
- `openapi.yaml` line 20: *"All identifiers are ULIDs … Tenants additionally carry a UUID `tenant_id` on every entity for RLS purposes (ADR‑0008)."*
- Same file line 37: *"Every domain object carries `tenant_id` (UUID)."*
- But `openapi.yaml` line 1619 (`TenantId` parameter): `pattern: "^tenant_[0-9A-HJKMNP-TV-Z]{26}$"` — a prefixed ULID, not a UUID.
- And every example uses prefixed ULID: `"tenant_01HX5J9F8V8H8V0CG3F2Y5J6M9"` (lines 311, 357, 546, …).
- ADR‑0008 line 18: `tenant_id UUID NOT NULL` (DB column type).
- `span-attributes.md` line 46: *"UUID of the active tenant"*.

**What's wrong**: the same field is documented as UUID in prose and as ULID by schema/pattern. ADR‑0008 specifies UUID at the DB level; the contracts have promoted it to a prefixed ULID at the wire level. These need to be consistent.

**Recommended fix**: pick the wire form (ULID is the convention for every other id) and update the prose:
- Either update the OpenAPI prose to say *"`tenant_id` is a prefixed ULID at the wire; stored as UUID at the DB"*, or update ADR‑0008 to use ULID at the DB. Same fix in `span-attributes.md` line 46.

### A‑10 — Change vs audit envelope asymmetry 🟡

**Severity**: 🟡 high (B).

**Contract location**: `audit-event.schema.json` envelope has `actor_type` (line 104). `change-event.schema.json` envelope has only `actor_id` (line 45) — no `actor_type`. Subscribers of the change channel cannot distinguish operator/agent/system/platform_admin without parsing the prefix from `actor_id`.

**What's wrong**: minor but real schema drift; means subscribers must replicate the prefix‑parsing logic.

**Recommended fix**: add `actor_type` to the change‑event envelope (with the same enum as audit). Cost: +1 byte in NOTIFY payload — negligible vs the 8 kB cap.

### A‑11 — JWT payload shape not in any contract 🟡

**Severity**: 🟡 high (A).

**ADR clause**: ADR‑0006 + ADR‑0008: claims set is `{iss, sub, aud, scope, jti, iat, exp, tnt, cnf?}`, algorithm is EdDSA, `iss` is `mintkey/broker`.

**Contract location**: the OpenAPI exposes the JWKS endpoint (`/.well-known/jwks.json`) and the `JWK`/`JWKS` schemas (lines 2613–2642), but the **payload** of the brokered JWT — the actual claims — is not a schema in any contract. The `request_token` MCP tool returns a `token: string` (`tools.yaml` lines 436–440) without a typed claim definition.

**What's wrong**: every consumer (proxy plugin, agent SDK, test tooling) must independently re‑derive the claim set from the ADRs. Any diversion goes undetected.

**Recommended fix**: add a `BrokeredTokenClaims` schema to `openapi.yaml` (in `components.schemas` under a `Discovery` or `Tokens` group) with required `iss, sub, aud, scope, tnt, jti, iat, exp` and optional `cnf`, `kid`. Reference it from MCP `request_token` `output_schema.token` description.

### A‑12 — `token.revoked` channel name 🟡

Bundled into A‑01.

### A‑13 — `agent.permission.granted` audit payload `constraints` is open 🟡

**Severity**: 🟡 high (A).

**ADR clause**: same as A‑03 (ADR‑0016.4).

**Contract location**: `audit-event.schema.json` lines 433–456 — `constraints` is `additionalProperties: true`.

**Recommended fix**: replace with the closed `Constraints` schema. (The audit payload is the canonical record of *what was granted*; an open constraint shape lets the audit itself become unstructured.)

### A‑14 — `service.test_executed` referenced by flows but not in audit schema 🟡

**Severity**: 🟡 high (F).

**Contract location**: `audit-event.schema.json` does not define `service.test_executed`. `00-overview.md` line 62 lists it as iteration‑4 backlog. `E2E-01` line 30 puts it on the post‑condition list. `F-OP-03` lines 67, 71, 96 require it.

**Recommended fix**: add `service.test_executed` to `AuditEventType` (`openapi.yaml` line 2422) and `audit-event.schema.json` with payload `{ method, request_path_template, status_code, latency_ms, ok, error? }`.

### A‑15 — `tenant.bootstrap_completed` referenced by flows but not in schema 🟡

**Severity**: 🟡 high (F). Same shape as A‑14.

**Recommended fix**: add `tenant.bootstrap_completed` to `AuditEventType` and audit schema, payload `{ tenant_slug, isolation_mode }`.

### A‑16 — `settings.updated` audit event missing 🟡

**Severity**: 🟡 high (A). Bundled with A‑04.

**ADR clause**: ADR‑0016.6 *"every change emits `settings.updated`"*.

**Recommended fix**: add `settings.updated` to `AuditEventType` and audit schema, payload `{ fields_changed: [enum] }`.

### A‑17 — Default tenant slug `default` vs `t_default` 🟡

**Severity**: 🟡 high (A, H).

**Contract location**: `openapi.yaml` examples at lines 258, 357 use `slug: "default"`. ADR‑0008 (line 12, 13, 123, 138) and the container/glossary docs use `t_default`. Flows are mixed: `F-OP-02` line 38 uses `t_default` in the URL.

**What's wrong**: a self‑hosted "single‑tenant by default" deployment writes audit and change events tagged with one of two slugs, depending on which doc the implementer reads.

**Recommended fix**: pick one (suggest `default` — operator‑readable, no `t_` prefix), update ADR‑0008 references in a follow‑up amendment, or align the OpenAPI examples to `t_default`. Either is fine; both must agree.

### A‑18 — `mintkey.tenant_id` span attribute described as UUID 🟢

Bundled with A‑09.

### A‑19 — `POST /v1/tenants/{tid}/services/{sid}/test` not in OpenAPI 🟢

**Severity**: 🟢 medium (F). Acknowledged as iteration‑4 backlog in `00-overview.md`. Not a regression; marking visible.

**Recommended fix**: add the endpoint per the iteration‑3 contract‑addition table.

### A‑20 — REST `mintkey:code` vs MCP `error_code` vocabulary drift 🟢

**Contract location**:
- REST `x-mintkey-error-codes` (lines 2693–2707) has 15 codes including `vault_unavailable`, `change_channel_unavailable`, `oidc_unavailable`, `permission_not_found`.
- MCP `error_code` (`tools.yaml` lines 187–197) has 7 codes; only some overlap.

**What's wrong**: `contracts/README.md` lines 89–92 says they **share vocabulary**. They partially do; an explicit mapping table is missing.

**Recommended fix**: produce a small table under `_review-alignment.md` (this file) or in `contracts/README.md` mapping each MCP `error_code` to its REST `mintkey:code` equivalent + which codes are MCP‑only.

### A‑21 — `OperatorRole` vs `PlatformAdmin` 🟢

`OperatorRole` enum is `[Admin, Auditor, AgentOwner]`. `PlatformAdmin` is correctly modeled as a boolean on `Operator` (`platform_admin: true`). Glossary, ADR‑0008, OpenAPI, audit, and AdminJS pin all agree. **No fix.**

### A‑22 — Credential status vs Vault proto status 🟢

OpenAPI `Credential.status: [active, revoked]`. Proto `CredentialStatus { UNSPECIFIED, ACTIVE, REVOKED }`. The proto idiomatically adds `UNSPECIFIED`. **Aligned.**

### A‑23 — `vault.proto` mTLS for listener vs mTLS as `auth_scheme` 🟢

Bundled into A‑02. The proto comment line 19 mentions mTLS for adapter authentication (a transport‑layer concern); A‑02 covers the missing `AUTH_SCHEME_MTLS` for credential storage.

### A‑24 — `system_…` actor prefix not in glossary 🟢

**Contract location**: `change-event.schema.json` example line 195 has `actor_id: "system_01HX..."`. Glossary and OpenAPI prefix table (lines 23–33) don't list `system_…`.

**Recommended fix**: add `system_…` to the prefix table in `openapi.yaml` and to the glossary.

### A‑25 — Credential events aligned 🟢

`ev_credential_revoked` (audit + change) both require `key_version`. **Aligned.**

### A‑26 — JWKS force‑refresh not contractually surfaced 🟢

ADR‑0016.2 is implemented as plugin behavior; contracts unaffected. **No fix.**

### A‑27 — PlatformAdmin RLS escape contractually invisible 🟢

ADR‑0016.3 is a DB‑middleware concern; contracts unaffected. **No fix.**

### A‑28 — Vault backend enum aligned 🟢

`openapi.yaml` `ReadyResponse.checks.vault_backend` and `span-attributes.md` `mintkey.vault.backend` both use `[file, vault, sql_kms]`. **Aligned.**

---

## Per‑category "no issues" entries

- **C — ID prefix consistency**: all examples in OpenAPI, MCP, audit‑event, change‑event, and flows use `tenant_…`, `operator_…`, `agent_…`, `svc_…`, `cred_…`, `perm_…`, `audit_…`, `change_…`, `session_…`. The `system_…` prefix is used only in change‑event examples and the span attribute spec; promote it to the prefix table (A‑24). **No structural inconsistency**, only a doc gap.
- **D — Enum value consistency**: `actor_type` (4 values: operator, agent, system, platform_admin) agrees across audit‑event.schema.json line 66, openapi.yaml line 2420, span‑attributes.md line 48. `target_type` (10 values) agrees across audit (lines 70–81) and openapi (lines 2453–2463). `event_type` enums for audit/change use the same dotted strings. The drift is *missing values* (`mtls`, `tenant.deleted` cascade, `audit.chain.*`, `service.test_executed`, `tenant.bootstrap_completed`, `settings.updated`) covered above — not value mis‑spellings.
- **E — Time format consistency**: every timestamp says RFC 3339 UTC. No "ISO 8601" usage. Examples consistently use `2026‑05‑10T14:23:45Z`. **No issues.**
- **G — Obsolete entities**: aside from per‑tenant channel names (A‑01) and the open `Permission.constraints` (A‑03), the only other latent obsolescence is the AdminJS direct‑DB‑write narrative — but ADR‑0014.5 corrected it inside ADR‑0013, and the contracts (which only describe the FastAPI surface) carry no AdminJS direct‑DB semantics. **No further obsolete clauses found in contracts.**
- **H — Glossary terms used inconsistently**: `Tenant`, `Operator`, `OperatorTenantMembership`, `PlatformAdmin`, `Tenancy model`, `Agent`, `Service`, `Action/Scope`, `Credential`, `JWT`, `Egress Proxy`, `MCP Server`, `Admin Console`, `Audit Event` are used as defined. The two slips are A‑17 (`default` vs `t_default`) and A‑24 (`system_…` actor not in glossary).
