# Requirements Document — Classical Service API Keys

## Status

**DRAFT — blocked on `ADR-0018-classical-service-api-keys` (per `proposal/P-010` § "Outcome", decided 2026-05-11).** MUST NOT be promoted to `tasks.md` until ADR-0018 is Accepted. This document supersedes the earlier "Extended API Keys" (extended-brokered-JWT) version of this spec — that option (P-010 Option C) was rejected; the extended-JWT draft is retained in git history.

## Introduction

This feature adds **classical service API keys** — long-lived opaque static tokens that an operator issues from the Admin Console and that a **non-agent client** (a script, cron job, CI pipeline, third-party integration — anything that cannot or will not perform the MCP discovery + `request_token` exchange) presents directly to the egress proxy. The proxy recognises the key, resolves it **server-side** against the Broker (with a short cache), re-checks the requested action and any configured `Constraints` on **every request**, then injects the real backend credential exactly as it does for a brokered JWT. The client never sees, and never holds, the real backend credential — that property is preserved; what changes is that the client now holds a *long-lived bearer credential for Mintkey* (the API key) instead of a *short-lived one* (a brokered JWT).

**This is the standard API-gateway primitive, and it carries the standard tradeoff:** a leaked classical API key grants its `(service, actions)` access until the key is revoked. The mitigations are: a short proxy resolution-cache TTL (so revocation propagates in seconds, not minutes); optional per-key expiry (and an operator policy to *require* expiry); optional per-key `Constraints` — and unlike the rejected extended-JWT design, **all four `Constraints` kinds, including `time_window` and `rate_limit`, are enforced on every request** (the proxy does a server-side lookup anyway), so a classical key can be more tightly scoped than a brokered token ever was; an operator policy to *require* a `source_ip_allowlist`; fingerprint-only audit and OTel (the plaintext never appears in any log, span, or audit payload); and the rule that a key can never exceed its bound Agent's permission grants (revoking the Agent revokes all its keys). The threat-model document (`docs/architecture/01-architecture/05-threat-model.md`) MUST be updated to record this tradeoff and its mitigations before this feature ships.

Agents are **not** affected: they continue to use short-lived brokered JWTs (and the `refresh_at` ergonomic hint adopted as P-010 Option A). Classical API keys add no MCP surface.

## Architectural Prerequisites

This feature adds a new credential type, a new proxy code path, a new Broker endpoint, and new wire surfaces. Per `AGENTS.md` governance, `ADR-0018-classical-service-api-keys` MUST be Accepted before implementation. The ADR must decide:

- the token format and prefix (this document assumes `mk_svckey_<Crockford-base32 of 32 random bytes>`, Argon2id-hashed at rest with the same parameters as the Agent API Key, with an 8-byte fingerprint `hex(sha256(plaintext)[:8])` stored alongside for O(1) lookup);
- the server-side resolution model and the proxy resolution-cache TTL bound (this document assumes the proxy caches the resolution result keyed by fingerprint for `AdminSettings.api_key.proxy_cache_ttl_seconds`, default 60, range `[10, 300]`);
- that an API key binds to an **existing Agent** in v1 (a dedicated "service-account" principal type — an Agent with no MCP key — is a noted future refinement; see Out of Scope);
- the resolution endpoint owner (this document assumes the **Broker** — consistent with it being the token authority and already running an HTTP server — at `POST /v1/api-keys/resolve`, authenticated with `svcid_proxy` per ADR-0014.2);
- the `mintkey:code` enum delta (the new codes in § "Error Codes" below, added to ADR-0017.10's closed enum);
- the change-channel event (this document assumes `api_key.revoked` on the global `mintkey:agent` channel per ADR-0014.1, carrying `key_fingerprint`);
- whether an operator policy may make per-key `expires_at` and/or a `source_ip_allowlist` constraint **mandatory** (this document assumes yes, via `AdminSettings` booleans `api_key.require_expiry` and `api_key.require_ip_allowlist`, both default `false`).

## Glossary

- **Service_API_Key**: A long-lived opaque token `mk_svckey_<…>`, operator-issued, bound to one Agent + one Service + a non-empty subset of that Agent's `(service, action)` permission grants + an optional `expires_at` (absent = no expiry) + an optional `constraints` object (the closed `Constraints` schema, ADR-0016.4). Argon2id-hashed at rest; the plaintext is shown exactly once at creation.
- **Bound Agent**: The Agent a Service_API_Key acts as. The key inherits, and cannot exceed, that Agent's permission grants for the bound Service. Revoking the Agent (ADR-0008 `agents.status = 'revoked'`) revokes all its Service_API_Keys.
- **Key_Fingerprint**: `hex(sha256(plaintext)[:8])` — 16 hex chars. Stored on the row; used by the proxy to index its resolution cache and by the resolver to find the candidate row before the Argon2id verify. Safe to log / put in audit payloads (it is not the secret); it is *not* a span attribute by default.
- **Resolution_Endpoint**: The Broker endpoint `POST /v1/api-keys/resolve` that the proxy calls on a resolution-cache miss. Authenticated with `svcid_proxy`. Does a constant-time Argon2id verify; rate-limited per fingerprint and per source IP.
- **Resolution_Cache**: The proxy's in-memory cache of successful resolutions, keyed by `Key_Fingerprint`, TTL `AdminSettings.api_key.proxy_cache_ttl_seconds`. Evicted on an `api_key.revoked` change-channel event. A cache hit performs no Argon2id verify; a cache miss does (Argon2id is deliberately slow — the cache is what keeps the hot path fast).
- **Brokered_JWT**: The existing short-lived agent token. Unchanged by this feature; the proxy distinguishes the two by the credential's leading bytes (`eyJ…` = JWT; `mk_svckey_…` = Service_API_Key).
- **Proxy**: The Kong egress proxy with the Go plugin.
- **Admin_Console**: The AdminJS operator UI; all writes route through the Admin REST API with the AdminUiSignedRequest envelope.
- **Change_Channel**: Postgres `LISTEN/NOTIFY`, global channels (`mintkey:service`, `mintkey:agent`, `mintkey:credential`, `mintkey:heartbeat`) with application-layer tenant filtering (ADR-0010, ADR-0014.1).

## Error Codes

Added to ADR-0017.10's closed `mintkey:code` enum (and to the OpenAPI error-code list):

- `api_key_invalid` — the presented key is malformed, has no matching fingerprint, or fails the Argon2id verify. (Returned uniformly for all three to avoid an existence oracle; the audit distinguishes them.)
- `api_key_expired` — the key's `expires_at` is in the past.
- `api_key_revoked` — the key's `revoked_at` is set, or its bound Agent is revoked.
- `api_key_wrong_service` — the key is bound to a different `service_id` than the one in the request URL.
- `api_key_action_not_allowed` — the action the request maps to is not in the key's `allowed_actions`.
- `api_key_constraint_failed` — a `Constraints` check failed for this request; the message names the failing kind (`request_path_prefix` / `source_ip_allowlist` / `time_window` / `rate_limit`).
- `api_key_resolution_unavailable` — the Resolution_Endpoint is unreachable and there is no cached resolution for this fingerprint (fail-closed for the cache-miss-during-outage case only; cache hits are unaffected).
- `api_key_actions_exceed_grant` — (Admin REST API, HTTP 422) the `allowed_actions` requested at key creation are not a subset of the bound Agent's permission grants for the bound Service.
- `api_key_policy_violation` — (Admin REST API, HTTP 422) the create request violates an operator policy (`require_expiry` set but no `expires_at`; `require_ip_allowlist` set but no `source_ip_allowlist`; `expires_at` beyond `api_key.max_expiry_days`; `allow_no_expiry` false but no `expires_at`).

## Requirements

### Requirement 1: API Key Issuance

**User Story:** As an operator, I want to issue a long-lived API key bound to one of my agents and one service, so that a script or integration that can't speak MCP can call that service through Mintkey.

#### Acceptance Criteria

1. WHEN an operator submits a create request with `{service_id, allowed_actions[], expires_at?, constraints?}` for a given agent, AND `allowed_actions` is non-empty and is a subset of the agent's permission grants for `service_id`, AND `constraints` validates against the closed `Constraints` schema, AND the request satisfies the operator policies (R10.4), THEN the Admin REST API SHALL generate a 32-byte-entropy opaque key `mk_svckey_<Crockford-base32>`, store its Argon2id hash, `key_fingerprint`, binding (`agent_id`, `service_id`, `allowed_actions`, `constraints`, `expires_at`), `created_by`, and `created_at` in `service_api_keys`, emit audit event `api_key.created` (chokepoint + hash chain) with payload `{api_key_id, key_fingerprint, agent_id, service_id, allowed_actions, expires_at, constraints, created_by}` — **never the plaintext** — and return HTTP 201 `{api_key_id, plaintext_key, key_fingerprint, agent_id, service_id, allowed_actions, expires_at, constraints, created_at}`.
2. THE plaintext key SHALL be returned **exactly once**, in the 201 response; no subsequent endpoint SHALL return it; the Admin Console SHALL display it in a copy box with a "shown once — store it now" warning.
3. WHEN `allowed_actions` contains an action not present in the agent's permission grants for `service_id`, THE Admin REST API SHALL return HTTP 422 `api_key_actions_exceed_grant`.
4. WHEN the request violates an operator policy (R10.4), THE Admin REST API SHALL return HTTP 422 `api_key_policy_violation` with a message naming the violated policy.
5. IF the generated `key_fingerprint` collides with an existing row (astronomically unlikely with 32 bytes of entropy), THEN THE Admin REST API SHALL regenerate the key and retry (bounded retries); a `UNIQUE` constraint on `key_fingerprint` enforces this at the DB level.
6. THE create endpoint SHALL require the AdminUiSignedRequest envelope (state-changing operation) and SHALL be subject to the standard CSRF and tenant-context middleware.

### Requirement 2: API Key Use at the Proxy

**User Story:** As a script author, I want to put my Mintkey API key in a config file and call `https://<mintkey>/v1/call/<service_id>/<path>` like any REST API, so that I don't have to implement an OAuth-style token exchange.

#### Acceptance Criteria

1. WHEN the Proxy receives a request to `/v1/call/{service_id}/{path...}` whose credential (in `Authorization: Bearer …` or the service's configured inbound header) begins with `mk_svckey_`, THE Proxy SHALL treat it as a Service_API_Key (the classical-key path), NOT a Brokered_JWT.
2. WHEN the Proxy is on the classical-key path, IT SHALL compute the `Key_Fingerprint` and look it up in its Resolution_Cache; on a cache hit it SHALL use the cached resolution (`{api_key_id, agent_id, service_id, allowed_actions, constraints, expires_at}`) without contacting the Broker; on a cache miss it SHALL call the Resolution_Endpoint (R3) and, on success, cache the result for `AdminSettings.api_key.proxy_cache_ttl_seconds`.
3. WHEN the Proxy has a resolution (cached or fresh), IT SHALL, on **every** request, in order:
   a. verify `service_id` from the resolution equals `service_id` in the URL — else HTTP 401 `api_key_wrong_service`;
   b. verify `expires_at` (if present) is in the future — else HTTP 401 `api_key_expired` (and evict the cache entry);
   c. derive the request's action from `{method, path}` per the service's action mapping and verify it is in `allowed_actions` — else HTTP 403 `api_key_action_not_allowed`;
   d. evaluate each of the up-to-four `constraints` kinds against **this** request — `request_path_prefix` (the path starts with the prefix), `source_ip_allowlist` (the client IP is in the list), `time_window` (now is within the window in the configured timezone), `rate_limit` (the per-key in-memory token bucket has capacity) — else HTTP 403 `api_key_constraint_failed` naming the failing kind;
   e. on all checks passing, fetch the real backend credential from the Vault Adapter and inject it per the service's auth scheme exactly as on the Brokered_JWT path; strip the client's `Authorization` before forwarding to the backend.
4. WHEN any classical-key request completes, THE Proxy SHALL emit `proxy.hit` audit (chokepoint) with `auth_method: "api_key"`, `api_key_id`, `key_fingerprint`, and the usual `{service_id, action, request_method, request_path_template, status_code, latency_ms, outcome}` — **never the plaintext key**; and SHALL include a `used_at` timestamp so the Admin REST API can update `service_api_keys.last_used_at` (coalesced ≤ 1 write per `api_key_id` per minute, per R10.5).
5. WHEN a `mk_svckey_` credential is presented to an endpoint other than `/v1/call/{service_id}/{path...}` (e.g. somehow to the MCP server or the Admin REST API), THE receiving service SHALL reject it with the same error it would give any other invalid credential for that endpoint; classical API keys are valid **only** at the proxy's `/v1/call/...` route.
6. THE Proxy SHALL set the OTel span attribute `mintkey.auth_method` (`"brokered_jwt"` or `"api_key"`) on every `/v1/call/...` span; the `key_fingerprint` SHALL NOT be a span attribute.

### Requirement 3: Server-Side Resolution Endpoint

**User Story:** As the proxy, I need to confirm a presented API key is genuine, live, and bound to the service in the URL, without holding any key material myself.

#### Acceptance Criteria

1. THE Broker SHALL expose `POST /v1/api-keys/resolve`, authenticated with `X-Mintkey-Service-Token: <svcid_proxy>` (ADR-0014.2); requests without a valid service token SHALL get HTTP 401.
2. WHEN the Resolution_Endpoint receives `{key_fingerprint, presented_key, service_id, tenant_id}`, IT SHALL: validate `tenant_id` is a well-formed prefixed-ULID and `SET app.current_tenant`; `SELECT … FROM service_api_keys WHERE key_fingerprint = :fp`; if no row → 401 `api_key_invalid`; perform a **constant-time Argon2id verify** of `presented_key` against `key_hash`; if it fails → 401 `api_key_invalid`; if `revoked_at IS NOT NULL` or the bound agent's `status = 'revoked'` → 401 `api_key_revoked`; if `expires_at` is in the past → 401 `api_key_expired`; if `service_id` ≠ the row's `service_id` → 401 `api_key_wrong_service`; otherwise → 200 `{api_key_id, agent_id, service_id, allowed_actions, constraints, expires_at}`.
3. THE Resolution_Endpoint SHALL be rate-limited per `key_fingerprint` (e.g. 20/min) and per source-of-the-svcid-proxy-caller IP; exceeding either returns 429. (The per-fingerprint limit blunts brute-force against a guessed fingerprint; the verify is already Argon2id-slow.)
4. THE Resolution_Endpoint SHALL emit no audit event per call (it would 10×–100× audit volume); the proxy's `proxy.hit` records usage, and a distinct first-use signal is unnecessary.
5. THE Resolution_Endpoint SHALL distinguish failure reasons in its **own structured log** (for forensics) but SHALL return the uniform `api_key_invalid` for malformed / unknown-fingerprint / verify-failed, so a caller cannot use the response to enumerate valid fingerprints.

### Requirement 4: Revocation

**User Story:** As an operator, I want to revoke an API key the moment I suspect it's compromised, so that it stops working within seconds.

#### Acceptance Criteria

1. WHEN an operator revokes a Service_API_Key via the Admin Console, THE Admin REST API SHALL, in one DB transaction, set `revoked_at = now()`, `revoked_by`, `revoke_reason`; emit `api_key.revoked` audit (chokepoint + hash chain) with `{api_key_id, key_fingerprint, revoked_by, reason}`; and `pg_notify('mintkey:agent', json{event:"api_key.revoked", tenant_id, api_key_id, key_fingerprint, reason})`.
2. WHEN the Proxy receives an `api_key.revoked` change-channel event, IT SHALL evict the entry for that `key_fingerprint` from its Resolution_Cache within 5 seconds.
3. A revoked key SHALL be denied by the Proxy within the lesser of: 5 seconds (change-channel propagation), or `AdminSettings.api_key.proxy_cache_ttl_seconds` (the cache entry's natural expiry).
4. WHEN an operator revokes the **Agent** a key is bound to, THE Resolution_Endpoint SHALL thereafter return `api_key_revoked` for that key (it checks `agents.status`); the proxy's existing `agent.revoked` change-channel handling SHALL additionally evict any Resolution_Cache entries whose `agent_id` matches.
5. THE revoke endpoint SHALL be idempotent: revoking an already-revoked key returns HTTP 200; revoking a non-existent key returns HTTP 404.

### Requirement 5: Rotation

**User Story:** As an operator, I want to roll an API key with an overlap window, so that I can update clients before the old key stops working.

#### Acceptance Criteria

1. WHEN an operator triggers "Rotate" on a Service_API_Key, THE Admin REST API SHALL create a **new** Service_API_Key with the same `(agent_id, service_id, allowed_actions, constraints)` and an `expires_at` recomputed as `now() + (old.expires_at - old.created_at)` if the old key had an expiry, else null; return HTTP 201 with the new plaintext (shown once); emit `api_key.rotated` audit (chokepoint + hash chain) with `{old_api_key_id, new_api_key_id, agent_id, service_id, rotated_by}`; and **NOT** revoke the old key.
2. THE old key SHALL remain valid until the operator explicitly revokes it (R4) — the overlap window is operator-controlled.
3. THE Admin Console SHALL surface, for a rotated pair, both keys in the agent's key list with a visual link ("rotated from …" / "rotated to …") until the old one is revoked.

### Requirement 6: Constraints

**User Story:** As an operator, I want to scope an API key by path, source IP, time window, and rate, so that a leaked key is useful to an attacker only within the bounds I set.

#### Acceptance Criteria

1. A Service_API_Key MAY carry a `constraints` object validated against the closed `Constraints` schema (ADR-0016.4): `request_path_prefix` (string), `source_ip_allowlist` (array of CIDRs), `time_window` (`{timezone, days[], start_local, end_local}`), `rate_limit` (`{requests_per_second, burst}`). Unknown keys are rejected (`additionalProperties: false`).
2. THE Proxy SHALL evaluate **all** present `constraints` kinds on **every** request (R2.3.d). Unlike a brokered token (where `time_window` and `rate_limit` are evaluated once at issuance), here the proxy re-checks them per request — a classical key with a `time_window` is usable *only* during that window, every time.
3. THE `rate_limit` for a key SHALL be enforced by a per-`api_key_id` in-memory token bucket in the Proxy; the bucket is per-proxy-instance (acceptable for v1 — exact global rate limiting across proxy replicas is out of scope, as it is for permission-grant rate limits).
4. WHEN a constraint check fails, THE Proxy SHALL return HTTP 403 `api_key_constraint_failed` with a message naming the failing kind, and SHALL emit `proxy.hit` with `outcome: "denied"` and a `reason_code` field set to `constraint_failed:<kind>`.

### Requirement 7: Schema Migration

**User Story:** As a developer, I want the database schema to persist API keys with the same multi-tenant and audit guarantees as the rest of the schema.

#### Acceptance Criteria

1. THE Liquibase changeset (new — `apps/admin-api/db/changelog/012-service-api-keys.yaml`; Liquibase is the source of truth per ADR-0015) SHALL create table `service_api_keys` with columns: `id UUID PRIMARY KEY`, `tenant_id UUID NOT NULL REFERENCES tenants(id)`, `agent_id UUID NOT NULL REFERENCES agents(id)`, `service_id UUID NOT NULL REFERENCES services(id)`, `key_hash TEXT NOT NULL`, `key_fingerprint CHAR(16) NOT NULL`, `allowed_actions TEXT[] NOT NULL`, `constraints JSONB`, `expires_at TIMESTAMPTZ`, `last_used_at TIMESTAMPTZ`, `revoked_at TIMESTAMPTZ`, `revoked_by UUID`, `revoke_reason TEXT`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `created_by UUID NOT NULL`.
2. THE changeset SHALL add `CONSTRAINT uq_service_api_keys_fingerprint UNIQUE (key_fingerprint)`; `CHECK (array_length(allowed_actions, 1) >= 1)`; `CHECK (expires_at IS NULL OR expires_at > created_at)`.
3. THE changeset SHALL add indexes `(agent_id, service_id) WHERE revoked_at IS NULL` and `(service_id) WHERE revoked_at IS NULL`. Partial-index predicates MUST be IMMUTABLE — **no `now()`** (that fails the migration); "active" (= not revoked and not expired) is computed at query time, not in an index predicate.
4. THE `service_api_keys` table SHALL have the byte-for-byte standard tenant-isolation RLS policy — `USING (tenant_id = current_setting('app.current_tenant', true)::uuid OR current_setting('app.platform_admin_view', true) = 'on')` — in the same changeset as the table (ADR-0014.8, ADR-0016.3). It is a tenant-scoped table; NOT on the platform-scoped RLS-exclusion allowlist.
5. THE changeset SHALL include an explicit `rollback` block (per the Liquibase-rollback-safety policy).
6. THE `AdminSettings` closed schema (ADR-0016.6) SHALL gain an `api_key` sub-object with keys `proxy_cache_ttl_seconds` (int, default 60, `[10, 300]`), `require_expiry` (bool, default false), `allow_no_expiry` (bool, default true), `max_expiry_days` (int, default 365, `[1, 3650]`), `require_ip_allowlist` (bool, default false) — no new table, new keys only.

### Requirement 8: Admin REST API Endpoints

**User Story:** As the Admin Console (and any operator scripting against the API), I need CRUD-ish endpoints for service API keys.

#### Acceptance Criteria

1. `POST /v1/tenants/{tid}/agents/{aid}/api-keys` — create (R1). Body `{service_id, allowed_actions[], expires_at?, constraints?}`. Returns 201 with the plaintext once.
2. `GET /v1/tenants/{tid}/agents/{aid}/api-keys` — list. Returns `[{api_key_id, key_fingerprint, service_id, allowed_actions, constraints, expires_at, last_used_at, created_at, created_by, status}]` where `status ∈ {active, expired, revoked}`. **Never the plaintext.** Supports filtering by `service_id` and `status`.
3. `GET /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}` — single key, same shape as the list element. No plaintext.
4. `POST /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/revoke` — body `{reason}`. R4. Idempotent.
5. `POST /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/rotate` — body `{reason?}`. R5. Returns 201 with the new key's plaintext once.
6. ALL of the above SHALL enforce the tenant-context middleware (RLS), and the state-changing ones (create / revoke / rotate) SHALL enforce the AdminUiSignedRequest envelope and CSRF middleware. Reads are RLS-scoped to `{tid}`.
7. THE `proxy.hit` internal audit endpoint SHALL accept the new optional fields `auth_method`, `api_key_id`, `key_fingerprint`, `used_at` and SHALL perform the coalesced `last_used_at` update (R10.5) inside the audit transaction.

### Requirement 9: Admin Console

**User Story:** As an operator, I want to manage an agent's API keys from the agent's detail page.

#### Acceptance Criteria

1. THE Admin Console SHALL add an "API Keys" tab to the Agent detail page (alongside the existing Permissions / Audit tabs), listing the agent's keys: `key_fingerprint`, service, `allowed_actions`, constraints summary, `expires_at`, `last_used_at` (blank = never used), status.
2. THE "Create API Key" form SHALL let the operator pick a Service (from the agent's services), pick `allowed_actions` (a multiselect limited client-side to the agent's grants for the chosen service — the server re-validates per R1.3), set an optional Expiry (a date/time picker; required and bounded if the operator policies say so — R10.4), and set an optional Constraints sub-form (the same component used for permission-grant constraints; `source_ip_allowlist` required if `require_ip_allowlist`). On success it SHALL display the plaintext key in a copy box with a "shown once" warning.
3. THE list SHALL offer per-key "Revoke" (with a reason field) and "Rotate" actions; "Rotate" SHALL display the new key's plaintext once and link the old/new pair until the old is revoked.
4. ALL writes SHALL route through the Admin REST API with the AdminUiSignedRequest envelope (ADR-0014.5/0014.6); AdminJS SHALL NOT write `service_api_keys` directly (it reads via the read-only `@adminjs/sql` adapter).

### Requirement 10: Security Hardening

**User Story:** As a security engineer, I want the API-key safeguards to be enforced, not advisory.

#### Acceptance Criteria

1. THE plaintext API key SHALL NOT appear in any log line, OTel span attribute, audit payload, or any API response other than the one-time 201 at creation / rotation. Only the `key_fingerprint` and `api_key_id` appear in audit / logs; only `mintkey.auth_method` appears in spans.
2. THE Argon2id verify in the Resolution_Endpoint SHALL be constant-time with respect to a wrong key (compare via a fixed-cost path even for an unknown fingerprint — verify against a fixed dummy hash so timing does not reveal fingerprint existence).
3. THE Resolution_Endpoint SHALL be rate-limited per fingerprint and per caller (R3.3); the Proxy SHALL additionally apply a brief in-memory backoff after a 401 for a given fingerprint so a flood of a known-bad key does not hammer the Broker.
4. THE Admin REST API SHALL enforce the operator policies on key creation: if `api_key.require_expiry` is true, `expires_at` is required; if `api_key.allow_no_expiry` is false, `expires_at` is required; `expires_at` MUST be ≤ `now() + api_key.max_expiry_days`; if `api_key.require_ip_allowlist` is true, `constraints.source_ip_allowlist` is required and non-empty. Violations → HTTP 422 `api_key_policy_violation`.
5. THE Proxy SHALL coalesce `last_used_at` updates: at most one update per `api_key_id` per minute (the proxy tracks a per-`api_key_id` "last reported" timestamp and skips re-reporting within the minute). The update is performed by the Admin REST API inside the `proxy.hit` audit transaction; the proxy never writes the DB directly (ADR-0014.4).
6. WHEN the Resolution_Endpoint is unreachable and there is no cached resolution for a presented key, THE Proxy SHALL return HTTP 503 `api_key_resolution_unavailable` (fail-closed for the cache-miss-during-outage case); cache hits are served normally throughout an outage (this is a `min(cache TTL, outage)` exposure window for revocations, accepted).
7. An architecture test SHALL grep all container logs, OTel exports, and `audit_events.payload` for any string matching `^mk_svckey_` and assert zero matches (extends the mintkey-mvp red-team grep, T-1.3.3).

### Requirement 11: Contract and Schema Propagation

**User Story:** As an architecture maintainer, I want every wire surface this feature touches updated in lock-step so the CI parity gates stay green.

#### Acceptance Criteria

1. THE OpenAPI YAML (`docs/architecture/contracts/rest/openapi.yaml`, canonical per ADR-0014.3) SHALL be updated: a `ServiceApiKey` schema (the list-element shape, no plaintext) and a `ServiceApiKeyCreated` schema (the 201 shape, with plaintext); the five `/v1/tenants/{tid}/agents/{aid}/api-keys…` paths from R8; the new `mintkey:code` values from § "Error Codes"; the `AdminSettings.api_key` sub-object (mirror in ADR-0016.6).
2. THE Broker's `POST /v1/api-keys/resolve` is an internal service-to-service endpoint; it SHALL be documented in the Broker's contract notes but is not part of the public OpenAPI surface (consistent with other `svcid_*`-authenticated internal endpoints).
3. THE audit-event schema (`docs/architecture/contracts/events/audit-event.schema.json`) SHALL add event types `api_key.created`, `api_key.revoked`, `api_key.rotated`, and the `auth_method` / `api_key_id` / `key_fingerprint` fields on `proxy.hit`.
4. THE OTel span-attribute allowlist (`docs/architecture/contracts/events/span-attributes.md`) SHALL add `mintkey.auth_method` (enum value only; never the key or the fingerprint).
5. THE SQLAlchemy mirror (`packages/python/mintkey-models/mintkey_models/db.py`) SHALL be regenerated from the post-migration schema; the CI mirror-diff gate MUST pass. The corresponding Pydantic models (`ServiceApiKeyCreate`, `ServiceApiKey`, `ServiceApiKeyCreated`) SHALL be added to `mintkey-models`.
6. THE change-event schema (`docs/architecture/contracts/events/change-event.schema.json`) SHALL add the `api_key.revoked` event on `mintkey:agent`.
7. ALL CI parity gates (OpenAPI parity, SQLAlchemy mirror diff, JSON-Schema validity, `protoc` compile, Mermaid render) MUST pass on the post-feature tree.

### Requirement 12: No New MCP Surface

**User Story:** As an agent developer, I should see no change to the MCP tools — classical API keys are not for agents.

#### Acceptance Criteria

1. THE MCP `request_token`, `list_services`, `describe_service`, and `get_openapi` tools SHALL be unchanged by this feature.
2. Agents SHALL NOT be able to create, list, or use Service_API_Keys via MCP; classical API keys are operator-issued (Admin Console / Admin REST API) and used only by non-agent clients at the proxy's `/v1/call/...` route.
3. (Informational — a future, separate decision) `describe_service` MAY one day expose "this service accepts classical API keys" so an operator-facing tool can discover it; that is explicitly out of scope here.

## Non-Functional Requirements / Quality Attributes

- **Proxy hot path** — a Resolution_Cache **hit** adds only an in-memory lookup plus the same per-request action + constraint evaluation the brokered path already does; total added latency ≤ the brokered-JWT path (S-PERF-1 holds: ≤ 30 ms p99 added). A cache **miss** additionally incurs one Resolution_Endpoint roundtrip whose dominant cost is the Argon2id verify (~50–100 ms, by design — Argon2id is deliberately slow); with the default 60 s cache TTL each key incurs at most one such verify per minute regardless of request rate. This characteristic is documented for operators.
- **Resolution_Endpoint throughput** — Argon2id-bound; sized for ≥ 20 resolves/s/core with p99 ≤ 120 ms; the proxy cache keeps the *effective* resolve rate far below request rate. (If a deployment has many distinct high-rate API-key clients, raise `proxy_cache_ttl_seconds` or scale the Broker — a known, ordinary scaling lever.)
- **Revocation latency** — a revoked key (or a key whose bound agent is revoked) stops working within `min(5 s change-channel propagation, AdminSettings.api_key.proxy_cache_ttl_seconds)`.
- **Audit** — every API-key lifecycle event (`api_key.created` / `.revoked` / `.rotated`) and every classical-key `proxy.hit` is on the per-tenant hash chain; the chain-verification job (mintkey-mvp REQ-15) covers them with no special-casing.
- **No new long-running container** — this feature adds a Broker endpoint, a proxy code path + cache, Admin REST API endpoints, an AdminJS resource, and a Liquibase changeset; the 17-container compose count is unchanged.

## Out of Scope

- Agents requesting / using Service_API_Keys via MCP (operator-issued only in v1; agents use brokered JWTs).
- A dedicated "service-account" principal type (an identity that has API keys but no MCP key). In v1 a key binds to an existing Agent; the cosmetic wart that such an Agent also has an MCP key is noted as a future refinement (an `agent.mcp_enabled` flag).
- Per-key KMS keys / per-key encryption of the stored hash (the Argon2id hash is already not reversible; envelope-encrypting it is a 2.x concern, like the credential KEK).
- Federating externally-issued API keys (accepting a third party's key and mapping it to a Mintkey principal) — a different feature.
- Exact global rate limiting across proxy replicas for the `rate_limit` constraint (per-instance buckets in v1, as for permission-grant rate limits).
- The Option-A agent-refresh ergonomics (`request_token` `refresh_at`, `services.max_standard_ttl`) — tracked separately per `proposal/P-010` § "Outcome"; it does not belong in this spec.
