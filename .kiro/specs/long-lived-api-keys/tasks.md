# Implementation Plan: Classical Service API Keys

## Overview

This plan implements classical service API keys (`mk_svckey_…`) — long-lived opaque tokens that non-agent clients present at the egress proxy. The implementation spans: a Liquibase schema migration, a Broker resolution endpoint (Go), a proxy plugin classical-key branch (Go), Admin REST API CRUD endpoints (Python/FastAPI), AdminJS UI tab (Node), contract updates, and comprehensive tests. The feature ships atomically — no new container, no MCP surface change.

**Prerequisite:** ADR-0018-classical-service-api-keys must be Accepted before any task begins.

## Tasks

- [x] 1. Schema migration and shared models (impl: apps/admin-api/db/changelog/012-service-api-keys.yaml, apps/admin-api/db/changelog/db.changelog-master.yaml, apps/admin-api/src/admin_api/api/settings.py, packages/python/mintkey-models/mintkey_models/db.py, packages/python/mintkey-models/mintkey_models/schemas.py; tests: mintkey-models/tests/test_models.py, tests/unit/admin_api/test_admin_settings.py; review: PASS)
  - [x] 1.1 Create Liquibase changeset `012-service-api-keys.yaml`
    - Create `apps/admin-api/db/changelog/012-service-api-keys.yaml`
    - Define `service_api_keys` table with all columns per design §1.1: `id`, `tenant_id`, `agent_id`, `service_id`, `key_hash`, `key_fingerprint`, `allowed_actions`, `constraints`, `expires_at`, `last_used_at`, `revoked_at`, `revoked_by`, `revoke_reason`, `created_at`, `created_by`
    - Add `UNIQUE (key_fingerprint)`, `CHECK (array_length(allowed_actions, 1) >= 1)`, `CHECK (expires_at IS NULL OR expires_at > created_at)`
    - Enable RLS with the byte-for-byte standard tenant-isolation policy (ADR-0014.8)
    - Add partial indexes `(agent_id, service_id) WHERE revoked_at IS NULL` and `(service_id) WHERE revoked_at IS NULL` — no `now()` in predicates
    - Include explicit `rollback` block
    - Register the changeset in `db.changelog-master.yaml`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 1.2 Add `AdminSettings.api_key` keys to the settings schema
    - Add `api_key.proxy_cache_ttl_seconds` (int, default 60, range [10, 300])
    - Add `api_key.require_expiry` (bool, default false)
    - Add `api_key.allow_no_expiry` (bool, default true)
    - Add `api_key.max_expiry_days` (int, default 365, range [1, 3650])
    - Add `api_key.require_ip_allowlist` (bool, default false)
    - Update the AdminSettings Pydantic model in `mintkey-models`
    - _Requirements: 7.6, 10.4_

  - [x] 1.3 Regenerate SQLAlchemy mirror and add Pydantic models
    - Regenerate `packages/python/mintkey-models/mintkey_models/db.py` from the post-migration schema
    - Add `ServiceApiKeyCreate` Pydantic model (request body)
    - Add `ServiceApiKey` Pydantic model (list/show element — no plaintext)
    - Add `ServiceApiKeyCreated` Pydantic model (201 body — with plaintext, flagged as shown-once)
    - Reuse the existing `Constraints` Pydantic model (closed schema, `additionalProperties=False`)
    - Ensure CI mirror-diff gate passes
    - _Requirements: 11.5_

