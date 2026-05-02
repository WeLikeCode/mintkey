# Adversarial security review — Mintkey iteration‑4 contracts

**Scope**: `docs/contracts/rest/openapi.yaml`, `docs/contracts/mcp/tools.yaml`, `docs/contracts/events/audit-event.schema.json`, `docs/contracts/events/change-event.schema.json`, `docs/contracts/events/span-attributes.md`, `docs/contracts/vault-adapter/vault.proto`, plus iteration‑3 flow docs.

**Baseline**: ADRs 0001–0016 (most heavily 0003, 0004, 0006, 0007, 0008, 0014, 0016), threat model (`05-threat-model.md`), quality‑attribute scenarios (`03-quality-attributes.md`).

## Executive summary

The contracts get the headline crypto/architecture right (Ed25519 JWT with `tnt` claim, AES‑256‑GCM envelopes, Argon2id, plaintext returned exactly once, span allowlist, hash chain on AuditEvent, sensitive‑field markings on creation responses). However, **multiple ADR‑0014 and ADR‑0016 corrections are not yet reflected in the artifacts**: the test‑run endpoint (F‑OP‑03) and the `/v1/admin/settings` surface (ADR‑0016.6) are missing entirely; the `mtls` auth scheme (ADR‑0016.5) is absent across REST/MCP/audit/vault.proto enums; the `Permission.constraints` schema is still open (ADR‑0016.4 mandates closed); change‑channel naming throughout the docs still uses tenant‑scoped names contradicting ADR‑0014.1 global channels; the AdminJS↔FastAPI signed‑JWT envelope (ADR‑0014.6) is undocumented in the OpenAPI security schemes; PlatformAdmin cross‑tenant access has no dedicated audit event type; the `tenant.deleted` payload lacks the `cascade_count` required by ADR‑0016.7. There are also smaller leakage and DoS items. Implementing the fixes below closes every 🔴 and 🟡 finding.

## Prioritized findings table

