# ADR‑0017: Round‑3 corrections from multi‑perspective contract review

## Status
Accepted — 2026-05-10. Captures 12 new wire‑level decisions and the appendix of mechanical contract corrections that are direct consequences of prior ADRs but were not reflected in the iteration‑4 contracts as drafted.

## Context

A three‑subagent review of the iteration‑4 contracts (`docs/contracts/`) and iteration‑3 flows (`docs/03-flows/`) produced 41 raw findings across three independent perspectives:
- **Security** (`docs/contracts/_review-security.md`).
- **ADR alignment + cross‑file consistency** (`docs/contracts/_review-alignment.md`).
- **Syntax + Kiro/SDD readiness** (`docs/contracts/_review-syntax-and-kiro.md`).

After dedup: 8 critical issues were cross‑confirmed by two or three reviewers; 14 high‑priority items needed action; 9 lower‑priority items moved to the [open‑questions register](../open-questions.md) as OQ‑014..OQ‑022.

This ADR captures only the items that introduce or formalize **new** wire surfaces or behavioral requirements. Items that are direct mechanical consequences of prior ADRs (mtls in enums per ADR‑0016.5, cascade_count in payload per ADR‑0016.7, …) appear in the appendix without new decisions.

## Decisions

### 17.1 AdminUiSignedRequest as a declared OpenAPI security scheme (formalizes ADR‑0014.6)
[ADR‑0014.6](0014-iter-1-2-corrections.md) defined the AdminJS↔FastAPI signed‑request envelope. The OpenAPI spec must declare it as a `securityScheme` and apply it on every state‑changing endpoint, otherwise generated stubs (Kiro, codegen) will skip the auth.

```yaml
securitySchemes:
  AdminUiSignedRequest:
    type: http
    scheme: bearer
    bearerFormat: JWT
    description: |
      Ed25519 JWT signed by the AdminJS service. Required on every endpoint
      AdminJS calls on behalf of an operator. Carries claims:
        iss: "mintkey/admin-ui"
        sub: <operator_id>
        tnt: <tenant_id>
        aud: "mintkey/admin-api"
        iat, exp (60s TTL)
        jti (UUID; replay-checked against admin_request_jti per ADR-0016.1)
      FastAPI verifies signature against AdminJS's public key fetched from the
      Vault Adapter under credential type 'admin_ui_signing_key'.
```

Every state‑changing operation in `openapi.yaml` includes `security: - AdminUiSignedRequest: []`.

### 17.2 ServiceIdentity security scheme + ValidateServiceIdentity RPC (formalizes ADR‑0014.2)

Service‑to‑service calls (Admin API → Vault Adapter, MCP Server → Vault Adapter, Kong‑syncer / proxy plugin → Admin API for reconciliation) carry a per‑service boot secret. The contracts must surface this:

**OpenAPI** declares a `ServiceIdentity` scheme used on `/v1/changes`, `/v1/tenants/{tid}/changes`, and any reconciliation endpoint:

```yaml
ServiceIdentity:
  type: apiKey
  in: header
  name: X-Mintkey-Service-Token
  description: |
    Per-service boot secret per ADR-0014.2. 32-byte random token,
    Argon2id-hashed at rest in the Vault Adapter under credential type
    'service_identity'. Constant-time compared. Rotated by re-running
    the seed job's --rotate-bootstrap subcommand.
```

**`vault.proto`** gains:
```proto
rpc ValidateServiceIdentity(ValidateServiceIdentityRequest)
   returns (ValidateServiceIdentityResponse);

message ValidateServiceIdentityRequest {
  string service_identity_id = 1;  // e.g., svcid_admin_api
  bytes  token               = 2;  // raw 32-byte token
}
message ValidateServiceIdentityResponse {
  bool                ok                  = 1;
  repeated string     scopes              = 2;  // policy-grant scopes
  google.protobuf.Timestamp valid_until   = 3;  // for the rotation overlap window
}
```

A new credential type `service_identity` is added to the Vault Adapter's recognized types.

### 17.3 CsrfHeader security scheme on browser‑originated state‑changing endpoints (formalizes ADR‑0013 + ADR‑0014)

```yaml
CsrfHeader:
  type: apiKey
  in: header
  name: X-Mintkey-Csrf
  description: |
    Double-submit CSRF token for browser-originated state changes.
    Issued on session creation; required on POST/PATCH/DELETE/PUT.
    Not required for service-to-service calls (those use AdminUiSignedRequest
    or ServiceIdentity).
```

Applied on all state‑changing endpoints reachable by a browser session.

### 17.4 `platform_admin.access` audit event for cross‑tenant reads (NEW)

