# Mintkey MVP — Phase 1 Requirements

**Feature:** mintkey-mvp
**Phase:** 1 — Usable Product
**Sources:**
- `docs/architecture/00-vision/06-roadmap.md` — phases, milestones, scope
- `docs/architecture/01-architecture/03-quality-attributes.md` — `S-*-*` quality attribute scenarios
- `docs/architecture/01-architecture/05-threat-model.md`
- `docs/architecture/01-architecture/open-questions.md` — deferred items (`OQ-NNN`)
- `docs/architecture/03-flows/E2E-01-builder-happy-path.md` and the F-OP / F-AG flow set
- `docs/architecture/contracts/` — REST OpenAPI, MCP tools, audit-event and change-event JSON schemas, span attributes, `vault.proto`
- ADRs **0001 through 0017**, all Accepted (canonical at [`docs/architecture/01-architecture/adr/`](../../../docs/architecture/01-architecture/adr/))

---

## Introduction

Mintkey Phase 1 delivers a self‑hostable agentic credential broker that an operator can run with `docker compose up`. The operator registers services and credentials, creates agents, grants permissions, and an agent can discover services via MCP, receive a scoped short‑lived JWT, and call backends through an egress proxy that injects the real credential — which the agent never sees. Every step is audited (with mandatory hash chain) and observable end‑to‑end via OpenTelemetry.

The MVP is complete when the **E2E‑01 builder happy path** runs in CI **after** `docker compose up` reports healthy and **completes within ≤ 90 seconds** with no manual steps. Total CI gate envelope: 120 s compose start‑up + 90 s smoke test = **≤ 210 s** end to end ([S‑TEST‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)).

---

## Glossary

| Term | Definition |
|---|---|
| **Tenant** | An isolated namespace. Default deployment has one tenant with slug `t_default`. |
| **Operator** | A human user of the Admin Console. RBAC roles: `Admin`, `Auditor`, `AgentOwner`. `PlatformAdmin` is a separate boolean column on `Operator` that grants cross‑tenant scope (ADR‑0008). |
| **Agent** | An autonomous AI process that calls backend services through Mintkey. Identified by an `agent_…` ULID; authenticates with an `mk_agent_…` Agent API Key. |
| **Service** | A registered backend API (base URL + auth scheme + optional OpenAPI URL). Identified by `svc_…` ULID. |
| **Credential** | The real secret (API key, bearer token, basic auth, mTLS cert+key, OAuth client, OIDC client secret) stored encrypted in the Vault Adapter. |
| **Permission Grant** | A record binding `(agent, service, action)` with an optional **closed `Constraints` schema** — `rate_limit`, `time_window`, `request_path_prefix`, `source_ip_allowlist` (ADR‑0016.4). |
| **JWT / Brokered Token** | A JWS Ed25519 JWT issued by the Credential Broker. Short‑lived; claims `iss`, `sub`, `aud`, `tnt` (tenant **ULID with prefix**, never a slug — ADR‑0008 / ADR‑0017.11), `scope`, `jti`, `iat`, `exp`, optional `cnf.jkt`, optional `kid`. |
| **KEK** | Key Encryption Key — encrypts the per‑credential DEKs. Loaded from a keyfile at startup; never from an environment variable in production. |
| **DEK** | Data Encryption Key — unique per credential, encrypted with the KEK, stored alongside ciphertext. |
| **Change Channel** | Postgres `LISTEN/NOTIFY` on **global channels** `mintkey:service`, `mintkey:credential`, `mintkey:agent`, `mintkey:heartbeat` (ADR‑0014.1). Tenant filtering is enforced by subscribers at the application layer using `tenant_id` in the payload. |
| **`jti` denylist** | Postgres table `admin_request_jti` of recently‑seen `jti` values from AdminJS↔FastAPI signed requests, used to prevent replay across FastAPI replicas (ADR‑0016.1). |
| **Service Identity** | Per‑service boot secret (`svcid_admin_api`, `svcid_mcp`, `svcid_broker`, `svcid_proxy`) used by control‑plane services to authenticate to the Vault Adapter, per ADR‑0014.2. Argon2id‑hashed at rest. |
| **Audit Hash Chain** | Mandatory per‑tenant audit chain (ADR‑0014.7). Every `audit_events` row stores `prev_hash` + `hash`. Genesis: `sha256("mintkey-audit-genesis-v1:" || tenant_id)`. |
| **AdminUiSignedRequest** | Ed25519 JWT signed by AdminJS on every state‑changing call to `admin-api` (ADR‑0014.6). Carries `iss="mintkey/admin-ui"`, `sub`, `tnt`, `aud="mintkey/admin-api"`, `iat`, `exp` (60 s), `jti`. |

---

## Requirement 1: Foundation Skeleton (Milestone 1.0)

**User Story:** As an operator, I want all Mintkey containers to start cleanly from `docker compose up` so that I have a working baseline to build on.

### Acceptance Criteria