| # | Sev | Location | Description | Fix |
|---|-----|----------|-------------|-----|
| F‑01 | 🔴 | `openapi.yaml` (no path) | `/v1/admin/settings` GET/PATCH endpoints **absent**; ADR‑0016.6 mandates them. `internal_auth.can_be_disabled` server guard not described. | Add the surface per ADR‑0016.6, plus `settings.updated` audit event. |
| F‑02 | 🔴 | `openapi.yaml`, `tools.yaml`, `audit-event.schema.json`, `vault.proto` | `mtls` auth scheme **missing** from all four enums; ADR‑0016.5 requires it. | Add `mtls` everywhere; pin `MtlsCredentialValue` schema; client cert + private key blob marked sensitive. |
| F‑03 | 🔴 | `openapi.yaml` `Permission.constraints`, `GrantPermissionRequest.constraints`; `audit-event.schema.json` `ev_agent_permission_granted.payload.constraints` | Schema is **open** (`additionalProperties: true`); ADR‑0016.4 mandates a **closed** `Constraints` schema. | Replace with closed schema (rate_limit, time_window, request_path_prefix, source_ip_allowlist) per ADR‑0016.4. |
| F‑04 | 🔴 | `openapi.yaml` (no path); `audit-event.schema.json` (no `service.test_executed`) | Test‑run endpoint (F‑OP‑03) absent: no host‑allowlist enforcement, rate‑limit, or audit event documented. SSRF surface. | Add `POST /v1/tenants/{tid}/services/{sid}/test`, declare 422/429, document RFC1918/link‑local/metadata IP rejection (ADR‑0007), and add `service.test_executed` event. |
| F‑05 | 🔴 | All contracts that mention channels (`change-event.schema.json` `x-mintkey-channels`, `openapi.yaml` lines ~800/1296, F‑OP‑02 line 45 inconsistent with itself) | Channel naming uses tenant‑scoped form `mintkey:<tenant_slug>:credential`, contradicting ADR‑0014.1 (global channels with application‑layer tenant filter). | Replace with `mintkey:service`, `mintkey:credential`, `mintkey:agent`, `mintkey:heartbeat`. Document app‑layer tenant filter requirement. |
| F‑06 | 🟡 | `openapi.yaml` `securitySchemes` | AdminJS↔FastAPI signed‑JWT envelope (ADR‑0014.6 + ADR‑0016.1 jti denylist) is **not declared** as a security scheme. Implementer has nothing to generate against. | Add `AdminUiSignedRequest` security scheme (Bearer JWT, kid `admin-ui-…`), declare on every state‑changing endpoint, document `jti` denylist policy. |
| F‑07 | 🟡 | `openapi.yaml` `/v1/changes`, `/v1/tenants/{tenant_id}/changes` | "PlatformAdmin only" lives in description text; no machine‑readable role guard. Also no service‑identity scheme is defined for subscribers (Kong‑syncer, proxy plugin) per ADR‑0014.2. | Declare a `ServiceIdentity` security scheme (boot‑secret), apply to `/v1/changes`. Add `x-mintkey-required-role: platform_admin` for the global form. |
| F‑08 | 🟡 | `audit-event.schema.json` (event‑type enum) | No dedicated event for **PlatformAdmin cross‑tenant read access**. ADR‑0008 + ADR‑0016.3 require every cross‑tenant access to emit an audit event. `actor_type=platform_admin` is necessary but not sufficient. | Add `platform_admin.access` (or similar) with payload `{ resource_type, resource_ids[], reason, source_tenant?, target_tenant }`. |
| F‑09 | 🟡 | `audit-event.schema.json` `ev_tenant_deleted` payload | Missing `cascade_count` required by ADR‑0016.7. | Extend payload to `{ reason?, cascade_count: { agents, services, credentials, permissions } }`. Also add `agent.revoked` cascade events spec note. |
| F‑10 | 🟡 | `tools.yaml` `request_token` errors | `service_not_found` returned for both "no permission in this tenant" and "service exists in a different tenant" — correct. But `describe_service` and `get_openapi` **don't have a `not_authorized` distinct from `service_not_found`** for revoked agents (ADR‑0016.7 says new tool calls bearing a revoked key get `not_authorized`). Description doesn't explain post‑revoke behavior either. | Document `auth.revoked` / `tenant_deleted` final‑frame semantics from ADR‑0016.7 inline; ensure all tools list `not_authorized` and `tenant_suspended`. |
| F‑11 | 🟡 | `openapi.yaml` — `OperatorBearer` and `AgentApiKey` security schemes | `AgentApiKey` is declared but **never applied** to any operation. `OperatorBearer.bearerFormat: opaque` lacks any guidance on issuance, rotation, or storage. | Either remove `AgentApiKey` (agent traffic flows through MCP) or apply it to a documented endpoint. Add `bearerFormat: mintkey-operator-pat` with rotation/revocation note. |
| F‑12 | 🟡 | `openapi.yaml` `/v1/auth/internal-login` | 401 reuses the generic `Unauthorized` example saying "Session cookie missing or invalid"; description does not mandate **identical** response for unknown user vs wrong password (timing + body). Audit `reason_code` distinguishes `unknown_user` vs `password_mismatch` — fine internally, but the contract must explicitly forbid leaking that distinction to the caller. | Add explicit "MUST return identical body and timing for `unknown_user` and `password_mismatch`". The 429 + Argon2id verify should run on a fixed input even when the user doesn't exist. |
| F‑13 | 🟡 | `tools.yaml` (auth section) | No constant‑time compare guidance for the Bearer Agent API Key; threat model (Spoofing row 1) requires it. | Add explicit "Agents are authenticated by constant‑time comparison of `Authorization: Bearer` against the Argon2id‑hashed `api_key_hash`. Format prefix (`mk_live_`) is checked first to bound rejection cost." |
| F‑14 | 🟡 | `vault.proto` `service VaultAdapter` | No mention of caller authentication. ADR‑0014.2 mandates per‑service boot secrets verified in **constant time**. The proto says only "mTLS in v1, with token‑based authentication as a future option" — but ADR‑0014.2 says boot tokens are required *now*. | Add caller‑authentication metadata to all RPCs (gRPC metadata `mintkey-service-token`), document the `caller_actor_id` field's relation to the boot‑secret identity, and forbid using `caller_actor_id` for authorization. |
| F‑15 | 🟡 | `openapi.yaml` `Tenant.settings` | `additionalProperties: true` on `settings` (and on `CreateTenantRequest.settings`). Operators can set arbitrary keys; future settings (e.g., `allow_plain_http`) silently appear. | Pin a closed `TenantSettings` schema (slug‑level switches: `allow_plain_http`, `isolation_mode`, `kek_scope`). Reject unknown keys. |
| F‑16 | 🟢 | `openapi.yaml` audit query, list endpoints | No 429 declared on `GET /v1/tenants/{tid}/audit`, `GET /v1/tenants` (PlatformAdmin), `GET /v1/tenants/{tid}/agents`, etc. ADR threat model and S‑MT‑3 require per‑tenant rate limits. | Declare 429 on every list/audit endpoint; document max page size, optional `from` lower‑bound enforcement to avoid full‑table scan. |
| F‑17 | 🟢 | `openapi.yaml` `RegisterCredentialRequest` examples | Inline literal API keys / passwords / Stripe‑shaped strings (`sk_live_4eC…`, `alice:s3cret`, `eyJhbGciOiJIUzI1NiI…`). The example bodies will live in JSON examples and Kiro‑generated test fixtures forever. | Replace with obviously fake placeholders: `«REPLACE_ME»`, `<api-key-redacted-in-example>`. |
| F‑18 | 🟢 | `openapi.yaml` `Agent.api_key_fingerprint` description, F‑OP‑04 line 41 | Format inconsistency: OpenAPI says `sha256:<full‑64‑hex>`; F‑OP‑04 says "last 4 chars + truncated SHA‑256 prefix". `audit-event.schema.json` matches OpenAPI (`^sha256:[0‑9a‑f]{64}$`). | Pick one and align all three. Recommend the full SHA‑256 (matches OpenAPI + audit). |
| F‑19 | 🟢 | `audit-event.schema.json` `ev_auth_login_failed` payload | Includes `username_attempted` as a string with no length limit and no PII redaction note. An attacker can fill the audit log with arbitrary blobs (DoS + log injection). | Cap to 200 chars; document salted‑hash storage for `prod` per `span-attributes.md` PII policy. |
| F‑20 | 🟢 | `openapi.yaml` `/v1/auth/login` `redirect_uri` | "Validated against an allow‑list. Ignored if not on the allow‑list." Silent ignore is OK; but we should also explicitly reject open‑redirect by validating scheme + host + matching path prefix. | Document the validation algorithm; respond `400 invalid_redirect` rather than silently ignoring (so misconfigs are visible). |
| F‑21 | 🟢 | `span-attributes.md` redaction policy | Forbids `mintkey.token` / `mintkey.api_key` / etc. but doesn't forbid OAuth2 `refresh_token` (held by Vault Adapter for OIDC sessions per ADR‑0005). | Add `mintkey.refresh_token`, `mintkey.id_token`, `mintkey.access_token` to the forbidden list. |
| F‑22 | 🟢 | `openapi.yaml` `/v1/changes` and `/v1/tenants/{tid}/changes` | `since` parameter is a free‑form string; tolerated unknown values "return from the start with a Warning header" — that is a denial‑of‑service vector (full re‑emit on demand) and a fingerprinting vector (probing event ids). | Validate `since` strictly (must match `^change_[0-9A-HJKMNP-TV-Z]{26}$`); on unknown id, return 410 with `since_unknown`, not silent reset. |
| F‑23 | 🟢 | `vault.proto` `GetCredentialResponse` | `bytes value` is correctly noted as sensitive in comments but no protobuf‑level option (e.g., `[(mintkey.sensitive) = true]`) — Kiro/codegen has nothing structured to generate redaction code from. | Add a `mintkey.sensitive` custom option; mark `value`, `header_name`, `query_param` (when carrying a credential) accordingly. |
| F‑24 | 🟢 | `change-event.schema.json` envelope | No `prev_hash` / `hash` chain. Threat model accepts it (changes are references and re‑published, not authoritative state). | Acceptable; document explicitly: "Change events are **not** the source of truth; tampering is detected on reconciliation against `audit_events`." |
| F‑25 | 🔵 | `openapi.yaml` `/v1/auth/internal-login` | Operation has no `OperatorSession` security but the success path returns a `Set-Cookie`. CSRF defense for the *next* requests using that session is not specified anywhere in the OpenAPI (mentioned only in ADR‑0013 follow‑up). | Add a `securitySchemes` entry `CsrfHeader: type: apiKey in: header name: X-CSRF-Token` and apply on every state‑changing endpoint — or document an explicit double‑submit cookie pattern. |
| F‑26 | 🔵 | `tools.yaml` `request_token` description | Says "ttl_seconds clamped to per‑service min/max" but no mechanism in the contract to **see** the per‑service min/max from the agent side; agents may guess and get `invalid_argument`. | Expose `default_ttl_seconds`, `min_ttl_seconds`, `max_ttl_seconds` in `service_full` returned from `describe_service`. |