[ADR‑0008](0008-multi-tenancy-row-level-with-db-tier.md) and [ADR‑0016.3](0016-round-2-corrections.md) make `PlatformAdmin` cross‑tenant reads a security event in their own right. Today the audit chain only captures state changes; cross‑tenant reads (audit query, changes feed, list operations with `platform_admin_view='on'`) are silent. Add `platform_admin.access` to the audit event schema:

```json
{
  "event_type": "platform_admin.access",
  "payload": {
    "resource_type":      "string",   // services|agents|credentials|audit|changes|...
    "viewed_tenant_ids":  ["string"], // [] or ["t_acme"] or ["__all__"]
    "endpoint":           "string",   // canonical OpenAPI operationId
    "result_count":       "integer",
    "reason":             "string"    // optional operator-supplied justification
  }
}
```

Emitted on every cross‑tenant read action. The hash chain captures it like any other event.

### 17.5 `/v1/auth/internal-login`: identical body and equalized timing (NEW; tightens ADR‑0005)

Internal login must defeat a username‑existence oracle:
- Response body for "unknown user", "wrong password", and "operator suspended" is **identical** (`401` with `mintkey:code = invalid_credentials`).
- Server **always runs an Argon2id verify** even if the user record is absent (against a fixed dummy hash) so timing is equalized.
- The audit event distinguishes `auth.login.failed.user_unknown`, `auth.login.failed.bad_password`, `auth.login.failed.account_locked` for forensics, but the API caller cannot distinguish them.

Encoded as a `description` constraint on the OpenAPI operation and in the requirements section of `F-OP-01`.

### 17.6 Span attribute redaction extended for `*_token`, `*_secret`, `*_password` patterns (NEW)

`docs/contracts/events/span-attributes.md`'s redaction policy currently forbids `mintkey.token`, `mintkey.api_key`, `mintkey.password`. Extend to **suffix patterns**:

- Forbid any attribute matching `*_token` (covers `mintkey.access_token`, `mintkey.refresh_token`, `mintkey.id_token`, `mintkey.session_token`).
- Forbid any attribute matching `*_secret` (covers `mintkey.client_secret`, `mintkey.signing_secret`).
- Forbid any attribute matching `*_password` and `*_passphrase`.
- Forbid `mintkey.authorization_header`, `mintkey.cookie_value`.
- The CI redaction test asserts no span attribute matches any forbidden pattern.

### 17.7 `/v1/changes?since=<unknown>` returns `410 Gone` (refines ADR‑0010)

Currently the spec implies "unknown `since` → return from start with a Warning header". This is a DoS + fingerprinting surface. Correction:
- Validate `since` parameter against ULID prefix `change_…` and a stable pattern.
- If valid format but the event_id is not in the log (e.g., subscriber lagged past retention), return `410 Gone` with `mintkey:code = since_unknown` and a `Problem+json` body that includes `oldest_known_event_id` so the subscriber can resync from a known point.
- Never silently start from the beginning.

### 17.8 `BrokeredTokenClaims` schema in OpenAPI (formalizes ADR‑0006 + ADR‑0008)

The brokered JWT's claim shape currently lives in prose in [ADR‑0006](0006-token-format-and-binding.md) and [ADR‑0008](0008-multi-tenancy-row-level-with-db-tier.md). Add a typed schema in OpenAPI so Kiro / codegen has a single source for token validators on the proxy and verifiers anywhere else:

```yaml
BrokeredTokenClaims:
  type: object
  required: [iss, sub, aud, scope, tnt, jti, iat, exp]
  additionalProperties: false
  properties:
    iss:   { const: "mintkey/broker" }
    sub:   { type: string, pattern: "^agent_[0-9A-HJKMNP-TV-Z]{26}$" }
    aud:   { type: string, pattern: "^svc_[0-9A-HJKMNP-TV-Z]{26}$" }
    tnt:   { type: string, pattern: "^tenant_[0-9A-HJKMNP-TV-Z]{26}$" }
    scope: { type: string, description: "Single action, e.g., read:contacts." }
    jti:   { type: string, pattern: "^[0-9A-HJKMNP-TV-Z]{26}$" }
    iat:   { type: integer, format: int64 }
    exp:   { type: integer, format: int64 }
    cnf:   { type: object, properties: { jkt: { type: string } } }
    kid:   { type: string }
```

Referenced from MCP `request_token` and any internal verifier docs.

### 17.9 Default tenant slug is `t_default` (canonical)

Drift between OpenAPI examples (`slug: "default"`) and ADR‑0008 / glossary (`t_default`). Resolution: **the canonical default tenant slug is `t_default`**. Update every example.

### 17.10 REST `mintkey:code` ↔ MCP `error_code` mapping (formalizes both)

REST and MCP have separate machine‑readable error vocabularies. Document them both in `docs/contracts/README.md` with an explicit mapping table:

| Concept | REST `mintkey:code` | MCP `error_code` |
|---|---|---|
| Invalid credentials | `invalid_credentials` | n/a (REST‑only) |
| Tenant not found | `tenant_not_found` | n/a |
| Tenant suspended | `tenant_suspended` | `tenant_suspended` |
| Tenant deleted | `tenant_deleted` | `tenant_deleted` |
| Agent not authorized | `permission_denied` | `not_authorized` |
| Agent revoked | `agent_revoked` | `agent_revoked` |
| Service not found | `service_not_found` | `service_not_found` |
| Action not granted | `action_not_granted` | `action_not_granted` |
| Token expired | `token_expired` | `token_expired` |
| Token revoked | `token_revoked` | `token_revoked` |
| Rate limited | `rate_limited` | `rate_limited` |
| Validation failed | `validation_failed` | `validation_failed` |

Both vocabularies are **closed enums** in their respective contracts. New codes require an ADR.

### 17.11 ULID‑with‑prefix is the canonical wire form for IDs (clarifies ADR‑0008)

ADR‑0008 says `tenant_id UUID NOT NULL`; OpenAPI examples use `tenant_…<ULID>`; OpenAPI prose at lines 20+37 contradicts itself.

**Resolution**: at the wire (OpenAPI, MCP tools, audit/change events, vault.proto), every ID is **a ULID with a stable prefix** and pattern `^<prefix>_[0-9A-HJKMNP-TV-Z]{26}$`. The DB schema (Liquibase per ADR‑0015) may store the underlying 16 bytes as a UUID column; the wire form is always prefixed‑ULID.

Prefix table is the canonical reference: `tenant_…`, `operator_…`, `agent_…`, `svc_…`, `cred_…`, `perm_…`, `audit_…`, `change_…`, `session_…`, `system_…` (see 17.13).

OpenAPI defines a `UlidId` reusable schema with the prefix as a parameter. All ID properties `$ref` it.

### 17.12 `change-event` envelope adds `actor_type` (refines ADR‑0010)

The `audit-event` envelope has `actor_type`; the `change-event` envelope was missing it. Add `actor_type` (enum: `operator`, `agent`, `system`, `platform_admin`) to the change‑event envelope so subscribers know who triggered the event without parsing the actor ID prefix.

### 17.13 `system_…` actor prefix added to glossary

Used by the Audit Service, KEK rotation jobs, and the audit chain verification job. Documented in [`docs/00-vision/04-glossary.md`](../../00-vision/04-glossary.md) and the OpenAPI prefix table.

---

## Contract mechanical corrections (no new decisions; appendix)

These items are direct consequences of prior ADRs that the contracts as initially drafted did not reflect. Listed for traceability.

| # | Item | Source ADR | Files affected |
|---|------|------------|----------------|
| C‑01 | Channel naming reconciled to global (`mintkey:service`, `mintkey:credential`, `mintkey:agent`, `mintkey:heartbeat`); tenant filter is application‑layer | ADR‑0014.1 | `change-event.schema.json`, `openapi.yaml` (descriptions) |
| C‑02 | `mtls` added to every `auth_scheme` enum + `MtlsCredentialValue` schema in OpenAPI + `AUTH_SCHEME_MTLS = 7` in proto | ADR‑0016.5 | `openapi.yaml`, `tools.yaml`, `audit-event.schema.json`, `vault.proto`, `contracts/README.md` |
| C‑03 | `Permission.constraints` replaced with closed `Constraints` schema (rate_limit, time_window, request_path_prefix, source_ip_allowlist) | ADR‑0016.4 | `openapi.yaml`, `audit-event.schema.json` |
| C‑04 | `GET /v1/admin/settings` + `PATCH /v1/admin/settings` + `AdminSettings` schema + `settings.updated` audit event | ADR‑0016.6 | `openapi.yaml`, `audit-event.schema.json` |
| C‑05 | `tenant.deleted` payload extended with `cascade_count: { agents, services, credentials, permissions }` | ADR‑0016.7 | `audit-event.schema.json` |
| C‑06 | MCP error codes `agent_revoked`, `tenant_deleted` added to enum | ADR‑0016.7 | `tools.yaml` |
| C‑07 | MCP tools doc adds the tenant/agent‑deletion in‑flight behavior table | ADR‑0016.7 | `tools.yaml` |
| C‑08 | `audit.chain.verified` and `audit.chain.tampered` event types added | ADR‑0014.7 | `audit-event.schema.json` |
| C‑09 | `service.test_executed` audit event added with payload `{ method, path_template, status_code, latency_ms, ok, error? }` | iteration 3 / F‑OP‑03 | `audit-event.schema.json` |
| C‑10 | `tenant.bootstrap_completed` audit event added with payload `{ slug, isolation_mode }` | iteration 3 / F‑OP‑01 | `audit-event.schema.json` |
| C‑11 | `POST /v1/tenants/{tid}/services/{sid}/test` endpoint with rate limit, RFC1918 rejection per ADR‑0007, request/response schemas | iteration 3 / F‑OP‑03 | `openapi.yaml` |
| C‑12 | OpenAPI `nullable: true` migrated to OAS‑3.1 `type: [<orig>, "null"]` form across 21 lines | OAS 3.1 spec compliance | `openapi.yaml` |
| C‑13 | Service vs `service.registered` audit drift: payload extended with `display_name` (required), `openapi_url` and `description` (optional) | ADR‑0006 alignment | `audit-event.schema.json` |
| C‑14 | ~30 missing JSON Schema descriptions filled in on substantive payload properties | Kiro readiness | `audit-event.schema.json`, `change-event.schema.json` |
| C‑15 | Realistic‑looking credential strings in OpenAPI examples replaced with obvious placeholders | Security hygiene | `openapi.yaml` |
| C‑16 | Orphan `Session` schema removed; `UlidId` wired into all ID props | OpenAPI cleanup | `openapi.yaml` |
| C‑17 | `active_tenant` example responses updated to satisfy `required` on `Tenant`; email example fixed to satisfy `format: email` | OpenAPI lint | `openapi.yaml` |
| C‑18 | Mermaid syntax fixes in 8 sequence diagrams (`;` → `,`, `<base32-26>` → `(base32-26)`, `style` keyword collision) | Renderer compatibility | `docs/03-flows/*.md`, `docs/00-vision/07-kiro-readiness.md` |
| C‑19 | F‑OP‑01 gains "Contracts touched" line | Kiro readiness | `docs/03-flows/F-OP-01-bootstrap-and-login.md` |