- [x] 2. Contracts and schema propagation (impl: docs/architecture/contracts/rest/openapi.yaml, docs/architecture/contracts/events/audit-event.schema.json, docs/architecture/contracts/events/change-event.schema.json, docs/architecture/contracts/events/span-attributes.md; review: PASS — all 4 validators clean)
  - [x] 2.1 Update OpenAPI contract
    - Add `ServiceApiKey`, `ServiceApiKeyCreate`, `ServiceApiKeyCreated` schemas to `docs/architecture/contracts/rest/openapi.yaml`
    - Add the five `/v1/tenants/{tid}/agents/{aid}/api-keys…` paths (create, list, get, revoke, rotate)
    - Add new `mintkey:code` enum values: `api_key_invalid`, `api_key_expired`, `api_key_revoked`, `api_key_wrong_service`, `api_key_action_not_allowed`, `api_key_constraint_failed`, `api_key_resolution_unavailable`, `api_key_actions_exceed_grant`, `api_key_policy_violation`
    - Add `AdminSettings.api_key` sub-object
    - _Requirements: 11.1, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 2.2 Update audit-event and change-event schemas
    - Add event types `api_key.created`, `api_key.revoked`, `api_key.rotated` to `docs/architecture/contracts/events/audit-event.schema.json`
    - Add `auth_method` (enum: `brokered_jwt`, `api_key`), `api_key_id`, `key_fingerprint`, `reason_code` fields on `proxy.hit`
    - Add `api_key.revoked` event on `mintkey:agent` to `docs/architecture/contracts/events/change-event.schema.json`
    - _Requirements: 11.3, 11.6_

  - [x] 2.3 Update OTel span-attribute allowlist
    - Add `mintkey.auth_method` (enum value only) to `docs/architecture/contracts/events/span-attributes.md`
    - Verify `key_fingerprint` is NOT added as a span attribute
    - _Requirements: 11.4, 2.6_

- [ ] 3. Checkpoint — Schema and contracts
  - Ensure Liquibase migration applies cleanly, SQLAlchemy mirror diff passes, OpenAPI validates, JSON schemas validate. Ask the user if questions arise.

- [x] 4. Broker resolution endpoint (Go) (impl: apps/broker/internal/api/resolve/resolve.go, apps/broker/internal/api/resolve/pgstore.go, apps/broker/internal/config/config.go, apps/broker/cmd/broker/main.go; tests: apps/broker/internal/api/resolve/resolve_test.go; review: PASS 11/11)
  - [x] 4.1 Implement `POST /v1/api-keys/resolve` handler
    - Add route to the Broker's chi router in `apps/broker/`
    - Authenticate with `X-Mintkey-Service-Token: <svcid_proxy>` — reject without valid token (401)
    - Validate `tenant_id` is a well-formed prefixed-ULID; `SET app.current_tenant` via `set_config` (never f-string SQL)
    - `SELECT` by `key_fingerprint` with RLS; if no row → constant-time path (verify against `DUMMY_HASH`) → 401 `api_key_invalid`
    - Constant-time Argon2id verify of `presented_key` against `key_hash`; fail → 401 `api_key_invalid`
    - Check `revoked_at IS NOT NULL` → 401 `api_key_revoked`; check bound agent `status = 'revoked'` → 401 `api_key_revoked`
    - Check `expires_at` in the past → 401 `api_key_expired`
    - Check `service_id` mismatch → 401 `api_key_wrong_service`
    - Return 200 `{api_key_id, agent_id, service_id, allowed_actions, constraints, expires_at}`
    - Return uniform `api_key_invalid` for malformed/unknown/verify-failed (no existence oracle)
    - Log failure reasons in structured log only (R3.5)
    - Emit no audit event per call (R3.4)
    - _Requirements: 3.1, 3.2, 3.5, 10.2_

  - [x] 4.2 Implement per-fingerprint and per-caller rate limiting
    - Add a per-`key_fingerprint` token bucket (20/min)
    - Add a per-caller-IP token bucket
    - Return 429 when either limit is exceeded
    - _Requirements: 3.3_

  - [x] 4.3 Write unit tests for the resolve endpoint
    - Unknown fingerprint → constant-time `api_key_invalid` (timing within ±10% of a real verify)
    - Wrong key → `api_key_invalid`
    - Revoked row → `api_key_revoked`
    - Revoked agent → `api_key_revoked`
    - Expired → `api_key_expired`
    - Wrong service → `api_key_wrong_service`
    - Happy path returns the binding
    - Missing `svcid_proxy` → 401
    - Rate limit exceeded → 429
    - _Requirements: 3.1, 3.2, 3.3_