## Detailed findings

### F‑01 — Admin settings surface absent

**Severity**: 🔴 critical

**Where**: `docs/contracts/rest/openapi.yaml` — no `/v1/admin/settings` path; no `settings.updated` audit event.

**Why this is a problem**: ADR‑0016.6 specifies a `GET/PATCH /v1/admin/settings` endpoint with a closed `AdminSettings` schema and the `internal_auth.can_be_disabled` server guard (so an admin cannot lock themselves out by toggling internal auth before validating OIDC). Without these, Kiro will either (a) generate nothing — leaving operators no way to switch off the bootstrap auth surface — or (b) generate something undisciplined that doesn't have the disable‑guard. Either way the bootstrap break‑glass becomes a permanent attack surface.

**Recommended fix**: copy the closed `AdminSettings` schema from ADR‑0016.6 into `components.schemas`; add `GET` and `PATCH /v1/admin/settings` paths gated on PlatformAdmin; declare `settings.updated` in `audit-event.schema.json` with payload `{ fields_changed: [...] }`.

**ADR alignment**: ADR‑0016.6.

---

### F‑02 — `mtls` auth scheme missing

**Severity**: 🔴 critical

**Where**:
- `openapi.yaml`: `AuthScheme` enum (line ~1973), `RegisterCredentialRequest.discriminator.mapping`, no `CredMtls` schema.
- `tools.yaml`: `$defs.auth_scheme` enum.
- `audit-event.schema.json`: `$defs.auth_scheme` enum (line ~83).
- `vault.proto`: `enum AuthScheme` (line ~79).

**Why this is a problem**: ADR‑0016.5 mandates `mtls` as a first‑class auth scheme; the test plan in F‑OP‑02 (line 104) and F‑AG‑02 (line 97) already references `mtls`. Without it, an operator who registers an mTLS‑authenticated backend has nowhere to put the cert+key bundle, and the proxy plugin has no contract to know it must perform per‑request mTLS to the backend.

**Recommended fix**: add `mtls` to all four enums (in lockstep, per the comment on `vault.proto:78`). Add `CredMtls` to `openapi.yaml` (`auth_scheme: mtls`, `value: base64‑encoded PEM bundle`, `x-mintkey-sensitive: true`). Mention in vault.proto comments that the bundle contains both client cert and private key.

**ADR alignment**: ADR‑0016.5.

---

### F‑03 — `Permission.constraints` is open

**Severity**: 🔴 critical

**Where**:
- `openapi.yaml` `PermissionGrant.constraints` and `GrantPermissionRequest.constraints` (lines ~2383, ~2411).
- `audit-event.schema.json` `ev_agent_permission_granted.payload.constraints` (line ~448).

**Why this is a problem**: ADR‑0016.4 explicitly closes the schema (rate_limit, time_window, request_path_prefix, source_ip_allowlist). With `additionalProperties: true`, an operator can write any key (e.g., `bypass_audit: true`) and the validator silently accepts it. Constraint evaluators in MCP/proxy then ignore unknown keys; operator believes the constraint is enforced; it isn't. This is a "false sense of security" findings class and exactly the case ADR‑0016.4 was written to prevent.