1. WHEN `docker compose up` is run on a clean machine with Docker installed, THEN the **15 long‑running containers** (`postgres`, `keycloak`, `admin-api`, `admin-ui` (AdminJS), `mcp`, `broker`, `vault-adapter`, `kong`, `proxy-plugin`, `kong-syncer`, `demo-backend`, `otel-collector`, `jaeger`, `prometheus`, `grafana`) reach a healthy state within **≤ 120 seconds**, and the **2 one‑shot jobs** (`liquibase`, `seed-job`) exit `0` before `admin-api` starts.
2. WHEN Liquibase runs as a one‑shot job, THEN it applies all changelogs successfully and exits `0`. The Liquibase migration role is `mintkey_migrate`; the application role `mintkey_app` and the subscriber role `mintkey_subscriber` are created with appropriate grants.
3. WHEN Liquibase migrations complete, THEN every domain table — `tenants`, `operators`, `operator_tenant_memberships`, `agents`, `services`, `credentials`, `permission_grants`, `audit_events`, `admin_request_jti`, `service_identities`, `sessions`, `audit_chain_state`, `tenant_settings` — exists. Every **tenant‑scoped** table carries `tenant_id UUID NOT NULL`. (`admin_request_jti`, `audit_chain_state`, and `service_identities` are platform‑scoped and excluded from the tenant‑scoped requirement; the architecture test's allowlist names them explicitly.)
4. WHEN Liquibase migrations complete, THEN every tenant‑scoped table has a Postgres Row Level Security policy whose `qual` evaluates to:
   ```sql
   tenant_id = current_setting('app.current_tenant', true)::uuid
   OR current_setting('app.platform_admin_view', true) = 'on'
   ```
   The `OR` clause is the `PlatformAdmin` escape per ADR‑0016.3. RLS is enabled on every tenant‑scoped table.
5. WHEN the seed job runs, THEN it performs all of the following in order, idempotently:
   1. Creates the default tenant with slug `t_default` and `isolation_mode='row'`.
   2. Generates a 32‑byte random bootstrap admin password and creates the bootstrap operator with `role=Admin`, Argon2id‑hashed password, and an `OperatorTenantMembership` to `t_default`.
   3. Imports the Keycloak realm `mintkey` from `realm-mintkey.json`, including the `mintkey-admin` confidential OIDC client.
   4. Generates the per‑service‑identity boot secrets (`svcid_admin_api`, `svcid_mcp`, `svcid_broker`, `svcid_proxy`) — random 32‑byte tokens, Argon2id‑hashed into `service_identities`, plaintext into the host file (mode `0400`).
   5. Generates an Ed25519 keypair for AdminJS and stores the **public key** in the Vault Adapter under credential type `admin_ui_signing_key` (the private key is mounted into the AdminJS container).
   6. Generates an Ed25519 keypair for the broker and stores the **private key** in the Vault Adapter under credential type `signing_key`. Publishes the public key in the JWKS surface.
   7. Initializes the per‑tenant `audit_chain_state` row (genesis hash) for `t_default`.
6. WHEN the seed job completes, THEN it writes (a) the bootstrap admin password, (b) all service‑identity tokens, (c) the AdminJS private key path, to `./data/bootstrap-secrets/*` with file mode `0400` and ownership of the service user; the admin password is also printed once to stdout for operator capture; rerunning the seed job without `--rotate-bootstrap` is a no‑op.
7. WHEN `GET /v1/health` is called on `admin-api`, THEN it returns `200 OK` with `{"status": "ok"}` (liveness only — no dependency checks).
8. WHEN `GET /v1/ready` is called on `admin-api`, THEN it returns `200 OK` only after **DB connectivity**, **Liquibase completion**, **Vault Adapter reachability** (gRPC ping), and **change‑channel listener attachment** are all confirmed; otherwise `503 Service Unavailable` with `mintkey:code=not_ready` and a list of failing checks.
9. WHEN the OTel Collector starts, THEN it accepts OTLP on port `4317` (gRPC) and fans out traces to Jaeger and metrics to Prometheus without data loss under steady‑state load (≤ 100 RPS).
10. WHEN AdminJS starts, THEN it connects to `admin-api`, fetches the operator's identity via `GET /v1/auth/whoami`, and renders the dashboard's empty‑state markup for services, agents, and credentials (HTTP 200; empty‑state DOM elements present).
11. WHEN an **architecture test** runs in CI, THEN it asserts (a) 100% of tenant‑scoped tables have an RLS policy, (b) **no policy has `qual = 'true'` or any other no‑op form** (per ADR‑0014.8), and (c) the policy references `current_setting('app.current_tenant')` for the canonical clause and `app.platform_admin_view` for the escape.
12. WHEN the seed job completes successfully, THEN an audit event `tenant.bootstrap_completed` is emitted to the audit chain for `t_default` with payload `{slug, isolation_mode, initial_admin_operator_id}`. The chain's first entry has `prev_hash = sha256("mintkey-audit-genesis-v1:" || tenant_id)`.

---

## Requirement 2: Operator Login (Milestone 1.1)

**User Story:** As an operator, I want to log in to the Admin Console so that I can manage services, agents, and credentials.

### Acceptance Criteria

1. WHEN an operator navigates to the Admin Console URL without a valid session cookie, THEN they are redirected to `/login`.
2. WHEN an operator chooses "Internal auth" and submits valid bootstrap credentials, THEN `admin-api` verifies the Argon2id hash, creates a server‑side session row in `sessions`, sets `mintkey_session` cookie with `HttpOnly; Secure; SameSite=Strict`, and redirects to the dashboard.
3. WHEN an operator submits invalid credentials (unknown user, wrong password, **or** locked account), THEN the response body is **byte‑identical** across the three failure modes (HTTP 401, JSON `{"type": "...", "title": "Invalid credentials", "status": 401, "mintkey:code": "invalid_credentials"}`), and the **time‑to‑respond is statistically indistinguishable** across all three modes (server always runs an Argon2id verify against a fixed dummy hash if the user record is missing). Per ADR‑0017.5.
4. WHEN an internal‑login attempt fails, THEN the audit chain records ONE of:
   - `auth.login.failed.user_unknown`
   - `auth.login.failed.bad_password`
   - `auth.login.failed.account_locked`
   …with `username_attempted` (truncated to 200 chars), `ip`, `user_agent`, `at`, and the appropriate `reason_code`. The API response itself does **not** distinguish between them.
5. WHEN an operator logs in successfully (internal or OIDC), THEN an audit event `auth.login.success` is emitted with `operator_id`, `tenant_id`, `ip`, `user_agent`, `method` (`internal` or `oidc`), and `at`.
6. WHEN an operator chooses "Login with Keycloak" and completes the OIDC flow with PKCE, THEN `admin-api` validates the `state`, `nonce`, and ID‑token signature, looks up the operator by `oidc_sub` (or `email` if `link_by_email = true`), creates a session, and redirects to the dashboard. If no matching operator exists and auto‑provisioning is disabled (default), the response is `403` with audit `auth.login.denied.no_local_operator`.
7. WHEN a session cookie is missing or invalid on a protected Admin REST API endpoint, THEN the response is `401 unauthenticated`.
8. WHEN an operator logs out, THEN the `sessions` row is invalidated, the cookie is cleared, and an audit event `auth.logout` is emitted. If OIDC was used, the response includes a Keycloak end‑session redirect URL.
9. WHEN a state‑changing request arrives at AdminJS, THEN AdminJS:
   1. **Does not** write to the DB directly.
   2. Forwards the request to `admin-api` as an HTTP call carrying an **`AdminUiSignedRequest`** Ed25519 JWT (per ADR‑0014.6) in the `Authorization` header.
   3. The JWT carries the operator's session-derived `sub`, `tnt`, `iat`, `exp` (60 s), and a fresh `jti` (UUID).
10. WHEN `admin-api` receives a state‑changing request from AdminJS, THEN it validates the JWT signature against the AdminJS public key (fetched from the Vault Adapter at startup, refreshed hourly with force‑refresh on signature‑verify failure), **inserts the `jti` into `admin_request_jti`** (UNIQUE constraint; conflict ⇒ replay rejected with 401 `replay_detected`), and proceeds.
11. WHEN a state‑changing browser‑originated `POST`/`PUT`/`PATCH`/`DELETE` arrives without a valid `X-Mintkey-Csrf` header, THEN `admin-api` returns `403` with `mintkey:code=csrf_required`.
12. WHEN repeated failed internal‑login attempts hit the same `username_attempted` (≥ 10 within 5 minutes), THEN the account is temporarily locked for 15 minutes; the response remains body‑identical and time‑equalized to other failure modes (per AC #3).

---

## Requirement 3: Service Registration (Milestone 1.2)

**User Story:** As an operator, I want to register backend services so that agents can discover and call them through Mintkey.

### Acceptance Criteria

1. WHEN an operator submits a valid service registration (`name`, `display_name`, `base_url`, `auth_scheme`, optional `description`, optional `openapi_url`), THEN `admin-api` inserts a row in `services` with a ULID‑prefixed ID `svc_…`, `tenant_id` from the active session, `current_key_version=0`, and `status=active`. Response is `201 Created` with the full `Service` schema.
2. WHEN a service is registered, THEN an audit event `service.registered` is emitted with `service_id`, `tenant_id`, `operator_id`, `name`, `display_name`, `base_url`, `auth_scheme`, `openapi_url`, `at`. The audit row carries `prev_hash` + `hash` per the per‑tenant chain.
3. WHEN a service is registered, THEN `admin-api` publishes `NOTIFY mintkey:service` (the **global** channel per ADR‑0014.1) with payload `{event_id, event_type: "service.registered", tenant_id, actor_id, target_id: svc_…, at}` **inside the same DB transaction** as the INSERT and the audit emission.
4. WHEN the Kong‑syncer receives a `service.registered` notification (filtered to its configured tenant set; `[ALL_TENANTS]` for the default deployment), THEN it pushes updated declarative YAML to Kong's `/config` endpoint within ≤ 5 seconds.
5. WHEN the MCP Server receives a `service.registered` notification (filtered by its tenant set), THEN it invalidates its discovery cache for that tenant.
6. WHEN an operator provides a non‑empty `openapi_url`, THEN it is stored, validated for HTTPS (HTTP rejected outside dev mode), and returned by `describe_service` and `list_services`.
7. WHEN an operator lists services via `GET /v1/services` or `GET /v1/tenants/{tid}/services`, THEN only services whose `tenant_id` matches the active session's tenant are returned (RLS enforced; non‑matching IDs in the URL respond `404`).
8. WHEN an operator updates a service via `PATCH`, THEN an audit event `service.updated` is emitted with `fields_changed`, the change channel is notified.
9. WHEN an operator deletes a service via `DELETE`, THEN the row is **soft‑deleted** (`status='deleted'`), an audit event `service.removed` is emitted, the change channel is notified, and Kong‑syncer removes the route from Kong on next push.
10. WHEN a `base_url` resolves to an RFC1918, link‑local, loopback, or cloud‑metadata IP (`169.254.169.254`, etc.), THEN `admin-api` rejects the registration with `422` and `mintkey:code=forbidden_destination` unless the service explicitly opts in to internal hosts (per ADR‑0007). Resolution is performed at registration time and re‑validated at each test run.
11. WHEN a service registration is attempted with a `(tenant_id, name)` that already exists, THEN `admin-api` returns `409 Conflict` with `mintkey:code=service_name_taken`.
12. WHEN an operator without `AgentOwner+` role attempts to register a service, THEN `admin-api` returns `403 permission_denied` with an audit event `auth.access.denied`.

---

## Requirement 4: Credential Registration and Test (Milestone 1.3)

**User Story:** As an operator, I want to register credentials for a service and verify they work — without ever seeing the credential plaintext after submission — so that agents can make authenticated calls.

### Acceptance Criteria

1. WHEN an operator submits a credential (value + `auth_scheme` matching the service's), THEN `admin-api` calls the Vault Adapter's `PutCredential` gRPC. The call carries the **service identity** boot secret (`X-Mintkey-Service-Token`, ADR‑0014.2) so the Vault Adapter authenticates the caller; the request payload is `(tenant_id, service_id, plaintext, auth_scheme)`. The Vault Adapter assigns `key_version = current + 1`.
2. WHEN the Vault Adapter stores a credential, THEN it (a) generates a fresh 256‑bit DEK, (b) AES‑256‑GCM encrypts the plaintext + a fresh 96‑bit nonce, (c) wraps the DEK with the KEK, (d) stores `(tenant_id, service_id, key_version, ciphertext, nonce, wrapped_dek, auth_scheme, created_at)` in the SQLite file. The plaintext is never written to disk and is zeroed from process memory after the encrypt step.
3. WHEN the Vault Adapter starts, THEN it loads the KEK **from the keyfile path** configured at startup (`MINTKEY_VAULT_KEK_FILE`); the env‑var fallback (`MINTKEY_VAULT_KEK`) is rejected with a startup error in production mode.
4. WHEN a credential is stored, THEN an audit event `credential.registered` (or `credential.rotated` if `key_version > 1`) is emitted with `credential_id`, `service_id`, `tenant_id`, `key_version`, `auth_scheme`, `operator_id`, `at`. The plaintext value MUST NOT appear in the audit payload, in any log, or in any OTel span attribute.
5. WHEN an operator clicks "Test" on a service, THEN AdminJS calls `POST /v1/tenants/{tid}/services/{sid}/test` with body `{method, path, timeout_ms, body?}` (defaults `GET`, `/health`, `5000` ms). `admin-api`:
   1. Enforces a per‑service rate limit (default: 10 requests / minute / service).
   2. Re‑validates the destination against the egress allowlist (per AC 3.10).
   3. Calls the Vault Adapter `GetCredential` (passing service identity).
   4. Builds the outbound request, injects the credential per `auth_scheme`, makes the call, and returns `{ok, status_code, latency_ms, response_body_truncated, error?}`.
   5. Zeros the plaintext credential from request scope before returning.
6. WHEN the test call completes, THEN an audit event `service.test_executed` is emitted with payload `{method, request_path_template, status_code, latency_ms, ok, error?}`. The operator‑provided body is **not** stored in the audit event (stays in the synchronous response only).
7. WHEN the test call fails (non‑2xx, timeout, DNS failure, TLS failure, or `forbidden_destination`), THEN `ok=false` is returned with the specific error category in `error`, and the audit event records `ok=false` and the error category.
8. WHEN an offline filesystem dump of the vault SQLite file is read **without** the KEK keyfile, THEN no plaintext credential can be reconstructed; AES‑256‑GCM is used so any tampering is detected on decrypt ([S‑SEC‑2](../../../docs/architecture/01-architecture/03-quality-attributes.md)).
9. WHEN the Vault Adapter is queried for a credential, THEN the plaintext is held only in a **request‑scoped variable** and zeroed (best‑effort, given Go GC) after the response is sent. The encrypted DEK MAY be cached by the Vault Adapter keyed by `(tenant_id, service_id, key_version)` with TTL ≤ JWT TTL; the plaintext credential is **never cached** anywhere.

---

## Requirement 5: Agent Creation and Permission Grant (Milestone 1.4)

**User Story:** As an operator, I want to create agents and grant them permissions — with constrained scope — so that they can call specific services with specific actions and within specific bounds.

### Acceptance Criteria

1. WHEN an operator creates an agent (`name`, optional `description`), THEN `admin-api` (a) generates an `agent_…` ULID for the agent ID, (b) generates a 32‑byte cryptographically random Agent API Key with prefix `mk_agent_` (Crockford base32 for the random part), (c) computes the Argon2id hash + an 8‑byte fingerprint (`sha256(plaintext)[:8]` hex), (d) inserts a row with the hash and fingerprint, (e) returns the **plaintext key exactly once** in the `201 Created` response. Subsequent reads of the agent never include the plaintext key.
2. WHEN an agent is created, THEN the response includes `mcp_endpoint` (computed: `{MCP_BASE_URL}/mcp`) and `api_key_fingerprint` (the 8‑byte hex prefix used in audit events).
3. WHEN an agent is created, THEN an audit event `agent.created` is emitted with `agent_id`, `tenant_id`, `operator_id`, `name`, `api_key_fingerprint`, `at`. **The plaintext key MUST NOT appear in the audit payload.**
4. WHEN an operator grants a permission, THEN `admin-api` validates the request body against the **closed `Constraints` schema** (per ADR‑0016.4 — only `rate_limit`, `time_window`, `request_path_prefix`, `source_ip_allowlist` are allowed; unknown keys → `422 validation_failed`). On success, it inserts a `permission_grants` row with `(agent_id, service_id, action, constraints, tenant_id, operator_id, created_at)` and returns `201 Created`.
5. WHEN an identical `(agent_id, service_id, action)` grant already exists with the **same** constraints, THEN the response is `200 OK` with the existing record (idempotent). When the constraints differ, the response is `409 Conflict` with `mintkey:code=permission_constraints_conflict`.
6. WHEN a permission is granted, THEN an audit event `agent.permission.granted` is emitted with `agent_id`, `service_id`, `action`, `constraints`, `tenant_id`, `operator_id`, `at`.
7. WHEN an operator revokes a permission, THEN the `permission_grants` row is deleted and an audit event `agent.permission.revoked` is emitted with `agent_id`, `service_id`, `action`, `tenant_id`, `operator_id`, `at`.
8. WHEN an agent is listed, THEN only agents in the active tenant are returned (RLS enforced); the response includes the `api_key_fingerprint` but never the plaintext.
9. WHEN a stolen Agent API Key is used by an attacker, THEN the attacker can **only** call services the agent was granted, **only** for the actions granted, **only** within the configured `Constraints` (rate limit, time window, path prefix, source IP allowlist), and revocation propagates within ≤ 5 s ([S‑SEC‑3](../../../docs/architecture/01-architecture/03-quality-attributes.md), [S‑OPS‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)).

---

## Requirement 6: MCP Discovery and Token Issuance (Milestone 1.5)

**User Story:** As an agent, I want to discover which services I may use and request short‑lived tokens so that I can make authenticated calls without holding real credentials.

### Acceptance Criteria

1. WHEN an agent connects to the MCP Server with `Authorization: Bearer mk_agent_…`, THEN the MCP Server (a) format‑checks the prefix, (b) looks up the agent by `api_key_fingerprint`, (c) verifies via Argon2id with `subtle.ConstantTimeCompare`, (d) on success, sets `app.current_tenant = <agent.tenant_id>` (`SET LOCAL` per‑transaction in Postgres) for the session and binds `agent_id` to the connection.
2. WHEN an agent connects with an invalid, malformed, or revoked API key, THEN the MCP Server returns `401 unauthenticated` (no information about which check failed) and emits an audit event from the catalog: `auth.agent_login.failed.bad_format`, `auth.agent_login.failed.unknown_key`, `auth.agent_login.failed.revoked`. The API response is identical across failure modes.
3. WHEN an agent calls `list_services()`, THEN the MCP Server returns only services in the agent's tenant for which **at least one `permission_grant` exists for that agent**, paginated, scoped to the agent's tenant via RLS.
4. WHEN an agent calls `describe_service(service_id)`, THEN the MCP Server returns the `service_full` schema: `{service_id, name, display_name, description?, base_url, auth_scheme, actions: [string], openapi_url?, current_key_version, explicit_proxy_url, virtual_host_proxy_url}`.
5. WHEN an agent calls `request_token(service_id, action, ttl_seconds?)`, THEN the MCP Server (a) validates a `permission_grant` exists for `(agent, service, action)`, (b) evaluates `Constraints` (rate_limit, time_window, request_path_prefix policy, source_ip_allowlist) against the current request context, (c) calls the Credential Broker, (d) returns `{token, token_type: "Bearer", expires_at, jti, key_version, proxy_endpoint}`. If any constraint denies, returns `not_authorized` with the failing constraint named in the error message; emits `token.denied`.
6. WHEN the Credential Broker issues a token, THEN it signs a JWS Ed25519 JWT with claims:
   ```
   iss   = "mintkey/broker"
   sub   = agent_<ULID>           (agent ID, prefixed ULID)
   aud   = svc_<ULID>             (service ID, prefixed ULID)
   tnt   = tenant_<ULID>          (tenant ID, prefixed ULID — NEVER a slug)
   scope = <action>               (single action string)
   jti   = <ULID>
   iat, exp                       (Unix timestamps)
   cnf.jkt?                       (high-assurance opt-in)
   kid                            (broker signing key ID)
   ```
7. WHEN a token is issued, THEN the default TTL is **600 seconds** (10 minutes). TTL is configurable per service in the range `[60, 3600]` seconds. The agent SDK SHOULD refresh tokens before reaching 50% of remaining TTL (per [ADR‑0014.9](../../../docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md)).
8. WHEN a token is issued, THEN an audit event `token.issued` is emitted with `jti`, `agent_id`, `service_id`, `tenant_id`, `scope`, `key_version`, `ttl_seconds`, `at`.
9. WHEN token issuance is measured under 100 concurrent requests/sec, THEN p99 latency ≤ **50 ms** ([S‑PERF‑2](../../../docs/architecture/01-architecture/03-quality-attributes.md)).
10. WHEN an agent calls `request_token` for a `(service, action)` not granted, THEN the MCP Server returns `not_authorized` and emits `token.denied` with `reason_code` (`permission_not_found` | `constraint_failed:rate_limit` | `constraint_failed:time_window` | `constraint_failed:source_ip` | …). The reason is in the audit; the API response carries only the high‑level error.
11. WHEN the MCP Server receives an `agent.revoked` change‑channel event for an agent it has an active session with, THEN it terminates the session within **≤ 5 seconds** of the notification ([S‑OPS‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)).

---

## Requirement 7: Brokered Call End‑to‑End (Milestone 1.6)

**User Story:** As an agent, I want to call a backend service through the Mintkey proxy so that the real credential is injected without me ever seeing it.

### Acceptance Criteria

1. WHEN an agent sends `GET https://kong/v1/call/{service_id}/...` (or the virtual‑host alias `https://{service-slug}.proxy.local/...` per ADR‑0007) with `Authorization: Bearer <JWT>`, THEN the proxy plugin validates the JWT **locally** against its cached JWKS without calling the control plane.
2. WHEN the JWT's `kid` is **not** in the JWKS cache, THEN the plugin force‑refreshes the JWKS from `GET /.well-known/jwks.json` once before rejecting; force‑refresh is rate‑limited to **at most one refresh per `(verifier_instance, kid)` per minute** to prevent JWKS hammering on bogus tokens (per ADR‑0016.2).
3. WHEN the proxy plugin validates a JWT, THEN it checks, in order, all of:
   1. JWS signature against JWKS (EdDSA / Ed25519).
   2. `exp` not past, with `≤ 30 s` clock skew.
   3. `iss == "mintkey/broker"`.
   4. `aud == service_id` (matches the registered service ID derived from the URL).
   5. `tnt == service.tenant_id` (the service's owning tenant — looked up from the proxy plugin's service config cache).
   6. `scope` matches the action implied by the request (path/method → action mapping).
   7. `jti` not in the local revocation set.
   8. `sub` (the `agent_id`) not in the local revoked‑agent set.
   9. If `cnf.jkt` is present, the inbound client cert thumbprint matches.
4. WHEN all JWT checks pass, THEN the plugin calls the Vault Adapter's `GetCredential(tenant_id, service_id, key_version)` over gRPC, presenting the **`svcid_proxy` boot secret** (per ADR‑0014.2) for caller authentication. The Vault Adapter returns the plaintext + `auth_scheme` in a request‑scoped variable. **The proxy plugin holds NO plaintext cache** (per ADR‑0014.4).
5. WHEN the plugin has the plaintext credential, THEN it strips the agent's `Authorization` header, strips hop‑by‑hop headers, and injects the credential per the service's `auth_scheme`:
   - `api_key_header` → set the configured header name to the value.
   - `api_key_query` → append the configured query parameter.
   - `bearer_token` → `Authorization: Bearer <value>`.
   - `basic_auth` → `Authorization: Basic <base64(user:pass)>`.
   - `oauth2_client_credentials` → outbound `Authorization: Bearer <access_token>` with the plugin handling refresh (if expired).
   - `oidc_client_secret` → similar to `oauth2`.
   - **`mtls`** → the plugin loads the cert+key from the credential payload, establishes mTLS to the backend with that client identity, and zeros both cert+key after the request completes. (Special case: cert+key are larger payloads; the plugin uses them only for the TLS handshake.)
6. WHEN the backend responds, THEN the plugin's response scrubber strips any echoed `Authorization`, `Cookie`, `Set-Cookie` headers and scans the body for known credential fingerprints (the credential's known prefix patterns).
7. WHEN a credential echo is detected in the response, THEN the plugin emits a high‑severity audit event `proxy.credential_echo_detected` with `service_id`, `tenant_id`, `field_location` (header name or body path) and strips the field before forwarding to the agent.
8. WHEN the proxied call completes, THEN the plugin emits a `proxy.hit` audit event with `{jti, agent_id, service_id, tenant_id, action, request_method, request_path_template, status_code, latency_ms, outcome}`.
9. WHEN the plaintext credential is no longer needed (after the upstream request returns), THEN the byte slice is best‑effort zeroed (per ADR‑0014.4).
10. WHEN proxy latency is measured under 100 RPS sustained per instance, THEN p50 added latency ≤ **10 ms** and p99 added latency ≤ **30 ms** ([S‑PERF‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)).
11. WHEN the control plane (admin‑api, MCP Server, broker) is unreachable for up to 5 minutes, THEN agents with valid un‑expired JWTs continue to make successful brokered calls; only token issuance and JWKS rotation are affected ([S‑AVAIL‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)).
12. WHEN a JWT fails any validation check, THEN Kong returns `401` with a closed‑set machine‑readable error code chosen from: `token_expired`, `token_revoked`, `tenant_mismatch`, `audience_mismatch`, `action_not_granted`, `signature_invalid`, `agent_revoked`. The error code is exposed as `mintkey:code` in the response body (RFC 7807).
13. WHEN the backend returns a redirect to a different origin, THEN Kong does NOT follow it; the redirect is returned to the agent verbatim (egress allowlist enforcement per ADR‑0007).
14. WHEN a Jaeger trace is searched by request correlation ID, THEN it contains spans for: `mintkey.mcp.tool_call`, `mintkey.broker.issue_token`, `mintkey.proxy.handle_request`, `mintkey.vault.decrypt`, `mintkey.proxy.upstream_call` ([S‑OBS‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)).

---

## Requirement 8: Audit Log Viewer (Milestone 1.7)

**User Story:** As an operator, I want to view and filter audit events — confident the log is tamper‑evident — so that I can investigate what agents did and when.

### Acceptance Criteria

1. WHEN an operator opens the Audit Log view in AdminJS, THEN they see a paginated list of audit events for their active tenant, ordered by `at DESC` and stable within the same `at` by `event_id`.
2. WHEN an operator filters by `agent_id`, THEN only events for that agent are shown.
3. WHEN an operator filters by `event_type`, THEN only events of that type are shown.
4. WHEN an operator filters by time range (`from`, `to`), THEN only events within that range are shown.
5. WHEN an audit query covers a 1‑hour window for a single agent in a tenant of ≤ 1 M total events, THEN results are returned within ≤ 2 seconds ([S‑AUD‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)).
6. WHEN an operator in tenant A queries audit events, THEN they cannot see events from tenant B (RLS enforced; the API response carries no tenant‑B records).
7. WHEN the audit table is queried, THEN it is **append‑only** — the `mintkey_app` DB role has only `INSERT` and `SELECT` privileges on `audit_events`, no `UPDATE` and no `DELETE`. Architecture test asserts the role grants on every CI run.
8. WHEN audit events are stored, THEN **every** row carries `prev_hash` and `hash` per the **mandatory** per‑tenant hash chain (per ADR‑0014.7). `hash = sha256(canonical_json(event_minus_hash) || prev_hash)`. The first row in each tenant's chain references the genesis hash `sha256("mintkey-audit-genesis-v1:" || tenant_id)`.
9. WHEN audit emission would create a chain break (e.g., a concurrent insert claims the same `prev_hash`), THEN the transaction retries serially within the same per‑tenant audit advisory lock; the lock guarantees per‑tenant ordering.

---

## Requirement 9: Credential Rotation (Milestone 1.8)

**User Story:** As an operator, I want to rotate a backend credential without any agent reconfiguration so that I can maintain security hygiene without downtime.

### Acceptance Criteria

1. WHEN an operator submits a new credential value for an existing service, THEN the Vault Adapter stores it with `key_version = current + 1`. Older versions remain readable until soft‑deleted.
2. WHEN a new credential version is stored, THEN `admin-api` publishes `NOTIFY mintkey:credential` (the **global** channel per ADR‑0014.1) with payload `{event_id, event_type: "credential.rotated", tenant_id, service_id, key_version, at}` **inside the same DB transaction** as the Vault Adapter write and the audit emission.
3. WHEN the **Vault Adapter** receives a `credential.rotated` event for a credential whose previous version is in its encrypted‑DEK cache, THEN it **invalidates the cache entry** for `(tenant_id, service_id, key_version_old)` immediately. (The proxy plugin holds no credential cache per ADR‑0014.4.)
4. WHEN the proxy plugin makes its next call to the Vault Adapter for that credential, THEN the Vault Adapter serves the new `key_version` (cache miss → re‑decrypt the new wrapped DEK → return plaintext). The plugin uses the new value transparently.
5. WHEN credential rotation is measured under synthetic load (100 RPS through the proxy), THEN 100% of proxy hits within ≤ 30 seconds after rotation use the new credential with **zero failures** attributable to the rotation ([S‑OPS‑2](../../../docs/architecture/01-architecture/03-quality-attributes.md)).
6. WHEN a credential is rotated, THEN an audit event `credential.rotated` is emitted with `credential_id`, `service_id`, `tenant_id`, `previous_key_version`, `key_version`, `operator_id`, `at`. The event participates in the per‑tenant hash chain.
7. WHEN the change channel is unavailable during rotation, THEN the system degrades gracefully to TTL‑based expiry: subscribers reconcile via `GET /v1/changes?since=<event_id>` (per ADR‑0010 / ADR‑0017.7) on reconnect, and the Vault Adapter cache TTL (≤ JWT TTL = 10 min) bounds the worst‑case lag.

---

## Requirement 10: Agent Revocation (Milestone 1.9)

**User Story:** As an operator, I want to revoke an agent's access immediately so that a compromised agent cannot continue making calls.

### Acceptance Criteria

1. WHEN an operator clicks "Revoke" on an agent, THEN `admin-api` (a) sets `agents.status = 'revoked'`, (b) publishes `NOTIFY mintkey:agent` (the **global** channel per ADR‑0014.1) with `{event_id, event_type: "agent.revoked", tenant_id, agent_id, at}` inside the same DB transaction, (c) emits the audit event in the same transaction.
2. WHEN the MCP Server receives an `agent.revoked` event for one of its tracked tenants, THEN it (a) terminates any active session for that agent within ≤ 5 s, (b) rejects subsequent connection attempts with `401 agent_revoked`.
3. WHEN the proxy plugin receives an `agent.revoked` event, THEN it adds `agent_id` to its in‑memory revoked‑agent set within ≤ 5 s.
4. WHEN a request arrives at the proxy with a JWT whose `sub` is in the revoked‑agent set, THEN the plugin returns `401 agent_revoked` without calling the Vault Adapter.
5. WHEN revocation is measured end‑to‑end, THEN the deny propagates within **≤ 5 seconds** of the operator clicking "Revoke" ([S‑OPS‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)).
6. WHEN an agent is revoked, THEN an audit event `agent.revoked` is emitted with `agent_id`, `tenant_id`, `operator_id`, `reason?`, `at`.
7. WHEN the change channel is unavailable during revocation, THEN the system degrades gracefully: subscribers reconcile on reconnect via `GET /v1/changes?since=<event_id>` (which itself returns `410 since_unknown` per ADR‑0017.7 if the cursor is older than the retention window). Token TTL (≤ 10 min) bounds the worst‑case lag.
8. WHEN a revoked agent attempts a new MCP connection, THEN the connection is rejected with `401 agent_revoked` and an audit event `auth.agent_login.failed.revoked` is emitted.

---

## Requirement 11: Observability Dashboards (Milestone 1.10)

**User Story:** As an operator, I want pre‑built Grafana dashboards so that I can monitor system health without manual setup.

### Acceptance Criteria

1. WHEN Grafana starts, THEN it loads pre‑provisioned dashboards from the repo (`./grafana/provisioning/dashboards/`) without manual import.
2. WHEN the system is running, THEN the **"Mintkey Overview"** dashboard shows: per‑service request rate (RPS), error rate (4xx/5xx), p50/p99 proxy latency, token issuance rate, active agent count, change‑channel subscriber lag.
3. WHEN the system is running, THEN the **"Per‑Service"** dashboard shows: per‑service request rate, latency, error rate, top agents, top actions.
4. WHEN the system is running, THEN the **"Credential Cache"** dashboard shows: Vault Adapter encrypted‑DEK cache hit rate, cache invalidation events, decrypt latency p50/p99.
5. WHEN every container emits OTLP, THEN the OTel Collector fans out traces to Jaeger and metrics to Prometheus without data loss under steady‑state load (≤ 100 RPS).
6. WHEN any span attribute matches the **forbidden suffix patterns** — `*_token`, `*_secret`, `*_password`, `*_passphrase`, exact names `mintkey.token`, `mintkey.api_key`, `mintkey.password`, `mintkey.authorization_header`, `mintkey.cookie_value`, `mintkey.set_cookie_value`, **or** the credential‑signature regex `^(sk|pk)_[a-zA-Z0-9_-]{20,}$` or `eyJ[A-Za-z0-9+/=._-]{20,}` (JWT shape) — THEN the OTel SDK drops the attribute before export. The **redaction CI test** asserts that no span carries any forbidden attribute under load (per ADR‑0017.6).
7. WHEN `mintkey.tenant_id` is set on a span, THEN it MAY also propagate via OTel baggage; **no other** Mintkey attribute is allowed in baggage.

---

## Requirement 12: CI Smoke Test (Milestone 1.11)

**User Story:** As a developer, I want a CI smoke test that exercises the full E2E‑01 happy path so that every PR is gated on a working system.

### Acceptance Criteria

1. WHEN the CI smoke test runs, THEN it completes the full E2E‑01 happy path (bootstrap → login → register service → register credential → test → create agent → grant permission → MCP discovery → token request → brokered call → audit verification) within ≤ **90 seconds** after `docker compose up` reports healthy ([S‑TEST‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)).
2. WHEN the smoke test completes, THEN it asserts:
   1. Kong returns `200` for the brokered call.
   2. The `demo-backend` log shows the **real API key**, not the JWT.
   3. The audit log contains all 9 expected event types: `tenant.bootstrap_completed`, `auth.login.success`, `service.registered`, `credential.registered`, `service.test_executed`, `agent.created`, `agent.permission.granted`, `token.issued`, `proxy.hit`.
   4. A Jaeger trace exists with all expected spans (`mintkey.mcp.tool_call`, `mintkey.broker.issue_token`, `mintkey.proxy.handle_request`, `mintkey.vault.decrypt`, `mintkey.proxy.upstream_call`).
3. WHEN the smoke test runs, THEN it uses only Docker Compose — no external services, no manual steps after `docker compose up`.
4. WHEN the smoke test runs, THEN it asserts that **no plaintext credential** appears in any container log (red‑team grep against the known credential value and known fingerprints; zero matches required) ([S‑SEC‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)).
5. WHEN the smoke test runs, THEN it asserts that **no OTel span attribute matches the forbidden patterns** in REQ‑11.6 (CI redaction test).
6. WHEN CI runs **schema‑integrity gates** in addition to the smoke test, THEN it asserts:
   1. `openapi-spec-validator` passes on `docs/architecture/contracts/rest/openapi.yaml`.
   2. `redocly lint` reports **zero errors** (warnings allowed only on documented operations: `authLoginRedirect`, `authLoginCallback`, health, JWKS).
   3. **OpenAPI parity**: the runtime `GET /openapi.json` from `admin-api` is byte‑identical (after canonical YAML/JSON sort) to the checked‑in `docs/architecture/contracts/rest/openapi.yaml` (per ADR‑0014.3).
   4. JSON Schemas (`audit-event.schema.json`, `change-event.schema.json`) pass `Draft202012Validator.check_schema`.
   5. `protoc --descriptor_set_out=/dev/null docs/architecture/contracts/vault-adapter/vault.proto` exits 0.
   6. **SQLAlchemy mirror diff**: after Liquibase migrations against a temp DB, `sqlacodegen --generator declarative` output matches the checked‑in `mintkey-models/src/mintkey_models/sql.py` after canonical formatting (per ADR‑0015).
   7. **RLS architecture test**: every tenant‑scoped table in `pg_policies`, no policy with `qual = 'true'`, the `tenant_isolation` clause references `current_setting('app.current_tenant')`.
   8. **Audit chokepoint architecture test**: every state‑change handler in the FastAPI source emits an audit event via the single `audit.emit()` helper (static analysis).
   9. **Mermaid render**: every fenced ` ```mermaid ` block in `docs/architecture/` renders via `mmdc` without error.

---

## Requirement 13: Multi‑Tenant Smoke Test (Milestone 1.12)

**User Story:** As a `PlatformAdmin`, I want to verify that tenant isolation is enforced so that one tenant's data and tokens cannot be accessed by another.

### Acceptance Criteria

1. WHEN a `PlatformAdmin` creates a second tenant `t_acme` (`POST /v1/tenants`), THEN the operation completes within ≤ **60 seconds** end‑to‑end and the tenant is ready for service registration ([S‑MT‑2](../../../docs/architecture/01-architecture/03-quality-attributes.md)). The operation triggers (a) audit_chain_state genesis row, (b) tenant settings row, (c) Keycloak‑realm‑less default OIDC posture (single realm).
2. WHEN an operator in tenant `t_default` queries services via the Admin API or AdminJS, THEN they receive zero results from tenant `t_acme` (RLS enforced). Same for agents, credentials, permissions, audit events.
3. WHEN a JWT issued for tenant `t_default` is presented to a service registered in tenant `t_acme`, THEN the proxy plugin returns `401 tenant_mismatch` and emits `proxy.denied` with `reason_code=tenant_mismatch`.
4. WHEN an integration test fuzzes API endpoints with cross‑tenant `service_id`/`agent_id`/`credential_id` parameters from a non‑PlatformAdmin operator's session, THEN **zero** records from the wrong tenant are returned ([S‑MT‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)).
5. WHEN an architecture test runs in CI, THEN it asserts (a) 100% RLS coverage on tenant‑scoped tables, (b) no `qual='true'` policies, (c) every domain table's policy contains the `app.current_tenant` clause, (d) the `mintkey_app` DB role does not have `BYPASSRLS`.
6. WHEN a `PlatformAdmin` performs a cross‑tenant **read** (audit query, changes feed, list endpoint with `app.platform_admin_view='on'`), THEN an audit event `platform_admin.access` is emitted in the **target tenant's** audit chain with `{resource_type, viewed_tenant_ids, endpoint, result_count, reason?, operator_id, at}` (per ADR‑0017.4).
7. WHEN a `PlatformAdmin` performs a cross‑tenant **write** (creates a tenant, modifies `tenant_settings`, etc.), THEN the corresponding state‑change audit event is emitted with `actor_type=platform_admin` and a sibling `platform_admin.access` event records the action.

---

## Requirement 14: Admin Settings Endpoint (Milestone 1.13)

**User Story:** As a `PlatformAdmin`, I want to view and toggle instance‑wide admin settings so that I can govern the system after bootstrap.

### Acceptance Criteria

1. WHEN a `PlatformAdmin` calls `GET /v1/admin/settings`, THEN `admin-api` returns the full `AdminSettings` document (closed schema per ADR‑0016.6): `internal_auth.{enabled, can_be_disabled}`, `oidc.{issuer, client_id, auto_provision_role}`, `audit.{retention_days_security_relevant, retention_days_proxy_hits}`.
2. WHEN a non‑`PlatformAdmin` operator calls `GET /v1/admin/settings`, THEN the response is `403 permission_denied`.
3. WHEN a `PlatformAdmin` calls `PATCH /v1/admin/settings` with a partial body, THEN missing keys retain their existing values; supplied keys are validated against the closed schema (`additionalProperties: false`).
4. WHEN a `PATCH` would set `internal_auth.enabled=false` while `internal_auth.can_be_disabled=false` (i.e., before any operator has logged in via OIDC with `Admin` role), THEN the response is `409 validation_failed` with `mintkey:code=internal_auth_cannot_be_disabled` and a body explaining the precondition.
5. WHEN any settings change succeeds, THEN an audit event `settings.updated` is emitted with `fields_changed: [string]`, `operator_id`, `at` — and a sibling `platform_admin.access` event for the cross‑tenant nature of the change.
6. WHEN a settings change is read by `admin-api` on subsequent requests, THEN the new values take effect within the next request (no restart required).

---

## Requirement 15: Audit Chain Verification Job (Milestone 1.13)

**User Story:** As an `Auditor`, I want the audit hash chain to be periodically verified so that tampering is detected, not just defended against.

### Acceptance Criteria

1. WHEN the audit chain verification job runs (default cadence: daily), THEN for each tenant it walks the audit chain in order, recomputes each row's `hash`, and compares to the stored `hash`.
2. WHEN the chain is intact for a tenant, THEN the job emits `audit.chain.verified` to that tenant's audit chain with payload `{chain_length, first_event_id, last_event_id, last_hash, verified_at}`.
3. WHEN the chain has a discrepancy at row N, THEN the job emits `audit.chain.tampered` to the tenant's chain with `{first_bad_event_id, expected_hash, actual_hash, detected_at}`, and also writes a record into a system alert sink (logs at ERROR level + an OTel `mintkey.audit_chain.tampered` metric) so an operator is notified.
4. WHEN the verification job is invoked on demand by a `PlatformAdmin` (`POST /v1/admin/audit/verify-chain?tenant_id=...`), THEN it runs synchronously, returns within ≤ 30 s for chains of ≤ 1 M events, and emits the same events as the scheduled run.
5. WHEN a chain has been tampered, THEN subsequent verification attempts re‑emit `audit.chain.tampered` until the operator marks the discrepancy reviewed via an admin endpoint (`POST /v1/admin/audit/acknowledge-tamper`).
6. WHEN the verification job fails to start (DB unreachable, etc.), THEN the failure is recorded as a metric and a generic OTel error log; no audit event is emitted (the chain is the audit; if it can't be read, audit emission would be incoherent).

---

## Cross‑Cutting Requirements

### Security

- **REQ‑SEC‑1** ([S‑SEC‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)): the real backend credential MUST NOT appear in any log, OTel span attribute, response body visible to the agent, or audit event payload, at any point in the system. Enforced by the redaction CI test (REQ‑11.6) and the plaintext‑in‑logs red‑team grep (REQ‑12.4).
- **REQ‑SEC‑2** ([S‑SEC‑2](../../../docs/architecture/01-architecture/03-quality-attributes.md), ADR‑0003): all credentials at rest MUST be encrypted with AES‑256‑GCM using a per‑credential DEK wrapped by the KEK loaded from the keyfile.
- **REQ‑SEC‑3**: all Agent API Keys MUST be stored as Argon2id hashes. The plaintext key MUST be returned exactly once (at create time) and never stored or logged. Audit payloads carry `api_key_fingerprint` only.
- **REQ‑SEC‑4**: all operator sessions MUST use `HttpOnly; Secure; SameSite=Strict` cookies with server‑side session storage in Postgres.
- **REQ‑SEC‑5** (ADR‑0014.6): all state‑changing requests from AdminJS to admin‑api MUST be `AdminUiSignedRequest` Ed25519 JWTs, validated against AdminJS's public key. The `jti` MUST be inserted into `admin_request_jti` to prevent replay across replicas.
- **REQ‑SEC‑6**: CSRF tokens (`X-Mintkey-Csrf` header, double‑submit cookie pattern) MUST be validated on all browser‑originated state‑changing `POST`/`PUT`/`PATCH`/`DELETE` requests.
- **REQ‑SEC‑7** (ADR‑0007): the proxy MUST enforce an egress allowlist — only the registered `base_url` of the bound service is a valid destination. RFC1918, link‑local, loopback, and cloud‑metadata IPs MUST be rejected unless the service explicitly opts in.
- **REQ‑SEC‑8** (ADR‑0014.2): every service‑to‑service call to the Vault Adapter MUST present a service‑identity boot secret in `X-Mintkey-Service-Token`. Boot secrets are Argon2id‑hashed at rest in `service_identities`.
- **REQ‑SEC‑9** (ADR‑0017.5): `/v1/auth/internal-login` MUST return byte‑identical bodies and statistically indistinguishable timing across the four failure modes (unknown user, wrong password, locked account, missing CSRF).
- **REQ‑SEC‑10** (ADR‑0016.2): JWKS verifiers MUST force‑refresh on unknown `kid` and rate‑limit refresh attempts to one per `(verifier_instance, kid)` per minute.

### Auditability

- **REQ‑AUD‑1**: every state‑change handler MUST emit an audit event via the single `audit.emit()` helper. No second path exists. An architecture test asserts every state‑change handler's call site exists.
- **REQ‑AUD‑2**: the audit table MUST be append‑only. The `mintkey_app` DB role MUST NOT have `UPDATE` or `DELETE` on `audit_events`. An architecture test asserts the role grants.
- **REQ‑AUD‑3**: every audit event MUST include `event_id` (ULID), `event_type` (closed enum), `tenant_id`, `actor_id`, `actor_type` (`operator` | `agent` | `system` | `platform_admin`), `target_id`, `target_type`, `at` (RFC 3339 UTC), `prev_hash`, `hash`, optional `request_id`, optional `trace_id`.
- **REQ‑AUD‑4** (ADR‑0014.7): every tenant's audit chain MUST be hash‑chained. The genesis hash is `sha256("mintkey-audit-genesis-v1:" || tenant_id)`. Insert ordering is enforced by a per‑tenant Postgres advisory lock.

### Tenant Isolation

- **REQ‑MT‑1** (ADR‑0008): every tenant‑scoped table MUST carry `tenant_id UUID NOT NULL` and a Postgres RLS policy. Architecture test asserts coverage and excludes only the documented platform‑scoped tables.
- **REQ‑MT‑2**: every DB transaction in `admin-api`, `mcp`, `vault-adapter`, and `broker` MUST set `SET LOCAL app.current_tenant = '<uuid>'` via middleware before any query executes. The Postgres role `mintkey_app` does NOT have `BYPASSRLS`.
- **REQ‑MT‑3**: the JWT `tnt` claim MUST be the **prefixed ULID `tenant_id`** (per ADR‑0008 + ADR‑0017.11), never a slug. The proxy plugin MUST validate `tnt` matches the **registered service's `tenant_id`** on every request.
- **REQ‑MT‑4** (ADR‑0014.1): change‑channel subscribers MUST configure their tenant scope explicitly at startup — either a tenant list or the `[ALL_TENANTS]` sentinel for cross‑tenant subscribers (Kong‑syncer). The wrapper panics on startup if no tenant scope is configured. An architecture test asserts every subscriber's wrapper invocation includes a scope.
- **REQ‑MT‑5** (ADR‑0016.3): the `PlatformAdmin` RLS escape (`current_setting('app.platform_admin_view') = 'on'`) MUST be set only by middleware that has authenticated a `PlatformAdmin` session; an integration test fuzzes non‑PlatformAdmin sessions trying to set the flag and asserts the middleware refuses.

### Observability

- **REQ‑OBS‑1**: every container MUST emit OTLP traces, metrics, and structured logs from day one.
- **REQ‑OBS‑2** (ADR‑0017.6): OTel span attributes MUST be allowlisted. Any attribute matching the forbidden patterns in REQ‑11.6 MUST be stripped before export. CI redaction test asserts coverage.
- **REQ‑OBS‑3** ([S‑OBS‑1](../../../docs/architecture/01-architecture/03-quality-attributes.md)): a single agent request MUST be traceable end‑to‑end from MCP discovery through token issuance through proxy‑egressed backend call, with all expected spans present (REQ‑12.2).

### Schema and Migrations

- **REQ‑SCHEMA‑1** (ADR‑0015): Liquibase YAML changelogs in `admin-api/db/changelog/` are the **single source of truth** for the schema. SQLAlchemy `Mapped` types and Go `sqlc` queries mirror the schema; they MUST NOT add columns or types. The CI mirror‑diff (REQ‑12.6.6) enforces this.
- **REQ‑SCHEMA‑2**: a new tenant‑scoped table MUST be created with its RLS policy in the **same** Liquibase changeset; never in a follow‑up changeset.

### Contracts

- **REQ‑CON‑1** (ADR‑0014.3): the canonical OpenAPI document is `docs/architecture/contracts/rest/openapi.yaml`. CI parity check (REQ‑12.6.3) gates every PR.
- **REQ‑CON‑2**: contract changes (OpenAPI, MCP tools, audit/change schemas, vault.proto) MUST be reviewed by the architect; the contracts directory is loaded by Kiro as the spec input.

---

## Out of Scope (Phase 1)

- HashiCorp Vault backend (Phase 2 — ADR‑0003 v2)
- SQL+KMS backend (Phase 2 — ADR‑0003 v3)
- TLS termination details and production‑grade certificate management (Phase 2)
- Kubernetes Helm chart (Phase 2)
- gRPC, WebSockets, MCP‑to‑MCP proxy (Phase 3)
- MCP for email and other service families (Phase 4)
- Operator MFA (TOTP), SAML alternative IdP (Phase 2)
- HA / replication / horizontal scaling (Phase 2)
- DB‑per‑tenant high‑isolation tier (Phase 2)
- Per‑tenant KEK (Phase 2)
- Per‑tenant external IdP federation (Phase 2)
- Tenant deletion (Phase 2 — partially specified by ADR‑0016.7; cascade is documented but Phase 1 does not exercise hard tenant delete)
- Cross‑tenant audit query UI (Phase 2)

Open questions tracked in [`docs/architecture/01-architecture/open-questions.md`](../../../docs/architecture/01-architecture/open-questions.md) (`OQ-001`..`OQ-022`) are explicitly **out of scope** for Phase 1 unless the entry's "Phase / Owner" column says "Phase 1".