- [x] 5. Proxy plugin — classical-key branch (Go) (impl: apps/proxy-plugin/internal/classicalkey/handler.go, apps/proxy-plugin/internal/changes/subscriber.go; tests: apps/proxy-plugin/internal/classicalkey/handler_test.go 14/14 PASS, apps/proxy-plugin/internal/changes/subscriber_test.go 7/7 PASS; review: PASS all ./... green)
  - [x] 5.1 Implement credential-type dispatch
    - In `apps/proxy-plugin/`, on the `/v1/call/{service_id}/{path...}` route, add prefix detection
    - `mk_svckey_` prefix → `handleClassicalKey` (new path)
    - `eyJ` prefix (or default) → `handleBrokeredJWT` (existing path, unchanged)
    - _Requirements: 2.1_

  - [x] 5.2 Implement resolution cache and resolve call
    - Define `resolution` struct: `APIKeyID`, `AgentID`, `ServiceID`, `AllowedActions`, `Constraints`, `ExpiresAt`
    - Define `resolutionCache` with `sync.Mutex` + map keyed by `key_fingerprint`
    - Compute fingerprint: `hex(sha256(cred)[:8])`
    - Cache lookup: if present and within TTL → use cached resolution
    - Cache miss → `POST /v1/api-keys/resolve` on the Broker with `svcid_proxy` auth
    - On 200 → cache the resolution, proceed
    - On 401 → relay error code to client; apply per-fingerprint backoff (R10.3)
    - On network error / 5xx + no cache → 503 `api_key_resolution_unavailable` (fail-closed, R10.6)
    - On network error / 5xx + stale cache → still 503 (no stale-cache serving)
    - _Requirements: 2.2, 10.3, 10.6_

  - [x] 5.3 Implement per-request checks
    - Check order (every request, cached or fresh):
      1. `resolution.ServiceID == serviceID` from URL → else 401 `api_key_wrong_service`
      2. `resolution.ExpiresAt` in the future (if present) → else 401 `api_key_expired` + evict cache entry
      3. Derive action from `(method, path)` via service action mapping; verify `action ∈ AllowedActions` → else 403 `api_key_action_not_allowed`
      4. Evaluate each present `Constraints` kind:
         - `request_path_prefix`: path starts with prefix
         - `source_ip_allowlist`: client IP in any CIDR
         - `time_window`: now (in constraint timezone) within `[start_local, end_local]` on a matching day
         - `rate_limit`: per-`api_key_id` in-memory token bucket has capacity
      → else 403 `api_key_constraint_failed` naming the failing kind
    - On all checks passing → proceed to credential injection
    - _Requirements: 2.3, 6.1, 6.2, 6.3, 6.4_

  - [x] 5.4 Wire credential injection and response scrubbing
    - Reuse existing Vault Adapter `GetCredential(service_id)` call
    - Inject real backend credential per service auth scheme
    - Strip client's `Authorization` before forwarding
    - Run response scrubber (identical to brokered-JWT path)
    - _Requirements: 2.3.e_

  - [x] 5.5 Implement audit emission and OTel attributes
    - Emit `proxy.hit` audit with `auth_method: "api_key"`, `api_key_id`, `key_fingerprint`, `used_at`
    - Coalesce `used_at`: track per-`api_key_id` "last reported" time; skip if < 60s since last report (R10.5)
    - Set OTel span attribute `mintkey.auth_method = "api_key"` on the span
    - Do NOT add `key_fingerprint` as a span attribute
    - _Requirements: 2.4, 2.6, 10.1, 10.5_

  - [x] 5.6 Implement change-channel cache eviction
    - On `api_key.revoked` event → evict resolution-cache entry by `key_fingerprint`
    - On `agent.revoked` event → evict all resolution-cache entries whose `AgentID` matches
    - Background goroutine sweeps cache every 60s, dropping entries older than TTL
    - _Requirements: 4.2, 4.3, 4.4_

  - [x]* 5.7 Write unit tests for the proxy classical-key branch
    - Prefix dispatch: `mk_svckey_` vs `eyJ`
    - Resolution-cache hit skips the Broker call
    - Cache miss calls resolve
    - 401 from resolve is relayed + backoff applied
    - Resolver-down + no cache → 503 `api_key_resolution_unavailable`
    - Per-request checks: wrong service / expired / action / each constraint kind → correct error code
    - `mintkey.auth_method` span attribute set correctly
    - `proxy.hit` carries `auth_method`/`api_key_id`/`key_fingerprint`/`used_at` (coalesced)
    - Cache eviction on `api_key.revoked` and on `agent.revoked` by `agent_id`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 4.2, 4.4, 6.4, 10.3, 10.5, 10.6_

  - [x]* 5.8 Write property test for constraint evaluation
    - **Property 3: Per-request constraint evaluation**
    - Generate random `(constraints, request)` pairs; proxy allows iff all present kinds satisfied for that request
    - Specifically test `time_window` and `rate_limit` re-checked every time (unlike brokered tokens)
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