**Recommended fix**: replace both `constraints` definitions with the closed schema in ADR‑0016.4. Validate identically in `audit-event.schema.json`. Bumping the OpenAPI version is acceptable since the document is `experimental`.

**ADR alignment**: ADR‑0016.4.

---

### F‑04 — Test‑run endpoint absent (SSRF surface)

**Severity**: 🔴 critical

**Where**: `openapi.yaml` (no path); `audit-event.schema.json` (no `service.test_executed`).

**Why this is a problem**: F‑OP‑03 documents a "click Test" UX that POSTs to `/v1/tenants/{tid}/services/{sid}/test` with `{ method, path, timeout_ms }`. F‑OP‑03 calls it out under "Contract additions (iteration 4 backlog)". Without an OpenAPI definition: (a) Kiro has no spec to gate on; (b) host allowlist (RFC1918, link‑local, metadata IP per ADR‑0007) can't be CI‑enforced against the contract; (c) per‑service rate limit (S‑MT‑3) isn't documented; (d) there's no audit event schema, so the audit chokepoint is genuinely bypassed. This is the canonical SSRF surface — operator‑controlled outbound HTTP from inside the trust boundary.

**Recommended fix**: add `POST /v1/tenants/{tid}/services/{sid}/test`. Request body: `{ method: enum, path: string (max 1024, no `..`, no schemes), headers?: map, timeout_ms?: int default 5000 max 30000 }`. Response: `{ ok, status_code, latency_ms, response_body_truncated_4kb? , error? }`. Declare 422 (`forbidden_destination`), 429, 502 (`backend_unreachable`). Add `service.test_executed` audit event with payload `{ method, path_template, status_code?, latency_ms, ok, error? }` — never the response body in the audit. Document RFC1918/link‑local/metadata‑IP rejection.

**ADR alignment**: ADR‑0007 (egress allowlist, RFC1918 rejection) + threat model elevation‑of‑privilege ("SSRF via register a service").

---

### F‑05 — Channel naming contradicts ADR‑0014.1

**Severity**: 🔴 critical

**Where**:
- `change-event.schema.json` `x-mintkey-channels` (line ~143): `mintkey:<tenant_slug>:service`, `mintkey:<tenant_slug>:credential`, `mintkey:<tenant_slug>:agent`.
- `openapi.yaml` line ~800: `mintkey:<tenant_slug>:credential`.
- `openapi.yaml` line ~1296: `mintkey:<slug>:*`.
- F‑OP‑02 line 45 (correct, `mintkey:service`) vs. F‑OP‑03 line 41 (`mintkey:credential` — also correct) vs. the schema (incorrect).

**Why this is a problem**: ADR‑0014.1 explicitly *replaces* tenant‑scoped channel names with **global** channels (`mintkey:service`, `mintkey:credential`, `mintkey:agent`, `mintkey:heartbeat`) plus mandatory **application‑layer tenant filters** in subscribers, because tenant‑scoped channel names cause a `LISTEN` connection per‑(channel × tenant) and exhaust Postgres `max_connections` budgets. The contracts describe the deprecated approach.

**Recommended fix**: in `change-event.schema.json`, replace `x-mintkey-channels` with the four ADR‑0014.1 channels and document the application‑layer filter. In `openapi.yaml` descriptions for credential rotation and the changes endpoint, fix channel names to the global form. Add a one‑line note: "subscribers MUST configure an explicit tenant scope; the wrapper packages refuse to start without one."

**ADR alignment**: ADR‑0014.1.

---

### F‑06 — AdminJS↔FastAPI signed envelope undocumented in OpenAPI

**Severity**: 🟡 high

**Where**: `openapi.yaml` `components.securitySchemes` (lines ~1584+).

**Why this is a problem**: ADR‑0014.6 mandates that every AdminJS write to FastAPI carry a 60‑second Ed25519 JWT (`iss=mintkey/admin-ui`, `sub=<operator_id>`, `tnt`, `aud=mintkey/admin-api`, `iat`, `exp`, `jti`) plus FastAPI must keep a `jti` denylist (ADR‑0016.1, in Postgres). The OpenAPI describes only `OperatorSession` (cookie) and `OperatorBearer` (PAT). Generated server stubs from the OpenAPI alone will not enforce the signed envelope; operators may run AdminJS without it and not know.

**Recommended fix**: add an `AdminUiSignedRequest` security scheme:
```yaml
AdminUiSignedRequest:
  type: http
  scheme: bearer
  bearerFormat: mintkey-admin-ui-jwt
  description: |
    Per ADR-0014.6 + ADR-0016.1. 60-s Ed25519 JWT signed by AdminJS …
    jti is denylisted in Postgres (table admin_request_jti); replays
    rejected with 401 mintkey:code = jti_replay.
```
Apply on every state‑changing operation as an alternative to `OperatorSession` for inbound AdminJS calls. Document in the response `Unauthorized` problem code list `jti_replay` and `signature_invalid`.

**ADR alignment**: ADR‑0014.6, ADR‑0016.1.

---

### F‑07 — `/v1/changes` lacks machine‑readable role guard and a service identity scheme

**Severity**: 🟡 high

**Where**: `openapi.yaml` `/v1/changes` (lines ~1247+) and `/v1/tenants/{tenant_id}/changes` (~1288+).