## Consequences

### Positive
- All 8 cross‑confirmed critical issues from the multi‑perspective review resolved.
- Kiro now has unambiguous, internally consistent contracts to generate code from. No fields left to guess.
- Every state‑changing API endpoint has a declared security scheme; codegen can't accidentally skip auth.
- Cross‑tenant `PlatformAdmin` reads are visible in the audit chain.
- Internal‑login is timing‑attack hardened.
- Span redaction policy covers the suffix patterns Kiro/auto‑instrumentation libraries are most likely to introduce.
- OpenAPI is OAS‑3.1 compliant (Redocly errors → 0 expected after migration).

### Costs
- The OpenAPI gains ~8 new schemas and ~4 new endpoints; net file growth ~15%.
- Vault Adapter gains a new RPC; Vault Adapter implementations must be updated before the boot‑secret protocol becomes production‑usable.
- Audit log volume grows: every cross‑tenant read by a PlatformAdmin emits an event.
- AdminJS sign‑and‑send middleware required on every state‑changing endpoint.
- A small CI script for OpenAPI ↔ FastAPI parity ([ADR‑0014.3](0014-iter-1-2-corrections.md)) needs to learn the new schemas.

### Risks (net of corrections)
- **AdminJS public‑key rotation** (per ADR‑0014.6) is now load‑bearing for every admin write; if the public‑key fetch from Vault Adapter fails, AdminJS is dead. Mitigation: cache aggressively (1 h TTL), force‑refresh on signature‑verify failure (mirrors ADR‑0016.2 pattern).
- **`platform_admin.access` event volume** in environments with active cross‑tenant operations could be high. Mitigation: retention policy 17.10 covers it.

## Deferred items → open‑questions register

Tracked as OQ‑014..OQ‑022 in [open‑questions.md](../open-questions.md):
- OQ‑014 `AgentApiKey` declared but unapplied (delete or apply).
- OQ‑015 Constant‑time compare guidance for Bearer key in MCP doc.
- OQ‑016 `Tenant.settings` closed schema.
- OQ‑017 `api_key_fingerprint` format consistency (full SHA‑256 vs 8‑hex).
- OQ‑018 `username_attempted` length cap and salted hash in prod.
- OQ‑019 `redirect_uri` allowlist validation algorithm.
- OQ‑020 Proto field `(mintkey_sensitive) = true` option for codegen.
- OQ‑021 Change‑event envelope hash chain note.
- OQ‑022 Per‑service min/max TTL bounds in MCP `service_full`.

## Related
- [ADR‑0014](0014-iter-1-2-corrections.md) — round‑1 corrections.
- [ADR‑0016](0016-round-2-corrections.md) — round‑2 corrections.
- All amended prior ADRs: 0005, 0006, 0008, 0010, 0013, 0014, 0016.
- Multi‑perspective review reports: `docs/contracts/_review-security.md`, `_review-alignment.md`, `_review-syntax-and-kiro.md`.
- [open‑questions.md](../open-questions.md).