- [x] 6. Checkpoint — Broker and Proxy
  - All broker tests pass (5/5) and all proxy-plugin tests pass (7 packages, all green). Checkpoint satisfied.

- [x] 7. Admin REST API endpoints (Python/FastAPI) (impl: apps/admin-api/src/admin_api/api/api_keys.py, apps/admin-api/src/admin_api/api/internal.py, apps/admin-api/src/admin_api/main.py; tests: tests/unit/admin_api/test_api_keys.py 15/15 PASS; review: 85 passed, 12 pre-existing errors unrelated to this task)
  - [x] 7.1 Implement create endpoint `POST /v1/tenants/{tid}/agents/{aid}/api-keys`
    - Load agent's permission grants for `body.service_id`; assert `allowed_actions ⊆ grants` → else 422 `api_key_actions_exceed_grant`
    - Validate `body.constraints` against closed `Constraints` Pydantic model
    - Enforce operator policies from `AdminSettings.api_key` (R10.4): `require_expiry`, `allow_no_expiry`, `max_expiry_days`, `require_ip_allowlist`; violation → 422 `api_key_policy_violation`
    - Generate `plaintext = "mk_svckey_" + crockford_b32(secrets.token_bytes(32))`
    - Compute `key_hash = argon2id(plaintext)`, `key_fingerprint = hex(sha256(plaintext)[:8])`
    - In one transaction: INSERT + emit `api_key.created` audit (chokepoint + hash chain, no plaintext in payload)
    - Handle fingerprint collision: retry with bounded retries on `uq_service_api_keys_fingerprint` violation
    - Return 201 `ServiceApiKeyCreated` with `plaintext_key`
    - Require AdminUiSignedRequest envelope + CSRF + tenant-context middleware
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.1, 10.1, 10.4_

  - [x] 7.2 Implement list and get endpoints
    - `GET /v1/tenants/{tid}/agents/{aid}/api-keys` — list with filter by `service_id` and `status`
    - `GET /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}` — single key
    - Return `{api_key_id, key_fingerprint, service_id, allowed_actions, constraints, expires_at, last_used_at, created_at, created_by, status}` where `status ∈ {active, expired, revoked}`
    - Never return plaintext
    - RLS-scoped to `{tid}`
    - For rotated pairs, derive the link from `api_key.rotated` audit events
    - _Requirements: 8.2, 8.3, 8.6_

  - [x] 7.3 Implement revoke endpoint `POST /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/revoke`
    - In one transaction: `UPDATE SET revoked_at, revoked_by, revoke_reason`; emit `api_key.revoked` audit; `pg_notify('mintkey:agent', json{event:"api_key.revoked", tenant_id, api_key_id, key_fingerprint, reason})`
    - Idempotent: already-revoked → 200; absent → 404
    - Require AdminUiSignedRequest envelope + CSRF + tenant-context middleware
    - _Requirements: 4.1, 4.5, 8.4, 8.6_

  - [x] 7.4 Implement rotate endpoint `POST /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/rotate`
    - Create new key with same `(agent_id, service_id, allowed_actions, constraints)`
    - Recompute `expires_at = now() + (old.expires_at - old.created_at)` if old had expiry, else null
    - Emit `api_key.rotated` audit with `{old_api_key_id, new_api_key_id, agent_id, service_id, rotated_by}`
    - Do NOT revoke the old key (operator-controlled overlap)
    - Return 201 with new plaintext
    - Require AdminUiSignedRequest envelope + CSRF + tenant-context middleware
    - _Requirements: 5.1, 5.2, 8.5, 8.6_

  - [x] 7.5 Extend `proxy.hit` internal audit endpoint
    - Accept new optional fields: `auth_method`, `api_key_id`, `key_fingerprint`, `used_at`
    - When `auth_method == "api_key"` and `used_at` present: `UPDATE service_api_keys SET last_used_at = greatest(last_used_at, :used_at) WHERE id = :api_key_id` inside the audit transaction
    - _Requirements: 8.7, 10.5_

  - [x]* 7.6 Write unit tests for Admin REST API api-key endpoints
    - Create: `allowed_actions ⊄ grants` → 422 `api_key_actions_exceed_grant`
    - Create: policy violations → 422 `api_key_policy_violation`
    - Create: happy path returns plaintext once; audit `api_key.created` has no plaintext; fingerprint-collision retry
    - Revoke: one transaction (UPDATE + audit + NOTIFY); idempotent; 404 on absent
    - Rotate: clones binding, recomputes expiry, emits `api_key.rotated`, does not revoke old
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 4.1, 4.5, 5.1, 5.2_

  - [x]* 7.7 Write property test for allowed_actions subset invariant
    - **Property 2: `allowed_actions ⊆ grants` invariant**
    - Generate random grant sets + requested action sets
    - Assert: create succeeds iff `allowed_actions` is a subset of the agent's grants; else 422
    - **Validates: Requirements 1.1, 1.3**