**Why this is a problem**: subscribers (Kong‑syncer, proxy plugin, MCP server) call `/v1/changes` for reconciliation. ADR‑0014.2 requires those subscribers to authenticate via per‑service boot secrets. Today the OpenAPI says only "PlatformAdmin only" in the description. Stub generators will (a) generate unprotected endpoints or (b) fail back to `OperatorSession`, neither of which suits an automated subscriber.

**Recommended fix**: define a `ServiceIdentity` security scheme (`type: http`, `scheme: bearer`, `bearerFormat: mintkey-service-token`). Apply to `/v1/changes` and `/v1/tenants/{tid}/changes`. Add a `x-mintkey-required-role: platform_admin` extension on the global form (the tenant‑scoped form is OK for any subscriber tied to that tenant). Document in the description that the boot secret is constant‑time compared (per ADR‑0014.2).

**ADR alignment**: ADR‑0014.2.

---

### F‑08 — No audit event for PlatformAdmin cross‑tenant reads

**Severity**: 🟡 high

**Where**: `audit-event.schema.json` (no event); `openapi.yaml` `AuditEventType` enum (lines ~2422+) likewise.

**Why this is a problem**: ADR‑0008 + ADR‑0016.3 say "every cross‑tenant access by PlatformAdmin emits an audit event with `actor_type=platform_admin` and the resource(s) touched". Today, `actor_type` is set on existing events for *state changes* a PlatformAdmin makes. There is no event for the **read** path: a PlatformAdmin running `GET /v1/tenants/{otherTid}/audit` or `GET /v1/changes` (global) leaves no audit row. The whole point of a hash‑chained audit is undermined if cross‑tenant reads don't appear in it.

**Recommended fix**: add a new audit event type, `platform_admin.access`:
```json
{
  "event_type": "platform_admin.access",
  "target_type": "tenant",
  "payload": {
    "operator_id": "operator_…",
    "viewed_tenant_ids": ["tenant_…"],
    "endpoint": "/v1/tenants/{tid}/audit",
    "reason": "string (operator-supplied or 'unspecified')",
    "result_count": 42
  }
}
```
Emit on every API hit where `app.platform_admin_view='on'` is set per ADR‑0016.3.

**ADR alignment**: ADR‑0008, ADR‑0016.3.

---

### F‑09 — `tenant.deleted` payload missing `cascade_count`

**Severity**: 🟡 high

**Where**: `audit-event.schema.json` `ev_tenant_deleted.payload` (lines ~186–202).

**Why this is a problem**: ADR‑0016.7 specifies "final `tenant.deleted` event with payload `cascade_count: { agents, services, credentials, permissions }`". The payload today only contains `reason`. Without `cascade_count`, an auditor cannot at a glance verify the cascade actually fired. Combined with F‑08 above, this is the audit gap.

**Recommended fix**: extend payload to include `cascade_count: { agents: int, services: int, credentials: int, permissions: int }`, all required. Optionally add `cascade_id_samples` (first 10 ids of each type) for forensic correlation. Update the discriminator example.

**ADR alignment**: ADR‑0016.7.

---

### F‑10 — MCP tool docs miss revoked/deleted runtime semantics

**Severity**: 🟡 high

**Where**: `tools.yaml` per‑tool `errors` lists; `tools.yaml` general description.

**Why this is a problem**: ADR‑0016.7 specifies precise semantics for in‑flight MCP sessions when an agent is revoked or its tenant is deleted (final error frame, EOF on stdio, distinct `mintkey:code = agent_revoked` / `tenant_deleted`). The contract today only lists `not_authorized` and `tenant_suspended` in the per‑tool error tables — not `agent_revoked` or `tenant_deleted` codes, nor the in‑flight closure protocol.

**Recommended fix**: add `agent_revoked` and `tenant_deleted` to the `error_code` enum and to `common_errors`. Add a top‑of‑file section "Behavior on revocation / tenant deletion" copying the ADR‑0016.7 table verbatim (HTTP/SSE final error frame; stdio EOF; new tool calls 401; in‑flight read‑only completes; in‑flight `request_token` aborts 503).

**ADR alignment**: ADR‑0016.7.

---

### F‑11 — Unused / under‑specified security schemes

**Severity**: 🟡 high

**Where**: `openapi.yaml` `securitySchemes.AgentApiKey` (lines ~1600+) and `OperatorBearer` (~1592+).

**Why this is a problem**: `AgentApiKey` is declared but is not the `security` requirement on **any** operation. Either an agent‑facing endpoint is missing from the contract (a real omission) or the security scheme is dead code that leaks a "this exists" hint to consumers. `OperatorBearer.bearerFormat: opaque` says nothing about issuance, scope, rotation, or scope per role — making it a magic token.

**Recommended fix**:
- Either remove `AgentApiKey` (since "most agent traffic flows through MCP instead" is the docstring), or apply it explicitly to whichever agent‑facing REST endpoint exists (probably none — confirm and remove).
- Update `OperatorBearer` description: format prefix, length, rotation cadence (per ADR‑0013), and link to the not‑yet‑existing issuance endpoint. Note that PATs MUST be hashed at rest with Argon2id, like agent keys.

---

### F‑12 — Internal login leaks user existence

**Severity**: 🟡 high

**Where**: `openapi.yaml` `/v1/auth/internal-login` (lines ~216–267); `audit-event.schema.json` `ev_auth_login_failed.payload.reason_code` (lines ~715–724).

**Why this is a problem**: the threat model's information‑disclosure list calls out "login error responses constant‑time; 401 vs 403 distinctions don't leak which user/agent exists". Today: (a) the contract does not require identical bodies for `unknown_user` vs `password_mismatch`; (b) the audit event reason‑code distinguishes them, which is appropriate for the audit log but means the implementation has the distinction available to leak; (c) there is no requirement to run a *dummy* Argon2id verify for the unknown‑user path so timing equalizes.

**Recommended fix**: in the OpenAPI description for `internal-login`, add:
> 401 responses MUST be byte‑identical (same `Problem.detail` text and same headers) regardless of whether the username exists. Implementations MUST run an Argon2id verify against a fixed dummy hash when the username does not exist, to equalize timing within ±10 ms p99. The per‑username 429 rate limit (5 attempts / 60 s) MUST apply identically to known and unknown usernames.

Optionally: drop `unknown_user` from the audit reason‑code enum (collapse into `auth_failed`) — although keeping it for forensics is also defensible if the audit log itself is restricted.

**ADR alignment**: threat‑model § information‑disclosure; ADR‑0014.7 (audit log access constraints).

---

### F‑13 — MCP missing constant‑time compare guidance for Bearer key

**Severity**: 🟡 high

**Where**: `tools.yaml` lines ~14–24 (Auth section).

**Why this is a problem**: an agent that submits a slightly‑wrong key probes the response timing to recover bytes one at a time. Threat model § Spoofing row 1 explicitly lists "Keys are 32‑byte random, hashed at rest, validated by **constant‑time compare**. Format‑prefixed for early rejection." The contract has only the "hashed at rest" half.

**Recommended fix**: extend the Auth section:
> The MCP Server validates the Bearer token by:
> 1. Format check (prefix `mk_live_`, length, base32 alphabet); reject malformed early.
> 2. Lookup operator/agent record by the prefix‑indexed key id (does not depend on the secret part).
> 3. **Constant‑time** comparison of `Argon2id(presented_secret) == stored_hash`. The implementation MUST use `subtle.ConstantTimeCompare` / `hmac.compare_digest` — never `==` on byte strings.

**ADR alignment**: threat model spoofing; ADR‑0009 auth row.

---

### F‑14 — `vault.proto` missing caller‑authentication contract

**Severity**: 🟡 high

**Where**: `docs/contracts/vault-adapter/vault.proto` lines 16–20 ("INTERNAL SERVICE" comment) and every RPC.

**Why this is a problem**: ADR‑0014.2 defines per‑service boot secrets with a constant‑time hash compare in the Vault Adapter as the **production** caller authentication. The proto comment says "mTLS in v1, with token‑based authentication as a future option" — that contradicts ADR‑0014.2, which made the boot secret the v1 mechanism. The `caller_actor_id` field is only documented as "for audit emission"; there is no protocol‑level requirement that the adapter must verify the actor matches the bound boot secret. A misimplementation could trust `caller_actor_id` as authoritative and let one service identity claim another's identity.

**Recommended fix**:
- Add a contract section: "Every RPC carries a per‑service boot secret in gRPC metadata key `mintkey-service-token`. The adapter validates it constant‑time against a hash stored in its `service identity` credential type (ADR‑0014.2). `caller_actor_id` is **informational only** for audit; the adapter MUST NOT use it for authorization."
- Document the access policy per service identity (per ADR‑0014.2: `svcid_proxy` can only `GetCredential`; `svcid_admin_api` has read+write; etc.). A `caller_actor_id` whose declared identity does not match the verified boot secret triggers `PERMISSION_DENIED` and a `service_identity_mismatch` audit.

**ADR alignment**: ADR‑0014.2.

---

### F‑15 — `Tenant.settings` is an open object

**Severity**: 🟡 high

**Where**: `openapi.yaml` `Tenant.settings` and `CreateTenantRequest.settings` (lines ~1857, 1879, 2376–2389 for `constraints`).

**Why this is a problem**: `additionalProperties: true` lets an operator (or PlatformAdmin via the `tenants` POST) inject any key. Future feature flags (`allow_plain_http` per ADR‑0007 dev mode, `kek_scope` per ADR‑0008 phase 2) will then ride on this open bucket without a typed schema, and Kiro will not generate validation for them.

**Recommended fix**: define a closed `TenantSettings` schema:
```yaml
TenantSettings:
  type: object
  additionalProperties: false
  properties:
    isolation_mode: { enum: [row, database] }
    allow_plain_http: { type: boolean, default: false }
    contact: { type: string, format: email }
    kek_scope: { enum: [shared, per_tenant], default: shared }
```
New keys require an ADR + version bump (same convention as ADR‑0016.4).

---

### F‑16 — Rate limits not declared on expensive list endpoints

**Severity**: 🟢 medium

**Where**: `openapi.yaml` audit query (~1175), tenants list (~328), agents list (~908), credentials list (~735), services list (~517), changes (~1247, 1288).

**Why this is a problem**: only `internal-login` declares 429. The threat model and S‑MT‑3 require per‑tenant rate limits at the application layer; the contract should expose them so generated clients implement backoff. The audit query without `from`/`to` is the worst — a `PlatformAdmin` could pull the entire chain in one cursor walk.

**Recommended fix**: declare 429 on every list/audit endpoint. Document in `description`: "subject to per‑tenant rate limit (default 60 r/m)" and "audit query MUST include either `from` or `after`; a request with neither MUST be rejected with 400 `audit_query_too_broad`".