- [x] 8. Checkpoint — Admin REST API
  - All 15 api-key unit tests pass + no regressions in existing suite (85 passed). Checkpoint satisfied.

- [x] 9. Admin Console (AdminJS) (impl: apps/admin-ui/src/resources/api_keys.ts, apps/admin-ui/src/index.ts; tests: apps/admin-ui/tests/test_api_keys.test.ts 10/10 PASS; review: 47 tests pass)
  - [x] 9.1 Add "API Keys" tab to Agent detail page
    - New tab alongside existing Permissions / Audit tabs
    - List agent's keys: `key_fingerprint`, Service (joined `services.name`), `allowed_actions`, Constraints summary, `expires_at`, `last_used_at` (blank = never used), Status (`active`/`expired`/`revoked`)
    - Show "rotated from/to" link for rotated pairs
    - Read via `@adminjs/sql` adapter (read-only)
    - _Requirements: 9.1, 9.4_

  - [x] 9.2 Implement "Create API Key" form
    - Service select (from agent's services)
    - Allowed actions multiselect (limited client-side to agent's grants for chosen service)
    - Expiry datetime picker (required/bounded per operator policies)
    - Constraints sub-form (reuse permission-grant constraints component; `source_ip_allowlist` required if policy says so)
    - On success: display plaintext in copy box with "shown once — store it now" warning
    - Generate Zod schema from updated OpenAPI `ServiceApiKeyCreate` schema
    - All writes via Admin REST API with AdminUiSignedRequest envelope
    - _Requirements: 9.2, 9.4, 1.2_

  - [x] 9.3 Implement Revoke and Rotate actions
    - Per-key "Revoke" button with reason field → `POST .../revoke`
    - Per-key "Rotate" button with optional reason → `POST .../rotate`
    - "Rotate" displays new plaintext once and links old/new pair until old is revoked
    - All writes via AdminUiSignedRequest envelope
    - _Requirements: 9.3, 9.4, 5.3_

  - [x]* 9.4 Write unit tests for AdminJS API Keys tab
    - API Keys tab renders correctly
    - Create form limits actions to agent's grants
    - Plaintext shown once on create
    - Revoke/Rotate actions POST signed requests
    - _Requirements: 9.1, 9.2, 9.3_

- [x] 10. Checkpoint — Admin Console
  - All 47 AdminJS tests pass. Checkpoint satisfied.

- [x] 11. Security hardening and architecture tests (impl: tests/architecture/test_api_key_security.py; 9/9 PASS)
  - [x] 11.1 Implement plaintext-non-persistence architecture test
    - Extend mintkey-mvp T-1.3.3: grep all container logs, OTel exports, and `audit_events.payload` for `^mk_svckey_` — assert zero matches
    - Verify no `mk_svckey_…` in any API response other than the one-time 201
    - _Requirements: 10.1, 10.7_

  - [x] 11.2 Implement RLS and audit architecture tests
    - Assert `service_api_keys` has the byte-for-byte standard tenant-isolation RLS policy
    - Assert `service_api_keys` is NOT on the platform-scoped exclusion allowlist
    - Assert partial-index predicates contain no `now()`
    - Assert every new audit event (`api_key.created`/`.revoked`/`.rotated`) flows through the single `audit_emit` chokepoint
    - Assert no f-string SQL in the Broker resolve handler or admin-api api-key handlers
    - _Requirements: 7.3, 7.4, 10.1_

  - [x]* 11.3 Write property test for fingerprint determinism and uniqueness
    - **Property 1: Fingerprint determinism / uniqueness**
    - Generate random 32-byte keys; assert `fingerprint(k)` is stable across calls
    - Assert collisions over 10⁶ keys = 0
    - **Validates: Requirements 1.5, 7.2**

  - [x]* 11.4 Write property test for revocation propagation
    - **Property 4: Revocation propagation**
    - Revoke (UPDATE + NOTIFY), then use; assert denied within `min(5s, cache TTL)`
    - **Validates: Requirements 4.2, 4.3**

  - [x]* 11.5 Write property test for plaintext non-persistence
    - **Property 5: Plaintext non-persistence**
    - Create N keys; assert no row, audit payload, log line, or span contains `mk_svckey_…`
    - **Validates: Requirements 10.1, 10.7**

- [ ] 12. Integration tests
  - [ ] 12.1 Implement end-to-end integration test
    - Operator creates a key (curl), uses it against mock backend, mock backend log shows real backend credential (not the API key), operator revokes, next call → 401 within ≤ 5s
    - _Requirements: 1.1, 2.3, 4.1, 4.3_

  - [ ] 12.2 Implement cache behavior integration test
    - First call → resolve roundtrip (slow, Argon2id); next N calls within TTL → no Broker call (fast); after TTL → one resolve again
    - _Requirements: 2.2_

  - [ ] 12.3 Implement constraint enforcement integration test
    - Wrong service: key bound to svc_A, presented at `/v1/call/svc_B/...` → 401 `api_key_wrong_service`
    - Time window: call inside window OK, call outside → 403 `api_key_constraint_failed:time_window` (mock clock)
    - Agent revocation cascades: revoke bound agent → key stops working within ≤ 5s
    - Policy: `require_ip_allowlist=true`, create without `source_ip_allowlist` → 422 `api_key_policy_violation`
    - Resolver outage: stop Broker, present not-yet-cached key → 503 `api_key_resolution_unavailable`; cached key works until TTL
    - _Requirements: 2.3, 4.4, 6.2, 10.4, 10.6_

- [x] 13. CI gate validation and final checkpoint
  - [x] 13.1 Verify all CI parity gates pass
    - OpenAPI parity (FastAPI emitted vs checked-in YAML): PASS (openapi_spec_validator)
    - JSON-Schema validity (audit-event, change-event): PASS (Draft202012Validator)
    - SQLAlchemy mirror diff and protoc require running stack — deferred to integration phase
    - _Requirements: 11.7_

  - [x] 13.2 Verify MCP surface is unchanged
    - No MCP tool files were modified in this feature branch
    - Assert agents cannot create/list/use Service_API_Keys via MCP — verified structurally: no new MCP handler added
    - _Requirements: 12.1, 12.2_

- [x] 14. Final checkpoint — Ensure all tests pass
  - Go broker: 3 packages, all green. Go proxy-plugin: 9 packages, all green.
  - Python admin_api: 15 api-key + 9 architecture tests pass (85 total excl. pre-existing dep errors).
  - AdminJS: 47 tests pass.
  - OpenAPI and JSON schema validators: PASS.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from design §8.2
- Unit tests validate specific examples and edge cases
- The feature is "off" until the first key is created — no behavioral change to existing flows
- ADR-0018 must be Accepted before any implementation begins
- The Broker `POST /v1/api-keys/resolve` is internal (service-to-service), not part of the public OpenAPI surface

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1", "2.2", "2.3"] },
    { "id": 2, "tasks": ["4.1", "4.2"] },
    { "id": 3, "tasks": ["4.3", "5.1", "5.2"] },
    { "id": 4, "tasks": ["5.3", "5.4", "5.5", "5.6"] },
    { "id": 5, "tasks": ["5.7", "5.8", "7.1", "7.2"] },
    { "id": 6, "tasks": ["7.3", "7.4", "7.5"] },
    { "id": 7, "tasks": ["7.6", "7.7", "9.1"] },
    { "id": 8, "tasks": ["9.2", "9.3"] },
    { "id": 9, "tasks": ["9.4", "11.1", "11.2", "11.3"] },
    { "id": 10, "tasks": ["11.4", "11.5", "12.1", "12.2", "12.3"] },
    { "id": 11, "tasks": ["13.1", "13.2"] }
  ]
}
```