---

### F‑17 — Realistic credential strings in OpenAPI examples

**Severity**: 🟢 medium

**Where**: `openapi.yaml` `RegisterCredentialRequest.examples` (lines ~807–828); `Credential` example `value: "eyJhbGciOiJIUzI1NiI…"` (~843); InternalLoginRequest example `password: "SX7-correct-horse-battery-staple"` (~234).

**Why this is a problem**: Kiro and any code generator will lift these examples into test fixtures. Stripe live‑key‑shaped strings (`<redacted-example-api-key>`) and JWT‑shaped strings get flagged by external secret scanners (gitleaks, trufflehog) and will produce repo‑level alarms. They also normalize "credentials live in YAML examples", contrary to S‑SEC‑1.

**Recommended fix**: replace every example credential with an obvious placeholder: `«replace‑with‑plaintext»` for the secret fields; for `bearer_token`, `eyJREDACTED.REDACTED.REDACTED`; for `basic_auth`, `<username>:<password>`. Add a CI lint that rejects example values matching known credential‑shape regexes.

---

### F‑18 — Inconsistent `api_key_fingerprint` format

**Severity**: 🟢 medium

**Where**: `openapi.yaml` Agent example (line ~937) `sha256:7f83b…` (full 64‑hex); `audit-event.schema.json` `ev_agent_created.api_key_fingerprint.pattern` `^sha256:[0-9a-f]{64}$`; `F-OP-04.md` line 41 says "fingerprint = sha256(plaintext)[:8]" (8 hex / 4 bytes).

**Why this is a problem**: 4‑byte fingerprint has 2³² collision space — operationally fine for ID display but irrelevant for cryptographic verification. The OpenAPI/audit schema dictates 64‑hex (full SHA‑256) — fine. The flow doc disagrees. Implementations will pick one or the other and break compatibility between the audit/REST/AdminJS surfaces.

**Recommended fix**: standardize on **full SHA‑256** (matches the schema). Update F‑OP‑04 line 41 and the surrounding sequence diagram. If a short display form is desired in the UI, derive it client‑side (`fingerprint[:12]`).

---

### F‑19 — `username_attempted` in failed‑login audit unbounded

**Severity**: 🟢 medium

**Where**: `audit-event.schema.json` `ev_auth_login_failed.payload.username_attempted` (line ~709).

**Why this is a problem**: an attacker hitting `/v1/auth/internal-login` with multi‑KB usernames can inflate the audit table; PII (typo'd email addresses; tokens accidentally pasted as usernames) lands in audit unredacted; `span-attributes.md` requires PII be salted‑hashed in `prod`, but the audit schema has no equivalent constraint.

**Recommended fix**: cap to `maxLength: 200`. Add a description note: "In `prod`, `username_attempted` is salted‑SHA‑256 (16‑byte salt per‑instance)." Add a redaction list extension `x-mintkey-redact-in-prod: salted_sha256` so Kiro can generate the right marshalling.

---

### F‑20 — `redirect_uri` silent ignore obscures misconfig

**Severity**: 🟢 medium

**Where**: `openapi.yaml` `/v1/auth/login` `redirect_uri` (lines ~152–162).

**Why this is a problem**: silent ignore on disallowed redirect means a misconfigured AdminJS deployment will land users in a wrong place with no visible failure. Open‑redirect classes occur in the gap between "validated" and "dropped silently"; any later refactor that allows multi‑value `redirect_uri` without proper allow‑listing inherits that weak pattern.

**Recommended fix**: change the description to require `400 invalid_redirect` with `mintkey:code = redirect_uri_not_allowed` instead of silent ignore. Document the validation algorithm: scheme `https` (or `http` in dev mode), host exact match against allow‑list, path prefix match.

---

### F‑21 — Span allowlist missing OIDC token names

**Severity**: 🟢 medium

**Where**: `span-attributes.md` § Redaction policy (lines ~127–161).

**Why this is a problem**: ADR‑0005 says OIDC refresh tokens are stored encrypted via the Vault Adapter. The allowlist forbids `mintkey.token` and `mintkey.api_key` but not `mintkey.refresh_token`, `mintkey.access_token`, `mintkey.id_token`. An OTel auto‑instrumented HTTP client could capture a `urllib3.Request.body` attribute (via attribute mapping) carrying the token POST.

**Recommended fix**: extend the forbidden list to `mintkey.refresh_token`, `mintkey.access_token`, `mintkey.id_token`, plus the suffix patterns `*.refresh_token`, `*.access_token`, `*.id_token`. Same for any HTTP body attribute that an OTel instrumentation might add.

---

### F‑22 — `since` parameter allows DoS / fingerprinting

**Severity**: 🟢 medium

**Where**: `openapi.yaml` `/v1/changes` and `/v1/tenants/{tid}/changes` (lines ~1255–1265).

**Why this is a problem**: "tolerant of unknown `since` values (returns from the start with a Warning header)" gives an attacker a high‑cost, repeatable trigger to dump the entire reconciliation feed. It also enables existence probing of `event_id` values via response timing.

**Recommended fix**: validate `since` must match `^change_[0-9A-HJKMNP-TV-Z]{26}$`. On unknown id, return `410 Gone` with `since_unknown` and a recommended `start_after_event_id`. Combined with F‑16's 429, this bounds the DoS.

---

### F‑23 — `vault.proto` lacks structured sensitive marking

**Severity**: 🟢 medium

**Where**: `vault.proto` `GetCredentialResponse.value`, `PutCredentialRequest.value` (lines ~119–155, ~157–198).

**Why this is a problem**: the proto comments correctly call the field SENSITIVE, but there's no protobuf‑level option a code generator can pick up. Generated Go/Python clients will print the field with `%+v` / `repr()` unless the developer remembers to mask it.

**Recommended fix**: define a custom file‑level option:
```proto
import "google/protobuf/descriptor.proto";
extend google.protobuf.FieldOptions {
  bool mintkey_sensitive = 50001;
}
```
Mark `bytes value = 2 [(mintkey_sensitive) = true];` on `GetCredentialResponse` and `PutCredentialRequest`. Provide a small linter that fails compilation when a generated Stringer would emit a sensitive‑marked field.

---

### F‑24 — Change‑event has no hash chain (informational)

**Severity**: 🟢 medium

**Where**: `change-event.schema.json` envelope (lines ~37–55).

**Why this is a problem**: change events are not the source of truth — they're references — so no hash chain is fine. But the contract should say so explicitly, otherwise an integrator might assume change events provide tamper‑evidence.

**Recommended fix**: add to the file's top description:
> Change events are **fan‑out notifications**, not the audit record. Tamper‑evidence is provided by the per‑tenant hash chain on `audit_events` (ADR‑0014.7). Subscribers MUST reconcile against `GET /v1/tenants/{tid}/audit` for forensic purposes; they MUST NOT treat change events as authoritative.

---

### F‑25 — CSRF defense not in OpenAPI

**Severity**: 🔵 informational

**Where**: `openapi.yaml` security schemes — `OperatorSession` exists but no `X-CSRF-Token` header.

**Why this is a problem**: ADR‑0013 says "CSRF middleware on the FastAPI side specifically for AdminJS Custom Action calls. *Lean: yes — every state‑changing endpoint gets CSRF.*" SameSite=Strict on the cookie helps but is not bulletproof against same‑site subdomain attacks. If the contract doesn't declare it, generated clients won't send it.

**Recommended fix**: add a `CsrfHeader` security scheme (`type: apiKey, in: header, name: X-CSRF-Token`); apply on every POST/PATCH/DELETE that uses `OperatorSession`. Document the double‑submit cookie pattern (or token derived from session).

---

### F‑26 — Agent has no contract for per‑service TTL bounds

**Severity**: 🔵 informational

**Where**: `tools.yaml` `request_token` (lines ~424–429) and `service_full` (~141–186).

**Why this is a problem**: agents that don't know the per‑service min/max guess a TTL and get `invalid_argument`. The agent SDK's "refresh‑before‑call" pattern (ADR‑0014.9) needs the actual TTL bounds to refresh proactively.

**Recommended fix**: extend `service_full` with `min_ttl_seconds`, `max_ttl_seconds`, `default_ttl_seconds`. Reference these from the `request_token` description. Since this is the read path, no security implication, but it removes a guessing class of `invalid_argument` returns that pollute audit.

---

## What looks good (no findings)

- **Sensitive‑field marking on creation responses**: `Agent.api_key`, `Credential.value`, `CredApiKeyHeader.value`, `CredApiKeyQuery.value`, `CredBearerToken.value`, `CredBasicAuth.value`, `CredOAuth2ClientCredentials.client_secret`, `CredOidcClientSecret.client_secret`, `InternalLoginRequest.password`, `request_token` MCP output `token` — all carry `x-mintkey-sensitive: true` and are excluded from list responses (list returns `value: null`, `api_key: null`).
- **Hash chain on AuditEvent**: `prev_hash` and `hash` are present in the envelope per ADR‑0014.7. (Nullable for the genesis row is appropriate.)
- **Tenant in MCP**: `tools.yaml` correctly resolves tenant from the agent's authentication context — no `tenant_id` parameter on any tool. ADR‑0008/0009.
- **Span allowlist**: `span-attributes.md` is a strong, closed allowlist with CI enforcement and the right list of forbidden attributes (notwithstanding F‑21's gap).
- **Audit payloads omit credential value**: `ev_credential_registered`, `ev_credential_rotated`, `ev_credential_revoked` carry only `credential_id`, `service_id`, `key_version`, `auth_scheme` — no plaintext.
- **`agent.created` payload**: carries `api_key_fingerprint` (sha256), not the key. (Modulo the format inconsistency in F‑18.)
- **Path traversal & SSRF posture**: ADR‑0007 + threat model are explicit and consistent; the only gap is that the test‑run endpoint isn't yet a contract (F‑04).

## Categories without independent issues
- **Cryptography choices**: Ed25519, AES‑256‑GCM (one nonce per encryption), Argon2id, SHA‑256 hash chain — all named correctly in ADRs and reflected in contracts. *No issues found in cryptography primitive choice; F‑23 covers the codegen markup gap.*
- **Replay defense**: `jti` denylist (Postgres‑backed per ADR‑0016.1) and JWKS force‑refresh (ADR‑0016.2) are correctly specified in the ADRs; F‑06 is about surfacing them in the OpenAPI.
- **Secret bootstrap**: ADR‑0014.2 is sound; F‑14 is about reflecting it in `vault.proto`.
- **Plaintext credential lifetime in proxy**: ADR‑0014.4 is reflected in F‑AG‑02 ("zero plaintext from request scope"); contracts do not re‑introduce a plaintext cache. *No issues found in credential lifecycle in process memory.*

