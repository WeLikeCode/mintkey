# Mintkey MVP — Tasks

Tasks are ordered by milestone (1.0 → 1.13). Each task follows TDD discipline: write the failing test first, implement until it passes, then refactor. Every task references the requirement(s) it satisfies.

## Conventions

- **Task IDs** (`T-M.N.K`) are stable; do not renumber.
- **`Refs` field** points to: `Req <N> AC<K>` (in `requirements.md`), `S-*-*` (quality‑attribute scenarios), `ADR-NNNN[.X]` (architecture decisions), `design §<N>` (design.md sections).
- **Each task is sized for a single Claude Sonnet session** (~30–90 minutes of focused work; one to three files; ≤ ~250 lines of new code per session). When a task spans multiple components, the "Sonnet hint" line gives a recommended first sub‑deliverable.
- **References to ADRs** include 0001–0017 (full set; round‑1/2/3 corrections incorporated).
- **`P-*-*` shorthand labels** in some tasks' `Acceptance` lines are Kiro‑internal property labels; they correspond to the named requirement or `S-*-*` scenario in the same line.

## Task Dependency Graph

```
M1.0 (Foundation) → M1.1 (Login) → M1.2 (Services) → M1.3 (Credentials) → M1.4 (Agents)
→ M1.5 (MCP + Token) → M1.6 (Brokered Call) → M1.7 (Audit Viewer) → M1.8 (Rotation)
→ M1.9 (Revocation) → M1.10 (Dashboards) → M1.11 (CI Smoke)
→ M1.12 (Multi-tenant) → M1.13 (Admin Settings + Chain Verification)
```

---

## Milestone 1.0 — Foundation Skeleton

### T-1.0.1: Liquibase changelogs — initial schema
- **What:** Write Liquibase YAML changelogs covering all domain tables with `tenant_id UUID NOT NULL`, RLS policies (with the **PlatformAdmin escape OR clause**), DB roles, and indexes.
- **Test first:** Write `tests/acceptance/test_rls_coverage.py` that connects to a test Postgres, applies all changelogs, queries `pg_policies`, and asserts (a) every tenant‑scoped table has an RLS policy, (b) **no policy has `qual = 'true'`** or any other no‑op form, (c) the policy's `qual` references **both** `current_setting('app.current_tenant', true)` AND `current_setting('app.platform_admin_view', true) = 'on'` (per ADR‑0016.3). Run it — it fails (no changelogs yet).
- **Implement:** Write `admin-api/db/changelog/001-initial-schema.yaml` through `010-indexes.yaml`. Apply RLS to **tenant‑scoped tables**: `tenants`, `operators`, `operator_tenant_memberships`, `sessions`, `services`, `credentials`, `agents`, `permission_grants`, `audit_events`, `tenant_settings`. Create three roles: `mintkey_migrate` (DDL, bypasses RLS), `mintkey_app` (DML; `INSERT`+`SELECT` on `audit_events` only — no `UPDATE`/`DELETE`), `mintkey_subscriber` (LISTEN privileges + read‑only SELECT). The RLS policy template is exactly:
  ```sql
  ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
  CREATE POLICY tenant_isolation ON <table>
    USING (
      tenant_id = current_setting('app.current_tenant', true)::uuid
      OR current_setting('app.platform_admin_view', true) = 'on'
    );
  ```
- **Clarifications (added):**
  - Also create the **platform‑scoped tables** (no RLS, on the documented allowlist): `admin_request_jti`, `service_identities`, `audit_chain_state`. These are excluded from the RLS coverage test by name in `tests/acceptance/test_rls_coverage.py:RLS_EXCLUDE`.
  - The `, true` second argument to `current_setting` is **mandatory** — without it the policy errors when the GUC is uninitialized during edge‑case connection initialization.
  - `audit_events` carries `prev_hash BYTEA` and `hash BYTEA` columns (the **mandatory** hash chain per ADR‑0014.7; see also T-1.7.5).
- **Sonnet hint:** Tackle in two sessions — (1) the schema + RLS template; (2) the architecture test. The architecture test in particular is a self‑contained ~80‑line script.
- **Acceptance:** Schema test passes with 100% coverage of tenant‑scoped tables. The platform‑scoped allowlist is documented at the top of the test file.
- **Refs:** Req 1 AC3, AC4, AC11; design §2; ADR-0008; ADR-0014.8; ADR-0015; ADR-0016.3.

### T-1.0.2: Seed job
- **What:** Implement the one‑shot seed job that bootstraps the system. The seed job runs **after** Liquibase has exited 0 and **before** `admin-api` starts.
- **Test first:** Write `tests/unit/seed/test_seed_idempotent.py` using testcontainers (Postgres + Keycloak). Run seed twice; assert state is identical after both runs and no error is raised. Then run with `--rotate-bootstrap`; assert all generated secrets are different from the first run.
- **Implement:** `seed-job/main.py` performing 12 steps **in order, idempotently** (each `INSERT … ON CONFLICT DO NOTHING` or equivalent guard):
  1. Wait for Postgres connectivity.
  2. Verify Liquibase has applied (`SELECT version FROM databasechangelog ORDER BY orderexecuted DESC LIMIT 1`).
  3. INSERT default tenant `t_default` (slug, `isolation_mode='row'`).
  4. INSERT per‑tenant `audit_chain_state` row with genesis hash `sha256("mintkey-audit-genesis-v1:" || tenant_id)`.
  5. Generate bootstrap admin password (32 bytes random); Argon2id hash; INSERT operator with `is_platform_admin=true`; INSERT `OperatorTenantMembership(role=Admin)` for `t_default`.
  6. **Generate 4 service‑identity boot secrets** (`svcid_admin_api`, `svcid_mcp`, `svcid_broker`, `svcid_proxy`); Argon2id hash each into `service_identities`; write plaintexts to `./data/bootstrap-secrets/svcid_*` (mode 0400).
  7. **Generate AdminJS Ed25519 keypair**; store the **public** key in the Vault Adapter under credential type `admin_ui_signing_key`; write the **private** key to `./data/bootstrap-secrets/admin_ui_private.pem` (mode 0400). *(Per ADR‑0014.6, ADR‑0017.1.)*
  8. **Generate Broker Ed25519 keypair**; store the **private** key in the Vault Adapter under credential type `signing_key` with a `kid` (ULID); the public key is published by the broker's JWKS endpoint at runtime.
  9. Import Keycloak realm `mintkey` from `seed-job/realm-mintkey.json` via the Keycloak Admin REST API.
  10. Write bootstrap admin password to `./data/bootstrap-secrets/admin_password` (mode 0400) and print to stdout.
  11. Emit audit event `tenant.bootstrap_completed` for `t_default` (the **first** event in the per‑tenant chain).
  12. Exit 0.
- **Clarifications (added):**
  - The seed job does **not** itself run Liquibase — it depends on the separate Liquibase one‑shot. (Pre‑correction designs had the seed run Liquibase; that's superseded.)
  - The 4 boot secrets, the AdminJS keypair, and the broker keypair were missing from earlier task drafts; they are required by REQ‑1.5 and REQ‑SEC‑8.
  - The `bootstrap-secrets` directory should be on a separate volume mount (`bootstrap_secrets`) per design §11.
- **Sonnet hint:** Tackle in three sessions — (1) steps 1–5; (2) steps 6–8 (key/secret generation; needs Vault Adapter from T-1.0.4); (3) steps 9–11 (Keycloak + audit emission).
- **Acceptance:** Idempotency test passes. All 12 outputs verifiable. `service_identities` populated; AdminJS public key in the Vault Adapter; broker private key in the Vault Adapter; first audit event emitted with valid `prev_hash` matching the genesis hash.
- **Refs:** Req 1 AC5, AC6, AC12; design §3; ADR-0014.2, ADR-0014.6, ADR-0014.7, ADR-0017.5.

### T-1.0.3: Admin API skeleton — health + ready endpoints
- **What:** Scaffold the FastAPI app with `/v1/health` and `/v1/ready`, OTel middleware, tenant‑context middleware (using **bound parameters**), and CSRF middleware.
- **Test first:** Write `tests/unit/admin_api/test_health.py`:
  - `GET /v1/health` returns 200 always (no dependency checks).
  - `GET /v1/ready` returns 503 before all of {DB connectivity, Liquibase done, Vault Adapter reachable, change‑channel listener attached}; 200 after all are confirmed.
- **Implement:** `admin-api/src/admin_api/main.py`, `api/health.py`, `middleware/otel.py`, `middleware/tenant.py`, `middleware/csrf.py`, `db/session.py`. The tenant‑context middleware **uses SQLAlchemy bound parameters via `set_config()`**, NOT f‑strings:
  ```python
  await session.execute(
      text("SELECT set_config('app.current_tenant', :tid, true)"),
      {"tid": str(tenant_id)},
  )
  if is_platform_admin_view:
      await session.execute(
          text("SELECT set_config('app.platform_admin_view', 'on', true)"),
      )
  ```
  *(F‑string interpolation into SQL is forbidden — see also T-1.2.1's `pg_notify` pattern.)*
- **Clarifications (added):**
  - `set_config(name, value, is_local=true)` is the parameterizable equivalent of `SET LOCAL`.
  - `current_setting()` reads it back. The `, true` second arg is needed in policies (T-1.0.1) so the read returns NULL if uninitialized.
  - The CSRF middleware uses double‑submit cookie pattern with `X-Mintkey-Csrf` header; it skips GET/HEAD methods and skips routes annotated `@no_csrf` (login flow).
  - The tenant‑context middleware reads the active tenant from the validated session (cookie OR signed‑request JWT — see T-1.0.13).
- **Sonnet hint:** Single session; ~200 lines; the OTel middleware uses `opentelemetry.instrumentation.fastapi.FastAPIInstrumentor`.
- **Acceptance:** Health tests pass. OTel spans emitted for every request. No SQL injection patterns (architecture test in T-1.0.15 will catch any f‑string SQL).
- **Refs:** Req 1 AC7, AC8; Req MT-2; ADR-0008; ADR-0016.3.

### T-1.0.4: Vault Adapter skeleton — startup + KEK loading
- **What:** Implement the Vault Adapter Go service skeleton with KEK loading and gRPC server stub.
- **Test first:** `services/vault-adapter/internal/kek/loader_test.go`:
  - Missing KEK source ⇒ non‑zero exit + clear error message ("KEK source required").
  - Keyfile loading from `MINTKEY_VAULT_KEK_FILE` works (32‑byte file, mode 0400).
  - Env‑var fallback (`MINTKEY_VAULT_KEK`) **rejected in production mode** (`MINTKEY_ENV=production`) — startup fails. Only allowed in `MINTKEY_ENV=dev`.
- **Implement:** `cmd/vault-adapter/main.go`, `internal/kek/loader.go`, `internal/config/config.go`, `internal/server/grpc.go` (server stub on port 8084).
- **Clarifications (added):**
  - The KEK keyfile lives at `/run/secrets/mintkey_kek_keyfile`, owned by the service user, mode 0400, mounted from a **separate volume** (`vault_kek`) from the encrypted SQLite file (`vault_data`). Defense in depth — an attacker who gets one mount should not get the other.
  - Process drops privileges (drops to non‑root user) immediately after KEK load.
- **Sonnet hint:** Single session. The KEK loader is ~50 lines; gRPC server stub is ~80 lines.
- **Acceptance:** KEK loader tests pass. Service starts and exposes gRPC port. KEK is in process memory only (verified by `pmap`/`/proc/<pid>/maps` not showing the keyfile path).
- **Refs:** Req 4 AC3; design §8; ADR-0003.

### T-1.0.5: Credential Broker skeleton — startup + JWKS endpoint
- **What:** Implement the Credential Broker Go service with Ed25519 key loading and JWKS endpoint.
- **Test first:** `services/broker/internal/keys/jwks_test.go`:
  - JWKS endpoint returns valid JWK Set with correct `kty=OKP`, `crv=Ed25519`, `use=sig`, and `kid` matching the loaded key's ULID.
  - `Cache-Control` header is `public, max-age=300`.
  - Multiple keys (during rotation overlap) all appear in the JWKS.
- **Implement:** `cmd/broker/main.go`, `internal/keys/loader.go`, `internal/keys/jwks.go`, `internal/config/config.go`. The private key is **fetched from the Vault Adapter** at startup using the `svcid_broker` boot secret (presented as `X-Mintkey-Service-Token` gRPC metadata) with credential type `signing_key`.
- **Clarifications (added):**
  - The signed JWT MUST include the `kid` in the **JWS protected header** (not just in claims) so verifiers can look up the public key. Use `jose.SignerOptions{}.WithType("JWT").WithHeader("kid", b.activeKID)`.
  - JWKS publishes both the active and the retiring keys during the overlap window (default 1 hour).
- **Sonnet hint:** Single session. The Vault Adapter client + key loader is ~100 lines; JWKS endpoint is ~50 lines.
- **Acceptance:** JWKS test passes. `GET /.well-known/jwks.json` returns a valid JWK Set.
- **Refs:** Req 6 AC9; design §7; ADR-0006; ADR-0016.2; ADR-0017.8.

### T-1.0.6: Kong-syncer skeleton — startup + health
- **What:** Scaffold the Kong‑syncer Go service with health endpoint and a Postgres LISTEN/NOTIFY subscriber stub.
- **Test first:** `services/kong-syncer/internal/health/handler_test.go` — `GET /v1/health` returns 200.
- **Implement:** `cmd/kong-syncer/main.go`, `internal/health/handler.go`, `internal/config/config.go`, `internal/changes/subscriber.go` (stub — full implementation in T-1.2.2).
- **Clarifications (added):**
  - On startup, the subscriber MUST configure its **tenant scope** via `internal/changes.WithTenantScope(...)`. For the syncer, the scope is `[ALL_TENANTS]` (it's cross‑tenant). The wrapper **panics on startup if no tenant scope is configured** (per REQ‑MT‑4 / ADR‑0014.1).
  - Subscribed channels are the **global** form: `mintkey:service`, `mintkey:agent` (NOT `mintkey:<tenant_slug>:service`).
- **Sonnet hint:** Single session.
- **Acceptance:** Health test passes. Subscriber wrapper panics if tenant scope is omitted.
- **Refs:** Req MT-4; design §9; ADR-0014.1.

### T-1.0.7: Proxy Plugin skeleton — startup + go-pdk registration
- **What:** Scaffold the proxy plugin Go service with go‑pdk registration and a JWT verifier stub.
- **Test first:** `services/proxy-plugin/internal/jwt/verifier_test.go`:
  - Malformed JWT returns error with code `invalid_format`.
  - Well‑formed JWT with wrong signature returns error with code `signature_invalid`.
- **Implement:** `cmd/proxy-plugin/main.go`, `internal/config/config.go`, `internal/jwt/verifier.go` (stub).
- **Clarifications (added):**
  - The plugin **does NOT have a credential cache** of any kind (per ADR‑0014.4). It calls the Vault Adapter via gRPC on every request. The encrypted‑DEK cache lives in the Vault Adapter.
  - The plugin **does have**: a JWKS cache (5‑min TTL with force‑refresh on unknown `kid`), a revoked‑agent set (in‑memory), a `jti` revocation set (in‑memory).
  - The plugin presents `svcid_proxy` boot secret on every gRPC call to the Vault Adapter.
- **Sonnet hint:** Single session.
- **Acceptance:** JWT verifier tests pass. Plugin registers with go‑pdk without error.
- **Refs:** design §10; ADR-0004; ADR-0014.4.

### T-1.0.8: Shared Go packages — changes, ulid, otelinit, audit, svcid
- **What:** Implement the shared Go packages.
- **Test first:**
  - `internal/changes/subscriber_test.go`: reconnect logic triggers reconciliation via `GET /v1/changes?since=<event_id>`; heartbeat timeout (60 s) triggers reconnect; **wrapper panics if `WithTenantScope` is not called**.
  - `internal/ulid/ulid_test.go`: prefix correctness for each type (`tenant_`, `agent_`, `svc_`, `cred_`, `perm_`, `audit_`, `change_`, `session_`, `system_`, `jti_`, `kid_`); monotonically increasing; 26‑char Crockford base32 body.
  - `internal/audit/emit_test.go`: `audit.Emit()` computes `prev_hash` correctly from the chain head; computes `hash = sha256(canonical_json(event_minus_hash) || prev_hash)`; takes a per‑tenant Postgres advisory lock; works inside an existing transaction.
  - `internal/svcid/client_test.go`: reads token from `/run/secrets/mintkey_service_token` at startup; presents it as `X-Mintkey-Service-Token` gRPC metadata; rotates correctly when the file changes (file watch).
- **Implement:** `internal/changes/subscriber.go`, `internal/ulid/ulid.go`, `internal/otelinit/init.go` (with the **SDK‑level redaction filter** per T-1.0.14), `internal/audit/emit.go`, `internal/svcid/client.go`.
- **Clarifications (added):**
  - `internal/audit/emit.go` is **the single audit chokepoint**. The architecture test in T-1.7.3 asserts no state‑change handler bypasses it.
  - `internal/svcid` was missing from earlier drafts; needed for REQ‑SEC‑8.
- **Sonnet hint:** Tackle in two sessions — (1) `changes` + `ulid` + `svcid`; (2) `otelinit` + `audit`.
- **Acceptance:** All unit tests pass. The audit chain integrity is verified by inserting 100 random events and re‑computing each hash from the prior `hash`.
- **Refs:** design §1; ADR-0010; ADR-0014.1; ADR-0014.2; ADR-0014.7; ADR-0017.6.

### T-1.0.9: mintkey-models shared Python package
- **What:** Implement the shared Python package: Pydantic v2 schemas, SQLAlchemy 2.x async `Mapped` types, audit emission helper, change‑channel client, service‑identity client, tenant‑context helper.
- **Test first:**
  - `mintkey-models/tests/test_models.py`: Pydantic models validate against examples in `docs/architecture/contracts/rest/openapi.yaml`; SQLAlchemy `Mapped` types are byte‑identical to `sqlacodegen` output against the introspected DB schema.
  - `mintkey-models/tests/test_audit.py`: `audit_emit()` computes correct `prev_hash`/`hash`; takes the per‑tenant advisory lock; runs inside the caller's session.
  - `mintkey-models/tests/test_tenant_ctx.py`: `set_tenant_context()` uses **bound parameters via `set_config()`**, not f‑strings; supports `is_platform_admin_view=True` to set `app.platform_admin_view='on'`.
- **Implement:** `mintkey_models/schemas.py`, `mintkey_models/db.py`, `mintkey_models/audit.py`, `mintkey_models/changes.py`, `mintkey_models/svcid.py`, `mintkey_models/tenant_ctx.py`. Package installable via `uv pip install -e mintkey-models/`.
- **Clarifications (added):**
  - SQLAlchemy types **mirror** Liquibase, never authoritative. The CI mirror‑diff (T-1.11.5) enforces this.
  - The `set_tenant_context()` helper is the Python counterpart of the Go `internal/tenant_ctx`; same SQL pattern.
- **Sonnet hint:** Two sessions — (1) schemas + db + tenant_ctx; (2) audit + changes + svcid.
- **Acceptance:** All tests pass. `uv pip install -e mintkey-models/` succeeds in `admin-api/` and `mcp-server/`.
- **Refs:** design §1; ADR-0012; ADR-0015.

### T-1.0.10: docker-compose.yml — full stack definition
- **What:** Write the complete `docker-compose.yml` with **15 long‑running containers + 2 one‑shot jobs = 17 services**, health checks, dependencies, volumes, and environment variables.
- **Test first:** `tests/acceptance/test_compose_starts.sh`:
  - `docker compose up -d` then poll `/v1/health` on `admin-api`, `mcp-server`, `broker`, `vault-adapter`, `kong-syncer`, `kong`, `keycloak`, `mock-backend`, `prometheus`, `grafana`, `jaeger`, `otel-collector`, `admin-ui` until 200 (timeout 120 s).
  - Assert one‑shot jobs (`liquibase`, `seed-job`) exited 0.
- **Implement:** `docker-compose.yml`. Startup graph:
  ```
  postgres
    └─→ liquibase (one-shot; depends_on postgres healthy)
          └─→ seed-job (one-shot; depends_on liquibase service_completed_successfully)
                └─→ admin-api (depends_on seed-job service_completed_successfully + vault-adapter healthy)
                      └─→ admin-ui, mcp-server, broker, vault-adapter, kong-syncer, kong → proxy-plugin
  keycloak (parallel; uses its own DB schema in postgres)
  otel-collector → jaeger, prometheus → grafana
  mock-backend (no deps; always up)
  ```
- **Clarifications (added):**
  - Container count was previously stated as 18; correct count is **17** per design §1: 15 long‑running + 2 one‑shot.
  - Volumes:
    - `postgres_data` — `/var/lib/postgresql/data`
    - `vault_data` — `/var/lib/mintkey/vault.sqlite` (the encrypted SQLite file)
    - **`vault_kek` (REQUIRED separate mount)** — `/run/secrets/mintkey_kek_keyfile` (mode 0400). Defense in depth: an attacker who gets `vault_data` should NOT also get the keyfile.
    - `bootstrap_secrets` — `/run/secrets/mintkey/bootstrap-secrets/` (mode 0400 each file).
    - `grafana_data` — `/var/lib/grafana`.
- **Sonnet hint:** Single session; ~200 lines of YAML.
- **Acceptance:** All containers start and pass health checks within 120 s. The KEK keyfile is on a separate mount. Liquibase exits 0 before seed‑job starts.
- **Refs:** Req 1 AC1; design §11; ADR-0003.

### T-1.0.11: RLS architecture test
- **What:** Write the CI architecture test that asserts the RLS coverage shape required by ADR‑0014.8 + ADR‑0016.3.
- **Test first:** This IS the test. `tests/acceptance/test_rls_coverage.py`:
  1. Apply Liquibase migrations to a fresh test DB.
  2. Query `pg_policies` for every table in the `public` schema (excluding the documented platform‑scoped allowlist `RLS_EXCLUDE`: `admin_request_jti`, `service_identities`, `audit_chain_state`, `databasechangelog`, `databasechangeloglock`).
  3. Assert every remaining table has at least one RLS policy.
  4. Assert **no policy has `qual = 'true'`** (no‑op policy detection).
  5. Assert every domain table's `tenant_isolation` policy `qual` references both `current_setting('app.current_tenant', true)` AND `current_setting('app.platform_admin_view', true)`.
  6. Assert the `mintkey_app` role does **not** have `BYPASSRLS`.
  7. Assert the `mintkey_app` role has **no** UPDATE/DELETE on `audit_events`.
- **Implement:** Run against the test DB; fix any missing policies/grants in the changelogs.
- **Clarifications (added):**
  - This test runs in CI on **every PR** as part of the schema‑integrity gate (T-1.11.5).
- **Acceptance:** Test passes. All 7 assertions verified.
- **Refs:** Req 1 AC11; Req MT-1, MT-5; ADR-0008; ADR-0014.8; ADR-0016.3.

### T-1.0.12: Service identity client library
- **What (NEW):** Implement the service‑identity boot‑secret client library for both Go and Python.
- **Test first:**
  - Go: `internal/svcid/client_test.go` — token loaded from `/run/secrets/mintkey_service_token` at startup; presented as `X-Mintkey-Service-Token` gRPC metadata; reloads on file change (inotify‑style).
  - Python: `mintkey-models/tests/test_svcid.py` — same behavior.
- **Implement:** `internal/svcid/client.go`, `mintkey_models/svcid.py`. Each service in compose mounts `./data/bootstrap-secrets/svcid_<service>` to `/run/secrets/mintkey_service_token`.
- **Clarifications (added):**
  - The token is **never** logged or included in OTel span attributes (verified by T-1.0.14 redaction filter).
  - Rotation: the seed job's `--rotate-bootstrap` produces a new token; services hot‑reload via file watch with a configurable overlap window.
- **Sonnet hint:** Single session; ~80 lines per language.
- **Acceptance:** Both libraries pass tests. Smoke test: `admin-api` calls Vault Adapter `Ping` with the `svcid_admin_api` token; succeeds.
- **Refs:** Req SEC-8; design §1, §8; ADR-0014.2.

### T-1.0.13: AdminUiSignedRequest middleware + jti denylist
- **What (NEW):** Implement the FastAPI middleware that validates Ed25519‑signed JWTs from AdminJS on every state‑changing endpoint, and enforces replay protection via the `admin_request_jti` table.
- **Test first:** `tests/unit/admin_api/test_signed_request.py`:
  - Valid JWT (Ed25519, signed by AdminJS private key) is accepted.
  - JWT with bad signature returns 401.
  - JWT with `iat > exp` returns 401.
  - JWT with `exp - iat > 60` returns 401 (TTL too long).
  - **Replay**: same `jti` sent twice → second attempt returns 401 with `mintkey:code=replay_detected`.
  - JWT for GET/HEAD method skipped (signed‑request only required on state‑changing methods).
- **Implement:** `admin-api/src/admin_api/auth/signed_request.py` + the FastAPI middleware registration. The public key is fetched from the Vault Adapter at startup (credential type `admin_ui_signing_key`); cached for 1 hour; force‑refreshed on signature‑verify failure. The `jti` is inserted into `admin_request_jti(jti UUID PK, expires_at)`; conflict ⇒ replay.
- **Clarifications (added):**
  - **NOT a shared symmetric secret.** AdminJS holds the private key; `admin-api` holds the public key. (Earlier design drafts described a shared‑secret model — that's superseded by ADR‑0014.6.)
  - The cleanup job (`DELETE FROM admin_request_jti WHERE expires_at < now()`) runs every 5 minutes (small in‑process scheduler).
- **Sonnet hint:** Single session; ~150 lines.
- **Acceptance:** All 6 test cases pass. Cleanup job removes expired rows.
- **Refs:** Req SEC-5; Req 2 AC10; design §4; ADR-0014.6; ADR-0016.1.

### T-1.0.14: SDK-level OTel redaction filter
- **What (NEW):** Implement the SDK‑level OTel span attribute redaction filter in both Go (`internal/otelinit`) and Python.
- **Test first:** `internal/otelinit/redaction_test.go` and `mintkey_models/tests/test_otel_redaction.py`:
  - Span attribute matching exact name `mintkey.token` is dropped.
  - Span attribute matching suffix `*_token` (e.g., `mintkey.access_token`) is dropped.
  - Span attribute matching suffix `*_secret` is dropped.
  - Span attribute matching suffix `*_password` / `*_passphrase` is dropped.
  - Span attribute value matching credential‑signature regex (`sk_*`, `pk_*`, JWT‑shape `eyJ*`) is dropped.
  - Allowlisted attribute (e.g., `mintkey.tenant_id`) passes through unchanged.
- **Implement:** Custom `SpanProcessor` in Go (`internal/otelinit/redaction.go`) and Python (`mintkey_models/otel_redaction.py`); registered in every service's OTel bootstrap.
- **Clarifications (added):**
  - This is the **first** of two redaction layers (SDK + Collector). The Collector layer (T-1.10.1) is defense in depth.
  - The redaction is per ADR‑0017.6; canonical pattern list lives in `docs/architecture/contracts/events/span-attributes.md`.
- **Sonnet hint:** Single session; ~100 lines per language.
- **Acceptance:** All test cases pass. CI red‑team grep (T-1.10.1) finds zero matches in production logs.
- **Refs:** Req OBS-2; Req 11 AC6; ADR-0017.6.

### T-1.0.15: SQL injection architecture test
- **What (NEW):** Static analysis test asserting no production code constructs SQL via f‑string interpolation.
- **Test first:** This IS the test. `tests/acceptance/test_no_sql_injection.py`:
  - Walks the AST of every `.py` file in `admin-api/src/` and `mcp-server/src/`.
  - For every `text(...)` call, asserts the argument is a string literal (not an f‑string, not a `.format()` call, not a `+` concatenation with a non‑constant).
  - For every f‑string in the codebase, asserts it does NOT contain SQL keywords (`SELECT`, `INSERT`, `UPDATE`, `DELETE`, `SET LOCAL`, `pg_notify`).
  - Allowlist: pure DDL test fixtures in `tests/` may use f‑strings.
- **Implement:** Run against the codebase; fix any matches by converting to `text(...)` with parameter binding.
- **Clarifications (added):**
  - This test catches the SQL‑injection patterns flagged in the design review (D-01, D-02). They were eliminated by using `set_config(...)` and bound `pg_notify(:channel, :payload)` in T-1.0.3.
- **Sonnet hint:** Single session; ~120 lines.
- **Acceptance:** Zero matches. CI gate.
- **Refs:** Req SEC-1, SEC-2; design §4 (corrected); ADR-0014.

---

## Milestone 1.1 — Operator Login

### T-1.1.1: Internal auth — Argon2id login endpoint with identical-body / equalized-timing
- **What:** Implement `POST /v1/auth/internal-login` with Argon2id verification, server‑side session creation, and audit event emission. **CORRECTED**: response body and timing must be identical across the four failure modes (unknown user, wrong password, locked account, missing CSRF).
- **Test first:** `tests/unit/admin_api/test_auth.py`:
  - Valid credentials return 200 + `Set-Cookie: mintkey_session=...; HttpOnly; Secure; SameSite=Strict`.
  - **Identical-body test**: assert the response body is byte‑identical for unknown‑user vs wrong‑password vs locked‑account (all return `{"type": ".../invalid-credentials", "title": "Invalid credentials", "status": 401, "mintkey:code": "invalid_credentials"}`).
  - **Equalized-timing test**: statistical k‑sample test (n=100 each) asserts the median response time across the three failure modes is within ±10% (the server always runs an Argon2id verify, against a fixed dummy hash if user is unknown).
  - Audit events distinguish the failure cases: `auth.login.failed.user_unknown`, `auth.login.failed.bad_password`, `auth.login.failed.account_locked` (the API doesn't distinguish; the audit does).
  - Account locks after 10 failed attempts within 5 minutes for the same `username_attempted`.
- **Implement:** `admin-api/src/admin_api/api/auth.py`, `auth/internal.py`, `auth/sessions.py`. Use a fixed `DUMMY_HASH` constant for the unknown‑user verify path.
- **Clarifications (added):**
  - The audit event `username_attempted` is truncated to 200 characters to avoid log injection.
  - `auth.login.failed.bad_password` carries `operator_id` (the user exists). `auth.login.failed.user_unknown` carries only `username_attempted`.
- **Sonnet hint:** Single session; the dummy‑hash + identical‑body pattern is ~30 lines of subtle code.
- **Acceptance:** All tests pass including the statistical timing test.
- **Refs:** Req 2 AC2, AC3, AC4, AC12; Req SEC-9; ADR-0017.5.

### T-1.1.2: OIDC login via Keycloak
- **What:** Implement the OIDC login flow using `authlib` — redirect to Keycloak with PKCE, validate `state` and `nonce` on callback, resolve operator + tenant memberships, create session.
- **Test first:** `tests/unit/admin_api/test_oidc.py`:
  - Mock the OIDC provider; assert callback creates a session and emits `auth.login.success` with `method=oidc`.
  - Tampered `state` returns 401 + audit `auth.login.failed.state_mismatch`.
  - ID token signature failure returns 401 + audit `auth.login.failed.id_token_invalid`.
  - Unknown OIDC `sub` (no matching operator) returns 403 with `mintkey:code=no_local_operator` and audit `auth.login.denied.no_local_operator` (auto‑provisioning disabled by default).
- **Implement:** `admin-api/src/admin_api/auth/oidc.py`, OIDC routes in `api/auth.py`.
- **Clarifications (added):**
  - PKCE is mandatory.
  - Auto‑provisioning is opt‑in via `internal_auth.oidc.auto_provision_role` setting (REQ‑14); default disabled.
- **Sonnet hint:** Single session.
- **Acceptance:** OIDC tests pass. Keycloak login works end‑to‑end in compose.
- **Refs:** Req 2 AC6; design §4.

### T-1.1.3: Session middleware + CSRF protection
- **What:** Implement session validation middleware and CSRF token middleware (double‑submit cookie pattern, `X-Mintkey-Csrf` header).
- **Test first:** `tests/unit/admin_api/test_csrf.py`:
  - State‑changing endpoints (POST/PUT/PATCH/DELETE) without `X-Mintkey-Csrf` header return 403 with `mintkey:code=csrf_required`.
  - Same with valid CSRF token succeed.
  - GET / HEAD requests bypass CSRF check.
- **Implement:** `admin-api/src/admin_api/middleware/csrf.py`, `auth/sessions.py`. The CSRF token is set as a non‑HttpOnly cookie at session creation; the client (AdminJS) reads it and echoes it in the header.
- **Clarifications (added):**
  - Routes annotated `@no_csrf` (login flow) skip the check.
  - The CSRF middleware runs **after** the session middleware (it needs the session to read the expected token from the session record).
- **Sonnet hint:** Single session.
- **Acceptance:** CSRF tests pass. Session expiry returns 401 (not 403 — auth before CSRF).
- **Refs:** Req 2 AC11; Req SEC-6.

### T-1.1.4: AdminJS login page
- **What:** Configure AdminJS login page with "Internal auth" and "Login with Keycloak" options.
- **Test first:** `admin-ui/tests/test_login.test.ts` (vitest + supertest):
  - Login page renders both options.
  - Internal login form POSTs to `/v1/auth/internal-login` (passes through the AdminJS Express server).
  - On success, the session cookie is set and the operator is redirected to the dashboard.
- **Implement:** `admin-ui/src/auth.ts`, login page configuration in AdminJS.
- **Clarifications (added):**
  - The login flow does NOT use the `AdminUiSignedRequest` middleware — login is the bootstrap surface. The middleware applies only to state‑changing endpoints **after** the operator is logged in.
- **Sonnet hint:** Single session.
- **Acceptance:** Login page renders. Internal auth flow works end‑to‑end.
- **Refs:** Req 2 AC1, AC8.

---

## Milestone 1.2 — Service Registration

### T-1.2.1: Service CRUD — Admin API
- **What:** Implement `POST/GET/PATCH/DELETE /v1/tenants/{tid}/services` with RBAC, tenant scoping, audit events, and **NOTIFY on the global channel** (per ADR‑0014.1).
- **Test first:** `tests/unit/admin_api/test_services.py`:
  - Create returns 201 with `svc_<ULID>` ID.
  - List returns only tenant‑scoped services (RLS enforced via `set_config('app.current_tenant', ...)`).
  - Duplicate `(tenant_id, name)` returns 409 with `mintkey:code=service_name_taken`.
  - RFC1918 / link‑local / metadata IP `base_url` returns 422 with `mintkey:code=forbidden_destination`.
  - Audit event `service.registered` emitted with `prev_hash`/`hash` (chain extended).
  - **`NOTIFY` fired on the global channel `mintkey:service`** (not `mintkey:<tenant_slug>:service`) inside the same DB transaction as the INSERT and audit emission.
  - The NOTIFY payload includes `tenant_id` so subscribers can filter at the application layer.
- **Implement:** `admin-api/src/admin_api/api/services.py`, `services/service_svc.py`, `changes/publisher.py`. The `pg_notify` call uses **bound parameters**:
  ```python
  await session.execute(
      text("SELECT pg_notify(:channel, :payload)"),
      {"channel": "mintkey:service", "payload": json.dumps(event)},
  )
  ```
- **Clarifications (added):**
  - **Channel naming**: global channels (`mintkey:service`, `mintkey:credential`, `mintkey:agent`, `mintkey:heartbeat`) per ADR‑0014.1. Earlier draft used `mintkey:<tenant_slug>:service` — that's superseded.
  - The `forbidden_destination` rejection applies to RFC1918, link‑local (169.254/16), loopback (127/8), and cloud metadata IPs (169.254.169.254, fd00:ec2::, etc.) unless the service explicitly opts in via `allow_internal_urls=true`.
- **Sonnet hint:** Single session; ~250 lines including the validators.
- **Acceptance:** All tests pass.
- **Refs:** Req 3 AC1–AC12; ADR-0007; ADR-0014.1.

### T-1.2.2: Kong-syncer — service change handler
- **What:** Implement the Kong‑syncer's LISTEN/NOTIFY subscriber and Kong YAML push logic.
- **Test first:**
  - `services/kong-syncer/internal/kong/yaml_test.go`: a service list produces valid Kong declarative YAML with the **explicit path route** (`/v1/call/<service_id>`) AND the **virtual‑host route** (`<slug>.<tenant_slug>.proxy.local`) per ADR‑0007.
  - Integration test: a `service.registered` NOTIFY on `mintkey:service` triggers a Kong `/config` push within ≤ 5 seconds.
  - The subscriber's tenant scope is `[ALL_TENANTS]` (cross‑tenant).
- **Implement:** `internal/changes/subscriber.go`, `internal/kong/yaml.go`, `internal/kong/client.go`, `internal/registry/client.go` (uses `svcid_proxy` boot secret to call admin‑api's read endpoint).
- **Clarifications (added):**
  - The syncer also subscribes to `mintkey:agent` for `agent.revoked` events (updates Kong's `acl` plugin denylist).
- **Sonnet hint:** Two sessions — (1) Kong YAML generation; (2) subscriber + push integration.
- **Acceptance:** Kong YAML test passes. Integration test passes (NOTIFY → Kong config update within 5 s).
- **Refs:** Req 3 AC4; design §9; ADR-0004; ADR-0007; ADR-0014.1.

### T-1.2.3: AdminJS — Services resource (writes via FastAPI)
- **What:** Configure AdminJS Services resource with list, create, edit, delete, and Test action — **all writes route through `admin-api`** with the `AdminUiSignedRequest` JWT (per ADR‑0014.5).
- **Test first:** `admin-ui/tests/test_services.test.ts`:
  - List view fetches via `@adminjs/sql` (read‑only).
  - Create form POSTs to `admin-api` with a **signed Ed25519 JWT** (verified by T-1.0.13).
  - Test action POSTs to `admin-api` `/v1/tenants/{tid}/services/{sid}/test` with the same signed envelope.
  - AdminJS does NOT INSERT/UPDATE/DELETE the `services` table directly (asserted by an integration test with a read‑only DB user that AdminJS uses for its `@adminjs/sql` adapter).
- **Implement:** `admin-ui/src/resources/services.ts`, `admin-ui/src/lib/signed-request.ts` (the JWT signer using the private key from `/run/secrets/admin_ui_private.pem`).
- **Clarifications (added):**
  - **All writes via FastAPI** (per ADR‑0014.5). No direct DB writes from AdminJS. The `@adminjs/sql` adapter is used in **read‑only mode** (configured with the `mintkey_app` role's read‑only grants via a separate read‑only DB user `mintkey_app_ro`).
  - The signed‑request JWT carries claims `iss="mintkey/admin-ui"`, `sub=<operator_id>`, `tnt=<tenant_id>`, `aud="mintkey/admin-api"`, `iat`, `exp=iat+60`, `jti=<uuid>`.
- **Sonnet hint:** Two sessions — (1) the `signed-request.ts` library; (2) the resource configuration.
- **Acceptance:** Services UI works end‑to‑end. The integration test confirms zero direct DB writes from AdminJS.
- **Refs:** Req 3; Req SEC-5; design §5; ADR-0013; ADR-0014.5; ADR-0014.6.

---

## Milestone 1.3 — Credential Registration

### T-1.3.1: Vault Adapter — PutCredential + GetCredential + ValidateServiceIdentity
- **What:** Implement AES‑256‑GCM envelope encryption in the Vault Adapter, plus the **`ValidateServiceIdentity` RPC** (per ADR‑0014.2).
- **Test first:**
  - `services/vault-adapter/internal/crypto/envelope_test.go`: encrypt then decrypt returns original plaintext; two encryptions of the same plaintext produce different ciphertexts (unique DEK + nonce); tampered ciphertext returns error (not wrong plaintext).
  - `services/vault-adapter/internal/store/sqlite_test.go`: put then get returns correct plaintext; get with wrong `key_version` returns `not_found`.
  - `services/vault-adapter/internal/server/grpc_test.go`: every RPC except `ValidateServiceIdentity` requires `X-Mintkey-Service-Token` metadata; missing/invalid token returns `Unauthenticated`. `svcid_admin_api` has full CRUD scope; `svcid_proxy` has only `GetCredential` scope.
- **Implement:** `internal/crypto/envelope.go`, `internal/crypto/dek.go`, `internal/store/sqlite.go`, `internal/server/grpc.go` (`PutCredential`, `GetCredential`, `RevokeCredential`, `ListVersions`, `ValidateServiceIdentity`).
- **Clarifications (added):**
  - The encrypted‑DEK cache (per REQ‑9.3 / ADR‑0014.4) is added in T-1.3.5 — keep this task focused on the storage layer.
  - The `ValidateServiceIdentity` RPC is called **internally** by the gRPC interceptor on every RPC; it's also exposed externally for callers to bootstrap.
- **Sonnet hint:** Two sessions — (1) crypto + store; (2) gRPC server + ValidateServiceIdentity.
- **Acceptance:** All tests pass.
- **Refs:** Req 4 AC1, AC2, AC8; Req SEC-2, SEC-8; design §8; ADR-0003; ADR-0014.2.

### T-1.3.2: Admin API — credential endpoints
- **What:** Implement `POST /v1/tenants/{tid}/services/{sid}/credentials` (create) and `POST /v1/tenants/{tid}/services/{sid}/test` (test‑run).
- **Test first:** `tests/unit/admin_api/test_credentials.py`:
  - Credential create calls Vault Adapter gRPC with `svcid_admin_api` boot secret.
  - Response body never contains the plaintext credential (only metadata: `id`, `key_version`, `auth_scheme`, `created_at`).
  - Audit event `credential.registered` emitted with no plaintext in payload.
  - Test endpoint returns `{ok, status_code, latency_ms, response_body_truncated, error?}`.
  - Test endpoint enforces a **per‑service rate limit** (default 10 / minute / service) — eleventh call within a minute returns 429 `mintkey:code=rate_limited`.
  - Test endpoint enforces the **egress allowlist** — a `forbidden_destination` returns 422 (re‑validates per‑request).
  - Test endpoint accepts operator‑configurable `{method, path, timeout_ms, body?}` (defaults `GET`, `/health`, `5000`).
  - Audit event `service.test_executed` emitted with `{method, request_path_template, status_code, latency_ms, ok, error?}` — **no body content**.
- **Implement:** `admin-api/src/admin_api/api/credentials.py`, `services/credential_svc.py`, `services/test_run.py`.
- **Clarifications (added):**
  - The test‑run endpoint and its rate limit + audit event were missing from earlier task drafts; mandated by REQ‑4 AC5–AC7 and ADR‑0017 (C-11).
- **Sonnet hint:** Two sessions — (1) credential CRUD; (2) test‑run endpoint with rate limit + allowlist.
- **Acceptance:** All tests pass.
- **Refs:** Req 4 AC4–AC9; ADR-0007; ADR-0014.2; ADR-0017 (C-11).

### T-1.3.3: Red-team plaintext grep test
- **What:** CI test that runs the full stack, performs a credential registration and test, then greps all container logs and OTel exports for the plaintext credential value.
- **Test first:** This IS the test. `tests/acceptance/test_no_plaintext.sh`:
  1. Register a credential with a known unique value (e.g., `MINTKEY_RED_TEAM_CANARY_<uuid>`).
  2. Run a service test against the mock backend.
  3. Run a brokered call through the proxy.
  4. Dump all container logs (`docker compose logs --no-color > /tmp/logs.txt`).
  5. Dump all OTel collector exports (`/tmp/otel-spans.json`).
  6. Grep for the canary value in both. Assert **zero matches**.
- **Implement:** Fix any leaks found by tightening redaction in T-1.0.14 (SDK) and T-1.10.1 (Collector).
- **Clarifications (added):**
  - The canary string includes a stable prefix (`MINTKEY_RED_TEAM_CANARY_`) so the grep is unambiguous.
  - This test runs in CI on every PR; flakiness here is treated as a hard failure.
- **Sonnet hint:** Single session for the test script; iterations on redaction may be multiple sessions.
- **Acceptance:** Zero plaintext matches in any log or trace.
- **Refs:** Req 4 AC4; Req SEC-1; Req 12 AC4; S-SEC-1.

### T-1.3.4: AdminJS — Credentials resource (writes via FastAPI)
- **What:** Configure AdminJS Credentials resource — **all writes routed to `admin-api`** with `AdminUiSignedRequest`; the list/show views never display the plaintext field.
- **Test first:** `admin-ui/tests/test_credentials.test.ts`:
  - Create form POSTs to `admin-api` with the signed envelope (NOT direct DB).
  - The `value` field is marked `x-mintkey-sensitive`; the list view shows only `auth_scheme` and `key_version`; show view shows `***`.
  - The "Rotate" action posts to `admin-api`'s rotation endpoint (T-1.8.2).
- **Implement:** `admin-ui/src/resources/credentials.ts`. Use AdminJS field config to mark `value` as write‑only.
- **Clarifications (added):**
  - The plaintext is never sent back from `admin-api` after creation; the AdminJS show view never has access to it.
- **Sonnet hint:** Single session.
- **Acceptance:** Credentials UI works. Plaintext never visible.
- **Refs:** Req 4 AC1, AC4; Req SEC-3, SEC-5.

### T-1.3.5: Vault Adapter — encrypted-DEK cache (NEW)
- **What (NEW):** Add the encrypted‑DEK cache to the Vault Adapter (per REQ‑9.3 / ADR‑0014.4).
- **Test first:** `services/vault-adapter/internal/cache/dek_cache_test.go`:
  - Cache key: `(tenant_id, service_id, key_version)`.
  - Cache TTL: 5 minutes (default; configurable, max 10 minutes).
  - Cache hit: subsequent `GetCredential` for the same `(tenant_id, service_id, key_version)` does NOT re‑read from SQLite.
  - Cache invalidation: on `credential.rotated` event from the change channel for `(tenant_id, service_id)`, all entries for that pair are evicted.
  - Cache stores the **encrypted** DEK only — never the plaintext DEK or plaintext credential.
- **Implement:** `internal/cache/dek_cache.go`, `internal/changes/subscriber.go` (Vault Adapter's change‑channel subscriber, scoped `[ALL_TENANTS]`).
- **Clarifications (added):**
  - **The proxy plugin holds NO cache**. This is the corrected behavior per ADR‑0014.4. Earlier drafts placed the cache in the proxy plugin — that's superseded.
  - Cache hit rate is exposed as Prometheus metric `mintkey_vault_dek_cache_hit_total` / `_miss_total`.
- **Sonnet hint:** Single session.
- **Acceptance:** Tests pass. Cache hit rate dashboard visible (T-1.10.3).
- **Refs:** Req 9 AC3; design §8; ADR-0014.4.

---

## Milestone 1.4 — Agent and Permission Management

### T-1.4.1: Agent CRUD — Admin API
- **What:** Implement agent CRUD with API key generation, Argon2id hashing, fingerprint computation, and audit events that carry the **fingerprint, NOT the plaintext key**.
- **Test first:** `tests/unit/admin_api/test_agents.py`:
  - Create returns 201 with `agent_<ULID>` ID and a 32‑byte plaintext API key prefixed `mk_agent_` (Crockford base32) in the body.
  - DB contains only the Argon2id hash and the 8‑byte fingerprint (`sha256(plaintext)[:8]` hex).
  - Subsequent `GET /v1/tenants/{tid}/agents/{aid}` does NOT return the plaintext.
  - Response includes `mcp_endpoint` (computed from `MCP_BASE_URL`) and `api_key_fingerprint`.
  - Audit event `agent.created` carries `api_key_fingerprint` — **NOT the plaintext**. (Architecture test asserts this.)
  - Architecture test in `tests/acceptance/test_no_plaintext_in_audit.py` greps the `audit_events.payload` JSONB for any string starting with `mk_agent_` and asserts zero matches.
- **Implement:** `admin-api/src/admin_api/api/agents.py`, `services/agent_svc.py`.
- **Clarifications (added):**
  - The plaintext is generated using `secrets.token_bytes(32)` and Crockford‑base32 encoded.
  - The architecture test that asserts "no `mk_agent_` in audit payloads" is mandatory.
- **Sonnet hint:** Single session.
- **Acceptance:** All tests pass including the audit‑payload grep.
- **Refs:** Req 5 AC1–AC3, AC9; Req SEC-3; ADR-0017.

### T-1.4.2: Permission grant/revoke with closed Constraints schema
- **What:** Implement permission grant/revoke endpoints that validate the **closed `Constraints` schema** (rate_limit, time_window, request_path_prefix, source_ip_allowlist) per ADR‑0016.4.
- **Test first:** `tests/unit/admin_api/test_permissions.py`:
  - Grant with valid `Constraints` (`{rate_limit: {requests_per_second: 10, burst: 20}, time_window: {timezone: "Europe/Bucharest", days: ["Mon"], start_local: "09:00", end_local: "17:00"}}`) returns 201.
  - Grant with **unknown key in `Constraints`** (e.g., `{foobar: 42}`) returns 422 with `mintkey:code=validation_failed` (Pydantic enforces `additionalProperties=false`).
  - Idempotent: re‑grant with identical `(agent, service, action, constraints)` returns 200 (existing record).
  - Conflicting constraints: re‑grant with same `(agent, service, action)` but different constraints returns 409 `mintkey:code=permission_constraints_conflict`.
  - Audit `agent.permission.granted` emitted with the full `constraints` in payload.
  - Revoke (DELETE) emits `agent.permission.revoked` and publishes `agent.revoked` NOTIFY on the **global channel** `mintkey:agent`.
  - Cross‑tenant grant attempt returns 404.
- **Implement:** `admin-api/src/admin_api/api/permissions.py`, Pydantic `Constraints` model in `mintkey-models/schemas.py` (mirrors the OpenAPI schema in `docs/architecture/contracts/rest/openapi.yaml`).
- **Clarifications (added):**
  - The `Constraints` schema is **closed** (`additionalProperties=false`) — this is the corrected behavior per ADR‑0016.4. Earlier drafts had it open; superseded.
  - Time window evaluation uses `zoneinfo` (Python 3.9+ stdlib). Source IP allowlist uses `ipaddress` stdlib.
  - The four constraint kinds are evaluated by the MCP Server during `request_token` (T-1.5.4).
- **Sonnet hint:** Single session.
- **Acceptance:** All tests pass including the closed‑schema enforcement.
- **Refs:** Req 5 AC4–AC7; ADR-0016.4; ADR-0014.1.

### T-1.4.3: AdminJS — Agents and Permissions resources (writes via FastAPI)
- **What:** Configure AdminJS resources for Agents and PermissionGrants — **all writes routed to `admin-api`** with `AdminUiSignedRequest`.
- **Test first:** `admin-ui/tests/test_agents.test.ts`:
  - Create shows API key in a copy box with "shown once" warning.
  - Subsequent views show only `api_key_fingerprint`.
  - Permission grant form validates `Constraints` client‑side against the closed schema (Zod schema generated from OpenAPI).
- **Implement:** `admin-ui/src/resources/agents.ts`, `admin-ui/src/resources/permissions.ts`.
- **Sonnet hint:** Single session.
- **Acceptance:** Agents UI works. API key shown exactly once. Constraints validation client‑side.
- **Refs:** Req 5 AC1, AC2; ADR-0014.5; ADR-0016.4.

---

## Milestone 1.5 — MCP Discovery and Token Issuance

### T-1.5.1: MCP Server — agent authentication + tenant context
- **What:** Implement Agent API Key validation in the MCP Server using constant‑time Argon2id, AND set the per‑request tenant context.
- **Test first:** `tests/unit/mcp_server/test_auth.py`:
  - Valid key returns `{agent_id, tenant_id}` and the request handler runs with `app.current_tenant` set to the agent's tenant.
  - Invalid/malformed key returns 401 with body identical across `bad_format` / `unknown_key` / `revoked` cases (the audit distinguishes them via `auth.agent_login.failed.<reason>`).
  - Constant‑time test: timing of valid vs invalid key check is within ±10% (statistical k‑sample n=100 each).
  - The MCP Server's auth middleware calls `admin-api`'s internal `POST /v1/internal/validate-agent-key` with `svcid_mcp` boot secret (NOT a direct DB query — this keeps agent lookups inside the FastAPI's audit chokepoint).
- **Implement:** `mcp-server/src/mcp_server/auth/agent_key.py`, `mcp-server/src/mcp_server/middleware/tenant.py` (sets `app.current_tenant` per session via `set_config()`).
- **Clarifications (added):**
  - The `validate-agent-key` internal endpoint takes the API key, runs Argon2id verify, returns `{agent_id, tenant_id, status}` or 401.
  - The MCP Server's tenant middleware uses `mintkey_models.tenant_ctx.set_tenant_context()` (bound parameters, NOT f‑strings).
- **Sonnet hint:** Single session.
- **Acceptance:** All tests pass. Tenant context is set on every DB query.
- **Refs:** Req 6 AC1, AC2; Req MT-2; ADR-0009; ADR-0014.2.

### T-1.5.2: MCP Server — list_services, describe_service, get_openapi tools
- **What:** Implement the three discovery tools.
- **Test first:** `tests/unit/mcp_server/test_discovery.py`:
  - `list_services` returns only services for which the agent has at least one `permission_grant` (joined query).
  - `describe_service` returns the `service_full` schema (per `docs/architecture/contracts/mcp/tools.yaml`).
  - `get_openapi` returns the URL or inline doc; if the service has no `openapi_url`, returns `null` field (not error).
  - Cross‑tenant: an agent in tenant A querying any of the three tools never sees tenant B's services (RLS enforced + auth context binding).
- **Implement:** `mcp-server/src/mcp_server/tools/list_services.py`, `describe_service.py`, `get_openapi.py`.
- **Sonnet hint:** Single session.
- **Acceptance:** Discovery tests pass. Cross‑tenant isolation verified.
- **Refs:** Req 6 AC3, AC4; ADR-0008.

### T-1.5.3: Credential Broker — token issuance with `tnt = tenant_id` and `kid` header
- **What:** Implement JWT issuance in the Credential Broker. **CORRECTED**: `tnt` claim is the **prefixed ULID `tenant_id`**, NOT a slug; the `kid` is included in the JWS header (not just in claims).
- **Test first:** `services/broker/internal/issuer/issuer_test.go`:
  - Issued JWT has claims `{iss: "mintkey/broker", sub: agent_<ULID>, aud: [svc_<ULID>], tnt: tenant_<ULID> (prefixed ULID, NOT slug), scope, jti, iat, exp}`.
  - JWS header carries `kid` (matches one of the keys in JWKS).
  - `jti` is unique across 10 000 issuances (`jti_<ULID>` prefix).
  - Signature verifies against the public key in JWKS.
  - Issuance audit event `token.issued` emitted with `{jti, agent_id, service_id, tenant_id, scope, ttl_seconds, key_version}`.
  - Authentication: caller must present `svcid_broker` (or `svcid_mcp`, configurable) `X-Mintkey-Service-Token` metadata; otherwise 401.
- **Implement:** `internal/issuer/issuer.go`, `internal/issuer/claims.go`, `internal/audit/client.go`.
- **Clarifications (added):**
  - **`tnt` is the prefixed ULID** (e.g., `tenant_01HX...`), not the slug `t_default`. Earlier drafts used the slug — that's a wire‑format bug per ADR‑0008 + ADR‑0017.11.
  - The `kid` MUST be in the JWS protected header (see `jose.SignerOptions{}.WithHeader("kid", ...)`) so verifiers (proxy plugin) can look up the right public key in JWKS.
- **Sonnet hint:** Single session.
- **Acceptance:** All tests pass; the `tnt` claim is verified to be the ULID, not the slug, by an explicit assertion.
- **Refs:** Req 6 AC6, AC8; Req MT-3; ADR-0006; ADR-0008; ADR-0017.8, ADR-0017.11.

### T-1.5.4: MCP Server — request_token with constraint evaluation
- **What:** Implement `request_token` with **closed Constraints evaluation** before delegating to the Broker.
- **Test first:** `tests/unit/mcp_server/test_request_token.py`:
  - Valid request returns a token bundle.
  - Request for unpermitted `(service, action)` returns `not_authorized` and emits `token.denied` with `reason_code=permission_not_found`.
  - **Rate‑limit constraint**: 11 requests in a 60‑second window for a `(rate_limit: {requests_per_second: 10})` permission returns `not_authorized` with `reason_code=constraint_failed:rate_limit`.
  - **Time‑window constraint**: a request outside the configured `time_window` returns `not_authorized` with `reason_code=constraint_failed:time_window`. Test mocks `now()` to be outside the window.
  - All denials emit `token.denied` audit events.
- **Implement:** `mcp-server/src/mcp_server/tools/request_token.py`, `mcp-server/src/mcp_server/policy/constraints.py` (rate limit via in‑memory token bucket; time_window via `zoneinfo`).
- **Clarifications (added):**
  - `request_path_prefix` and `source_ip_allowlist` are evaluated by the **proxy plugin** at request time, not by the MCP Server at token issuance. The MCP Server evaluates only `rate_limit` and `time_window`. The two plugin‑side constraints are passed through into the JWT (or looked up by the proxy from the permission grant) and evaluated when the token is used.
- **Sonnet hint:** Two sessions — (1) handler + permission lookup; (2) constraint evaluation.
- **Acceptance:** All tests pass.
- **Refs:** Req 6 AC5, AC10; ADR-0016.4.

### T-1.5.5: Token issuance performance test
- **What:** Load test asserting p99 token issuance ≤ 50 ms at 100 concurrent issuances/sec.
- **Test first:** `tests/acceptance/test_token_issuance_perf.py` — uses `httpx.AsyncClient` to fire 100 concurrent token requests in a tight loop for 30 s; measures p50, p95, p99; asserts p99 ≤ 50 ms.
- **Implement:** Optimize if needed (connection pooling, async DB queries, prepared statements).
- **Acceptance:** Performance test passes. S‑PERF‑2 satisfied.
- **Refs:** Req 6 AC9; S-PERF-2.

### T-1.5.6: MCP Server — change channel subscriber (global channels)
- **What:** Implement the LISTEN/NOTIFY subscriber in the MCP Server for cache invalidation and agent revocation. **Subscribes to global channels with explicit tenant scope.**
- **Test first:** `tests/unit/mcp_server/test_changes.py`:
  - `service.registered` event invalidates discovery cache for the affected tenant.
  - `agent.revoked` event terminates active session for that agent within ≤ 5 s and rejects subsequent requests.
  - Subscriber `WithTenantScope([ALL_TENANTS])` configured at startup; **panics if not configured**.
- **Implement:** `mcp-server/src/mcp_server/changes/subscriber.py`, `cache/discovery.py`. Channels subscribed: `mintkey:service`, `mintkey:agent` (NOT `mintkey:<tenant_slug>:*`).
- **Clarifications (added):**
  - **Channel naming**: global form per ADR‑0014.1.
- **Sonnet hint:** Single session.
- **Acceptance:** Change subscriber tests pass.
- **Refs:** Req 10 AC2; design §6; ADR-0014.1.

### T-1.5.7: JWKS force-refresh rate limiter (NEW)
- **What (NEW):** In the proxy plugin's JWT verifier, rate‑limit JWKS force‑refresh attempts to **one per `(verifier_instance, kid)` per minute** (per REQ‑SEC‑10 / ADR‑0016.2).
- **Test first:** `services/proxy-plugin/internal/jwt/jwks_refresh_test.go`:
  - First request with unknown `kid` triggers a refresh.
  - Second request with the same unknown `kid` within 60 s does **not** trigger a refresh; returns the same 401 immediately.
  - After 61 s, a third request triggers a fresh refresh.
- **Implement:** `internal/jwt/jwks_cache.go` — per‑kid mutex + last‑refresh timestamp.
- **Clarifications (added):**
  - This prevents JWKS hammering by malformed JWTs (DoS surface). Without it, an attacker can force the broker to serve unbounded JWKS requests.
- **Sonnet hint:** Single session; ~80 lines.
- **Acceptance:** All test cases pass.
- **Refs:** Req SEC-10; ADR-0016.2.

---

## Milestone 1.6 — Brokered Call End-to-End

### T-1.6.1: Proxy Plugin — JWT verification
- **What:** Implement full JWT verification in the proxy plugin (signature, exp, iss, aud, tnt, scope, jti denylist, agent revocation set).
- **Test first:** `services/proxy-plugin/internal/jwt/verifier_test.go` — one test case per claim check:
  - Expired token → 401 `token_expired`.
  - Wrong `iss` → 401 `signature_invalid`.
  - Wrong `aud` (doesn't match the registered service ID) → 401 `audience_mismatch`.
  - Wrong `tnt` (doesn't match the **registered service's `tenant_id`**) → 401 `tenant_mismatch`.
  - Wrong `scope` (doesn't match the requested action) → 403 `action_not_granted`.
  - Revoked `jti` → 401 `token_revoked`.
  - Revoked agent (`sub` in revoked‑agent set) → 401 `agent_revoked`.
  - Unknown `kid` → triggers JWKS force‑refresh (T-1.5.7) once, then accepts/rejects based on refreshed JWKS.
  - Clock skew up to 30 s tolerated on `exp`.
- **Implement:** `internal/jwt/verifier.go`, `internal/jwt/jwks_cache.go`, `internal/revocation/agent_set.go`, `internal/revocation/jti_set.go`.
- **Clarifications (added):**
  - `tnt` is checked against the **registered service's `tenant_id`** — the plugin looks up the service's tenant from its in‑memory service config map (populated by Kong‑syncer per T-1.2.2). It does NOT trust agent‑provided routing.
  - All error codes are from the **closed enum** in REQ‑7.12.
- **Sonnet hint:** Two sessions — (1) signature + claims; (2) revocation sets + JWKS refresh.
- **Acceptance:** All test cases pass.
- **Refs:** Req 7 AC1–AC3, AC12; ADR-0006; ADR-0008; ADR-0014.

### T-1.6.2: Proxy Plugin — credential injection per auth_scheme
- **What:** Implement credential injection for **all 7 auth schemes** including `mtls`.
- **Test first:** `services/proxy-plugin/internal/credential/injector_test.go` — one test per scheme:
  - `api_key_header`: sets the configured header name to the value; strips agent's Authorization.
  - `api_key_query`: appends `?api_key=<value>` to URL; strips agent's Authorization.
  - `bearer_token`: sets `Authorization: Bearer <value>`.
  - `basic_auth`: sets `Authorization: Basic <base64(user:pass)>`.
  - `oauth2_client_credentials`: sets `Authorization: Bearer <access_token>` (with refresh handled by Vault Adapter).
  - `oidc_client_secret`: similar.
  - **`mtls`**: loads cert+key from the credential payload; configures mTLS to backend for this request; **zeros cert+key bytes** after the TLS handshake completes. (Cert+key never appear in logs or OTel.)
  - Across all schemes: the agent's `Authorization` header is **always stripped** before forwarding to the backend.
- **Implement:** `internal/credential/injector.go`, `internal/credential/mtls.go`.
- **Clarifications (added):**
  - mTLS is the special case — the credential payload is a base64‑encoded PEM bundle (cert + key); the plugin parses it, configures the TLS dialer, and zeros the bytes.
- **Sonnet hint:** Two sessions — (1) the six "easy" schemes; (2) mTLS.
- **Acceptance:** All injection tests pass. Agent's Authorization header verified absent in every backend log.
- **Refs:** Req 7 AC5; ADR-0016.5.

### T-1.6.3: Proxy Plugin — Vault Adapter gRPC client
- **What:** Implement the gRPC client to the Vault Adapter, with `svcid_proxy` service identity.
- **Test first:** `services/proxy-plugin/internal/vault/client_test.go`:
  - `GetCredential` returns plaintext.
  - **No plaintext cache** in the plugin (asserted by checking the client's internal struct has no `cache` field — architecture test).
  - Vault Adapter unreachable returns error (not panic).
  - Plaintext byte slice is zeroed after use (best‑effort given Go GC; verified by `runtime.SetFinalizer` instrumentation in the test).
  - Every gRPC call carries `X-Mintkey-Service-Token: <svcid_proxy>` metadata.
- **Implement:** `internal/vault/client.go`.
- **Clarifications (added):**
  - **No cache in the proxy plugin** — corrected per ADR‑0014.4. The encrypted‑DEK cache lives in the Vault Adapter (T-1.3.5).
- **Sonnet hint:** Single session.
- **Acceptance:** All tests pass.
- **Refs:** Req 7 AC4; ADR-0014.2; ADR-0014.4.

### T-1.6.4: Proxy Plugin — response scrubber
- **What:** Implement the response scrubber that strips credential echoes from response headers and body, per the **forbidden patterns** in REQ‑11.6.
- **Test first:** `services/proxy-plugin/internal/scrubber/response_test.go`:
  - Response with `Authorization: Bearer ...` header has it stripped.
  - Response with `Cookie` / `Set-Cookie` has it stripped.
  - Response body containing `api_key=sk_live_4eC39H...` has the value redacted.
  - Response body containing a JWT‑shaped token (`eyJ...`) has it redacted.
  - `proxy.credential_echo_detected` audit event emitted when the scrubber fires; carries `field_location` (header name OR body offset).
  - Clean response (no forbidden patterns) passes through unchanged.
- **Implement:** `internal/scrubber/response.go`. Forbidden header names + body regex patterns are a closed list documented in `docs/architecture/contracts/events/span-attributes.md`.
- **Clarifications (added):**
  - Body scan is bounded to the first 256 KiB to avoid pathological scrubbing on large responses.
  - The scrubber is idempotent: `scrub(scrub(r)) == scrub(r)` (PBT property).
- **Sonnet hint:** Single session; ~150 lines.
- **Acceptance:** All tests pass; PBT idempotence holds.
- **Refs:** Req 7 AC6, AC7; Req 11 AC6; ADR-0017.6.

### T-1.6.5: Proxy Plugin — audit emission and OTel
- **What:** Implement `proxy.hit` audit emission and OTel span creation in the proxy plugin.
- **Test first:** `services/proxy-plugin/internal/audit/emitter_test.go`:
  - `proxy.hit` event contains `{jti, agent_id, service_id, tenant_id, action, request_method, request_path_template, status_code, latency_ms, outcome}`.
  - Event payload contains **no credential value**.
  - OTel span `mintkey.proxy.handle_request` emitted with attributes from the allowlist (no forbidden patterns — verified by T-1.0.14 redaction filter).
- **Implement:** `internal/audit/emitter.go`. Audit emission uses internal endpoint `POST /v1/internal/audit/emit` on `admin-api` with `svcid_proxy` boot secret.
- **Sonnet hint:** Single session.
- **Acceptance:** Audit emission tests pass. OTel spans visible in Jaeger with all expected attributes.
- **Refs:** Req 7 AC8; Req OBS-1, OBS-3; S-OBS-1.

### T-1.6.6: Proxy Plugin — egress allowlist
- **What:** Implement egress allowlisting that prevents the proxy from following cross‑origin redirects.
- **Test first:** `services/proxy-plugin/internal/jwt/verifier_test.go` (extend):
  - Backend responds with 302 to a different origin → Kong returns 302 verbatim to the agent (does NOT follow).
  - Backend responds with 302 to the same origin → Kong follows (configurable; default same‑origin allowed).
  - Request to a non‑registered base URL is impossible by construction (Kong routes to the registered URL only).
- **Implement:** Egress allowlist check in the access phase. Disable Kong's `follow_redirects` by default.
- **Clarifications (added):**
  - The "registered base URL" is the canonical authority. The plugin's service config map (populated by Kong‑syncer) is the source of truth.
- **Sonnet hint:** Single session.
- **Acceptance:** Tests pass. Cross‑origin redirects are not followed.
- **Refs:** Req 7 AC13; ADR-0007.

### T-1.6.7: Proxy Plugin — change channel subscriber (no DEK cache)
- **What:** Implement the LISTEN/NOTIFY subscriber in the proxy plugin. **CORRECTED**: the plugin subscribes for `agent.revoked` and `token.revoked` only (revoked‑agent set + jti revocation set). It does NOT subscribe to `credential.rotated` — the Vault Adapter's cache (T-1.3.5) handles that.
- **Test first:** Integration test:
  - Fire `agent.revoked` NOTIFY on `mintkey:agent`; assert plugin denies the next request from that agent within ≤ 5 s.
  - Fire `token.revoked` NOTIFY on `mintkey:agent`; assert plugin denies a request bearing that `jti`.
  - **The plugin does NOT subscribe to `mintkey:credential`** (the Vault Adapter does, in T-1.3.5).
- **Implement:** `internal/changes/subscriber.go` for the proxy plugin (subscribes to `mintkey:agent` only).
- **Clarifications (added):**
  - **Plugin holds no credential cache.** Earlier drafts subscribed to `credential.rotated` for cache invalidation — that's superseded per ADR‑0014.4. The Vault Adapter handles credential cache invalidation.
- **Sonnet hint:** Single session.
- **Acceptance:** Tests pass.
- **Refs:** Req 9 AC3; Req 10 AC3; ADR-0014.4; ADR-0014.1.

### T-1.6.8: End-to-end brokered call integration test
- **What:** Full integration test for the brokered call happy path using testcontainers.
- **Test first:** `tests/acceptance/test_brokered_call.py` — spins up Postgres + Vault Adapter + Broker + Kong + Plugin + mock‑backend; issues a JWT; sends request to Kong; asserts:
  - 200 from Kong.
  - **mock‑backend's log shows the real API key**, not the JWT.
  - `proxy.hit` audit event in the audit chain.
  - OTel trace has all expected spans (`mintkey.mcp.tool_call`, `mintkey.broker.issue_token`, `mintkey.proxy.handle_request`, `mintkey.vault.get_credential`, `mintkey.proxy.upstream_call`).
  - All red‑team checks (no plaintext in logs/spans) pass.
- **Implement:** Fix any integration issues found.
- **Sonnet hint:** Single session for the test; iterations on findings.
- **Acceptance:** Integration test passes. S‑SEC‑1, S‑OBS‑1 satisfied.
- **Refs:** Req 7; S-SEC-1; S-OBS-1.

### T-1.6.9: Proxy latency benchmark
- **What:** Latency benchmark asserting p50 ≤ 10 ms and p99 ≤ 30 ms added latency at 100 RPS sustained.
- **Test first:** `tests/acceptance/test_proxy_latency.py` — runs 100 RPS for 30 s; measures added latency vs direct backend call; asserts p50 ≤ 10 ms, p99 ≤ 30 ms.
- **Implement:** Optimize if needed.
- **Acceptance:** Benchmark passes. S‑PERF‑1 satisfied.
- **Refs:** Req 7 AC10; S-PERF-1.

### T-1.6.10: Control plane availability test
- **What:** Test asserting agents with valid JWTs continue to work when the control plane is down.
- **Test first:** `tests/acceptance/test_avail.py`:
  - Issue a JWT (TTL > 60 s).
  - Stop `admin-api`, `mcp-server`, `broker` containers.
  - Send 10 brokered requests through Kong.
  - Assert all 10 succeed (proxy uses cached JWKS + Vault Adapter still up).
- **Implement:** Ensure proxy plugin caches JWKS with 5‑min TTL and Vault Adapter doesn't depend on `admin-api`.
- **Acceptance:** Test passes. S‑AVAIL‑1 satisfied.
- **Refs:** Req 7 AC11; S-AVAIL-1.

---

## Milestone 1.7 — Audit Log Viewer

### T-1.7.1: Audit log API endpoint
- **What:** Implement `GET /v1/tenants/{tid}/audit` with cursor pagination and filters (`agent_id`, `service_id`, `event_type`, time range).
- **Test first:** `tests/unit/admin_api/test_audit.py`:
  - List returns only tenant‑scoped events (RLS).
  - Filter by `agent_id` works.
  - Filter by `service_id` works.
  - Filter by `event_type` works.
  - Filter by time range works.
  - Cross‑tenant query returns empty.
  - Response time ≤ 2 s for a 1‑hour window in a tenant with ≤ 1 M total events.
  - Pagination via `?after=<event_id>&limit=<n>` returns correct next page.
- **Implement:** `admin-api/src/admin_api/api/audit.py`.
- **Sonnet hint:** Single session.
- **Acceptance:** All tests pass. S‑AUD‑1 satisfied.
- **Refs:** Req 8 AC1–AC6.

### T-1.7.2: Audit table append-only enforcement test
- **What:** Schema test asserting `mintkey_app` role has no UPDATE or DELETE grants on `audit_events`.
- **Test first:** This IS the test. `tests/acceptance/test_audit_append_only.py`:
  - Connect as `mintkey_app`; attempt UPDATE on `audit_events` → asserts permission denied.
  - Attempt DELETE → asserts permission denied.
  - INSERT and SELECT succeed.
- **Implement:** Fix any schema issues (in T-1.0.1 changelogs).
- **Acceptance:** Test passes.
- **Refs:** Req 8 AC7; Req AUD-2.

### T-1.7.3: Audit chokepoint architecture test
- **What:** AST‑walking architecture test asserting every state‑change handler in `admin-api` calls `audit_emit()`.
- **Test first:** This IS the test. `tests/acceptance/test_audit_coverage.py`:
  - Walks the AST of all FastAPI route handlers in `admin-api/src/admin_api/api/`.
  - Identifies handlers that call DB write operations (`session.add`, `session.execute(text("INSERT|UPDATE|DELETE..."))`).
  - Asserts each such handler **also** calls `audit_emit()` (or imports a service module that does).
  - Allowlist: read‑only handlers + the audit emission helper itself.
- **Implement:** Fix any handlers that bypass the chokepoint.
- **Sonnet hint:** Single session; ~120 lines of AST walking.
- **Acceptance:** Test passes. P‑AUDIT‑1 satisfied.
- **Refs:** Req 8; Req AUD-1.

### T-1.7.4: AdminJS — Audit Log resource
- **What:** Configure AdminJS Audit Log resource with read‑only list, filters, and pagination.
- **Test first:** `admin-ui/tests/test_audit.test.ts`:
  - Audit log renders.
  - Filter by `agent_id`, `service_id`, `event_type`, time range works.
- **Implement:** `admin-ui/src/resources/audit.ts`.
- **Acceptance:** Audit UI works end‑to‑end.
- **Refs:** Req 8 AC1–AC5.

### T-1.7.5: Audit hash chain + per-tenant advisory lock (NEW)
- **What (NEW):** Implement the **mandatory** audit hash chain in the `audit_emit()` helper (Go and Python).
- **Test first:**
  - `internal/audit/chain_test.go` and `mintkey-models/tests/test_audit_chain.py`:
    - First event in a tenant's chain has `prev_hash = sha256("mintkey-audit-genesis-v1:" || tenant_id)`.
    - `hash = sha256(canonical_json(event_minus_hash) || prev_hash)`.
    - Each subsequent event's `prev_hash` equals the previous event's `hash`.
    - Insertion takes a per‑tenant Postgres advisory lock (`pg_advisory_xact_lock(hashtext('audit_chain:' || tenant_id))`) to enforce per‑tenant ordering.
    - Two concurrent inserts in the same tenant serialize correctly (no chain break).
    - PBT: insert N random events into the same tenant; recompute the chain; assert all hashes match.
- **Implement:** `internal/audit/emit.go`, `mintkey_models/audit.py`. The `audit_chain_state` table tracks `head_event_id` and `head_hash` per tenant (single‑row UPSERT inside the transaction).
- **Clarifications (added):**
  - This is **mandatory** per ADR‑0014.7. Earlier drafts had it as "optional".
- **Sonnet hint:** Two sessions — (1) the hash computation + advisory lock; (2) the integration with `audit_emit()`.
- **Acceptance:** All tests including PBT pass. Concurrent insertion preserves chain integrity.
- **Refs:** Req 8 AC8; Req AUD-4; ADR-0014.7.

---

## Milestone 1.8 — Credential Rotation

### T-1.8.1: Vault Adapter — RotateCredential
- **What:** Implement `RotateCredential` gRPC method that stores the new value with `key_version + 1` while keeping old versions readable until soft‑deleted.
- **Test first:** `services/vault-adapter/internal/store/sqlite_test.go` (extend):
  - Rotate increments `key_version`.
  - Old version still retrievable.
  - New version retrievable.
  - No window where neither version is available (atomic swap).
- **Implement:** `internal/server/grpc.go` (`RotateCredential`), `internal/store/sqlite.go`.
- **Acceptance:** Tests pass.
- **Refs:** Req 9 AC1, AC6.

### T-1.8.2: Admin API — credential rotation endpoint
- **What:** Implement `POST /v1/tenants/{tid}/services/{sid}/credentials` (a new key_version of an existing credential is a "rotation"; the API endpoint is the same as create) with audit event and NOTIFY in the same transaction.
- **Test first:** `tests/unit/admin_api/test_rotation.py`:
  - Rotation increments `key_version`.
  - `credential.rotated` audit event emitted (carrying `previous_key_version` AND `key_version`).
  - `credential.rotated` NOTIFY fired on `mintkey:credential` global channel inside the same DB transaction.
- **Implement:** `admin-api/src/admin_api/api/credentials.py` (the endpoint detects `key_version > 1` is a rotation and switches the audit event type).
- **Clarifications (added):**
  - **Channel name**: global `mintkey:credential` per ADR‑0014.1.
- **Acceptance:** Tests pass.
- **Refs:** Req 9 AC2, AC6.

### T-1.8.3: Vault Adapter — credential cache invalidation on rotation
- **What:** Verify the **Vault Adapter** (NOT the proxy plugin) invalidates its encrypted‑DEK cache within 5 s of a `credential.rotated` event.
- **Test first:** `tests/acceptance/test_rotation_propagation.py`:
  - Register credential v1; start brokered calls; rotate to v2.
  - Measure time until all calls use v2.
  - Assert ≤ 30 s with zero failures attributable to the rotation (S‑OPS‑2).
- **Implement:** Already implemented in T-1.3.5 (Vault Adapter cache invalidation); this test validates the end‑to‑end timing.
- **Clarifications (added):**
  - **Cache lives in Vault Adapter, NOT proxy plugin** — corrected per ADR‑0014.4.
- **Acceptance:** Test passes. S‑OPS‑2 satisfied.
- **Refs:** Req 9 AC3–AC5; ADR-0014.4.

### T-1.8.4: AdminJS — Credential rotation action
- **What:** Add a "Rotate" action to the Credentials resource in AdminJS.
- **Test first:** `admin-ui/tests/test_rotation.test.ts`:
  - Rotate action POSTs to `admin-api`'s rotation endpoint with `AdminUiSignedRequest`.
  - New `key_version` shown after rotation.
- **Implement:** `admin-ui/src/resources/credentials.ts` (Rotate action).
- **Acceptance:** Rotation UI works.
- **Refs:** Req 9; ADR-0014.5.

---

## Milestone 1.9 — Agent Revocation

### T-1.9.1: Admin API — agent revocation endpoint
- **What:** Implement `POST /v1/tenants/{tid}/agents/{aid}/revoke` with status update, audit event, and NOTIFY in the same transaction.
- **Test first:** `tests/unit/admin_api/test_revocation.py`:
  - Revoke sets `agents.status = 'revoked'`.
  - `agent.revoked` audit event emitted.
  - `agent.revoked` NOTIFY fired on **global** `mintkey:agent` channel inside the same DB transaction.
- **Implement:** `admin-api/src/admin_api/api/agents.py` (revoke endpoint).
- **Clarifications (added):**
  - Channel name: global per ADR‑0014.1.
- **Acceptance:** Tests pass.
- **Refs:** Req 10 AC1; ADR-0014.1.

### T-1.9.2: Revocation propagation end-to-end test
- **What:** End‑to‑end revocation timing test.
- **Test first:** `tests/acceptance/test_revocation_timing.py`:
  - Create agent; issue JWT; start brokered calls; revoke agent.
  - Measure time until calls are denied; assert ≤ 5 s.
  - Revoked agent cannot connect to MCP Server (401 `agent_revoked`).
  - Revoked agent's existing JWT is denied at proxy (401 `agent_revoked`).
- **Implement:** Already implemented in T-1.6.7 + T-1.5.6; this validates timing.
- **Acceptance:** Test passes. S‑OPS‑1 satisfied.
- **Refs:** Req 10 AC5; S-OPS-1.

### T-1.9.3: Change channel reconciliation on reconnect
- **What:** Test asserting subscribers that missed events during disconnect catch up via `GET /v1/changes?since=<event_id>`.
- **Test first:** `tests/acceptance/test_reconciliation.py`:
  - Disconnect a subscriber.
  - Fire several change events.
  - Reconnect; assert all events are processed via the reconciliation endpoint.
  - **`since=<unknown>`** (cursor older than retention) returns **`410 Gone`** with `mintkey:code=since_unknown` and `oldest_known_event_id` field per ADR‑0017.7. The subscriber resyncs from `oldest_known_event_id`.
- **Implement:** `admin-api/src/admin_api/api/changes.py` (reconciliation endpoint with 410 handling).
- **Clarifications (added):**
  - The 410 behavior was added in ADR‑0017.7; missing from earlier task drafts.
- **Acceptance:** Reconciliation test passes including the 410 case.
- **Refs:** Req 10 AC7; ADR-0010; ADR-0017.7.

### T-1.9.4: AdminJS — Agent revocation action
- **What:** Add a "Revoke" action to the Agents resource in AdminJS.
- **Test first:** `admin-ui/tests/test_revocation.test.ts`:
  - Revoke action POSTs to `admin-api` revocation endpoint with `AdminUiSignedRequest`.
  - Agent status shows "revoked" after action.
- **Implement:** `admin-ui/src/resources/agents.ts` (Revoke action).
- **Acceptance:** Revocation UI works end‑to‑end.
- **Refs:** Req 10; ADR-0014.5.

---

## Milestone 1.10 — Observability Dashboards

### T-1.10.1: OTel Collector redaction (defense in depth)
- **What:** Configure the OTel Collector with attribute deletion (exact names) and `redaction` processor (regex patterns) as the **second** layer of credential leakage defense.
- **Test first:** `tests/acceptance/test_otel_collector_redaction.py`:
  - SDK‑emitted span with `mintkey.access_token` attribute (somehow snuck past the SDK filter) is dropped at the Collector before reaching Jaeger.
  - SDK‑emitted span with body containing `eyJ...` (JWT‑shape) is redacted.
  - Allowlisted attributes (`mintkey.tenant_id`, `mintkey.agent_id`, etc.) pass through.
- **Implement:** `otel-collector-config.yaml` per design §13. Attribute deletes for exact names; `redaction` processor for regex patterns.
- **Clarifications (added):**
  - This is the **second** redaction layer; the **first** is the SDK‑level filter (T-1.0.14). Two layers because the SDK can fail silently (e.g., a future contributor adds a non‑span emission path).
- **Sonnet hint:** Single session.
- **Acceptance:** Tests pass.
- **Refs:** Req 11 AC6; Req OBS-2; ADR-0017.6.

### T-1.10.2: Prometheus metrics — all containers
- **What:** Ensure all containers emit the required Prometheus metrics.
- **Test first:** `tests/acceptance/test_metrics.py`:
  - Scrape `/metrics` from each container; assert presence of:
    - `mintkey_requests_total`, `mintkey_request_duration_seconds` (RED).
    - `mintkey_token_issued_total` (broker).
    - `mintkey_proxy_hit_total`, `mintkey_proxy_added_latency_seconds` (proxy plugin).
    - `mintkey_vault_dek_cache_hit_total`, `_miss_total` (vault adapter).
    - `mintkey_changes_subscriber_lag_seconds` (every subscriber).
- **Implement:** Add Prometheus metrics to any container missing them.
- **Acceptance:** All metrics present.
- **Refs:** Req 11 AC2–AC4.

### T-1.10.3: Grafana dashboards — pre-provisioned
- **What:** Create pre‑provisioned Grafana dashboards.
- **Test first:** `tests/acceptance/test_grafana.py`:
  - Grafana API lists 4 dashboards: `mintkey-overview`, `mintkey-per-service`, `mintkey-credential-cache`, `mintkey-audit`.
  - Each has its expected panels.
- **Implement:** `grafana/provisioning/dashboards/*.json`.
- **Acceptance:** Dashboards load automatically on startup.
- **Refs:** Req 11 AC1–AC4.

### T-1.10.4: End-to-end trace verification
- **What:** Test asserting a complete end‑to‑end trace is available in Jaeger after a brokered call.
- **Test first:** `tests/acceptance/test_e2e_trace.py`:
  - Make a brokered call.
  - Query Jaeger API.
  - Assert trace contains spans: `mintkey.mcp.tool_call`, `mintkey.broker.issue_token`, `mintkey.proxy.handle_request`, `mintkey.vault.get_credential`, `mintkey.proxy.upstream_call`.
- **Implement:** Fix any missing span propagation.
- **Acceptance:** Test passes. S‑OBS‑1 satisfied.
- **Refs:** Req 11; S-OBS-1.

---

## Milestone 1.11 — CI Smoke Test and Demo Script

### T-1.11.1: Mock backend — multi-scheme HTTP service
- **What (EXPANDED per design §12):** Implement the mock backend as a multi‑endpoint Python FastAPI app exercising all 7 auth schemes plus scrubber test targets.
- **Test first:** `mock-backend/tests/test_mock.py` — one test per endpoint:
  - `GET /health` → 200 always; logs auth header at INFO level.
  - `GET /api-key-header` → returns `{"received_key": "<X-Api-Key value>"}` if present, 401 if missing.
  - `GET /api-key-query` → returns `{"received_key": "<?api_key= value>"}`.
  - `GET /bearer` → returns `{"received_token": "<Authorization: Bearer value>"}`.
  - `GET /basic-auth` → returns `{"received_user": "<basic decoded user>"}`.
  - `GET /oauth-protected` → like `/bearer`.
  - `GET /mtls` → returns `{"client_cn": "<peer cert CN>"}` (requires mTLS handshake).
  - `POST /echo` → returns full request headers + body (used for response‑scrubber tests).
  - `GET /timeout` → sleeps 30 s before responding (used to test test‑run timeout).
  - `GET /5xx` → returns 500 (used to test test‑run failure handling).
  - `GET /redirect-internal` → 302 to `/health`.
  - `GET /redirect-external` → 302 to `https://example.com/` (used to verify proxy does NOT follow).
- **Implement:** `mock-backend/src/mock_backend/main.py` (FastAPI; ~200 lines), `mock-backend/src/mock_backend/openapi.json` (auto‑generated), `mock-backend/Dockerfile`.
- **Clarifications (added per design §12):**
  - **File structure pre‑accommodates Phase 3 MCP‑native expansion**: `mock-backend/src/mock_backend/rest/` is the REST app; `mock-backend/src/mock_backend/mcp/` is reserved (empty in Phase 1) for the future MCP server interface.
  - **Logging the real credential**: every endpoint logs the received auth header value at INFO level. The smoke test (T-1.11.2) asserts that the logged value is the **real credential**, not the agent's JWT — proving Mintkey swapped it in flight.
  - **Used as scrubber test target**: the `/echo` endpoint deliberately echoes credentials back to test the proxy plugin's response scrubber (T-1.6.4). It is not "for debugging" — it's the security test target.
- **Sonnet hint:** Two sessions — (1) the 6 simple HTTP auth endpoints + the 4 utility endpoints; (2) mTLS endpoint (requires careful TLS configuration).
- **Acceptance:** All endpoint tests pass. Mock backend exposes valid OpenAPI at `/openapi.json`. The smoke test (T-1.11.2) registers it as a Mintkey service with `openapi_url`.
- **Refs:** Req 12 AC2; design §12; ADR-0007; ADR-0016.5.

### T-1.11.2: Full E2E CI smoke test
- **What:** Complete CI smoke test exercising the full E2E‑01 builder happy path.
- **Test first:** This IS the test. `tests/acceptance/test_e2e_smoke.sh` (or `.py`):
  - Performs all 13 steps of E2E‑01: bootstrap → login → register service → register credential → test → create agent → grant permission → MCP discovery → token request → brokered call → audit verification.
  - Measures total runtime; asserts ≤ **90 seconds** after `docker compose up` reports healthy.
  - Asserts: Kong returns 200 for the brokered call; the **mock backend's log shows the real API key (not the JWT)**; the audit log contains all 9 expected event types; a Jaeger trace exists with all expected spans.
  - Red‑team grep against canary credential (T-1.3.3) and OTel exports — zero matches.
- **Implement:** Fix any issues found.
- **Sonnet hint:** Two sessions — (1) the 13‑step happy path; (2) the assertions.
- **Acceptance:** Smoke test passes in ≤ 90 s. S‑TEST‑1 satisfied.
- **Refs:** Req 12 AC1–AC5; S-TEST-1.

### T-1.11.3: CI pipeline configuration
- **What:** Configure the CI pipeline (GitHub Actions or equivalent) to run all tests on every PR.
- **Test first:** N/A — infrastructure.
- **Implement:** `.github/workflows/ci.yml` runs:
  - Per‑language linters (golangci-lint, ruff, mypy --strict, eslint --max-warnings=0).
  - Unit tests (Go test, pytest, vitest).
  - Integration tests (testcontainers).
  - Architecture tests (T-1.0.11, T-1.0.15, T-1.7.2, T-1.7.3, T-1.10.1).
  - Schema-integrity gates (T-1.11.5, T-1.11.6, T-1.11.7).
  - Smoke test (T-1.11.2).
- **Acceptance:** CI runs on every PR and fails on any test failure.
- **Refs:** Req 12.

### T-1.11.4: Mock backend — Mintkey service registration via seed (NEW)
- **What (NEW):** The seed job registers the mock backend as a Mintkey service so the agent can discover and call it through Mintkey's normal flow.
- **Test first:** `tests/acceptance/test_mock_backend_registered.py`:
  - After `docker compose up`, query `admin-api` for the `t_default` tenant's services.
  - Assert `mock-backend` is registered with the right `base_url`, `auth_scheme`, and `openapi_url`.
  - A demo agent `mock-agent` exists with permission grants for `read:health`, `read:echo`, etc.
- **Implement:** Extend `seed-job/main.py` (T-1.0.2) with a final step: register the mock backend service + create a demo agent + grant permissions. Optional via `MINTKEY_SEED_DEMO=true` env var.
- **Clarifications (added):**
  - This is what makes the mock backend **discoverable via MCP** — after the seed runs, an agent connecting to MCP can `list_services()` and see the mock backend.
- **Sonnet hint:** Single session; ~80 lines added to seed.
- **Acceptance:** Test passes. The smoke test (T-1.11.2) uses the seeded service.
- **Refs:** Req 12 AC2; design §12.

### T-1.11.5: OpenAPI parity CI gate (NEW)
- **What (NEW):** CI gate asserting the FastAPI runtime OpenAPI matches the checked‑in canonical YAML.
- **Test first:** This IS the test. `tests/acceptance/test_openapi_parity.py`:
  1. Start `admin-api`.
  2. `GET /openapi.json` from the running app.
  3. Diff (after canonical YAML/JSON sort) against `docs/architecture/contracts/rest/openapi.yaml`.
  4. Assert byte‑identical.
- **Implement:** A CI step in `.github/workflows/ci.yml`. Use `yq` for canonical sort.
- **Clarifications (added):**
  - Per ADR‑0014.3: the **checked‑in YAML is canonical**. FastAPI must conform.
- **Acceptance:** Diff is empty.
- **Refs:** Req 12.6.3; ADR-0014.3.

### T-1.11.6: SQLAlchemy mirror diff CI gate (NEW)
- **What (NEW):** CI gate asserting `mintkey-models/src/mintkey_models/db.py` matches the schema introspected from the live DB.
- **Test first:** This IS the test. `tests/acceptance/test_sqlalchemy_mirror.py`:
  1. Spin up Postgres.
  2. Apply Liquibase migrations.
  3. Run `sqlacodegen --generator declarative postgresql://...` to produce a fresh mirror.
  4. Diff (canonical formatting) against the checked‑in `mintkey-models/src/mintkey_models/db.py`.
  5. Assert byte‑identical (modulo whitespace/order).
- **Implement:** A CI step in `.github/workflows/ci.yml`.
- **Clarifications (added):**
  - Per ADR‑0015: Liquibase is the **source of truth**; SQLAlchemy mirrors. The CI gate enforces this.
  - If a developer adds a column in SQLAlchemy without Liquibase, this test fails.
- **Acceptance:** Diff is empty.
- **Refs:** Req SCHEMA-1; ADR-0015.

### T-1.11.7: Mermaid render CI gate (NEW)
- **What (NEW):** CI gate asserting every Mermaid block in the architecture docs renders without error.
- **Test first:** This IS the test. `tests/acceptance/test_mermaid_renders.sh`:
  1. Find all ` ```mermaid ` blocks in `docs/architecture/`.
  2. For each, `mmdc -i <input> -o /tmp/check.svg`.
  3. Assert exit 0 for every block.
- **Implement:** A CI step using `npx --yes -p @mermaid-js/mermaid-cli@10`.
- **Acceptance:** All blocks render.
- **Refs:** Req 12.6.9.

---

## Milestone 1.12 — Multi-Tenant Smoke Test

### T-1.12.1: Tenant creation API
- **What:** Implement `POST /v1/tenants` (PlatformAdmin only) with audit event and per‑tenant `audit_chain_state` initialization.
- **Test first:** `tests/unit/admin_api/test_tenants.py`:
  - PlatformAdmin can create tenant.
  - Non‑PlatformAdmin gets 403 (`mintkey:code=permission_denied`).
  - Creation completes in ≤ 60 s.
  - Audit `tenant.created` event in the new tenant's chain (genesis hash matches).
  - Audit `platform_admin.access` event (per ADR‑0017.4) in the platform's audit (or in the parent tenant's chain — TBD per OQ).
- **Implement:** `admin-api/src/admin_api/api/tenants.py`.
- **Acceptance:** All tests pass. S‑MT‑2 satisfied.
- **Refs:** Req 13 AC1; ADR-0017.4.

### T-1.12.2: Cross-tenant isolation integration test
- **What:** Cross‑tenant fuzzing test asserting zero data leakage across all API endpoints.
- **Test first:** This IS the test. `tests/acceptance/test_tenant_isolation.py`:
  - Creates two tenants `t_default` and `t_acme` with services/agents/credentials.
  - For every API endpoint, fires requests with cross‑tenant `service_id`/`agent_id`/`credential_id` from a non‑PlatformAdmin operator session.
  - Asserts all return empty results or 404. **Zero data leakage.**
  - Asserts no record from tenant B appears in tenant A's responses.
- **Implement:** Fix any RLS gaps found.
- **Acceptance:** Test passes. S‑MT‑1 satisfied.
- **Refs:** Req 13 AC2, AC4; S-MT-1.

### T-1.12.3: Cross-tenant token replay test
- **What:** Test asserting a JWT issued in tenant A is rejected for a service in tenant B.
- **Test first:** `tests/acceptance/test_cross_tenant_token.py`:
  - Issue JWT in tenant A.
  - Attempt to use it against a service in tenant B via the proxy.
  - Assert 401 `tenant_mismatch` and audit `proxy.denied` with `reason_code=tenant_mismatch`.
- **Implement:** Already implemented in T-1.6.1; this validates the end‑to‑end scenario.
- **Acceptance:** Test passes.
- **Refs:** Req 13 AC3.

### T-1.12.4: AdminJS — Tenants resource (PlatformAdmin)
- **What:** Configure AdminJS Tenants resource visible only to PlatformAdmin operators, **with the cross‑tenant view escape**.
- **Test first:** `admin-ui/tests/test_tenants.test.ts`:
  - Tenants resource is visible to PlatformAdmin only.
  - PlatformAdmin can switch between "All tenants" view (sets `req.session.platform_admin_view = true`) and a specific tenant.
  - When `platform_admin_view = true`, AdminJS resources skip the tenant filter (and the FastAPI sets `app.platform_admin_view='on'` per ADR‑0016.3).
  - When `platform_admin_view = false`, regular tenant filter applies.
- **Implement:** `admin-ui/src/resources/tenants.ts`, `admin-ui/src/middleware/platform-admin.ts`.
- **Clarifications (added):**
  - The PlatformAdmin escape was added in ADR‑0016.3; missing from earlier task drafts.
  - Every cross‑tenant **read** by a PlatformAdmin emits `platform_admin.access` (T-1.13.4).
- **Sonnet hint:** Single session.
- **Acceptance:** Tenants UI works. Cross‑tenant view restricted to PlatformAdmin.
- **Refs:** Req 13 AC1, AC6; ADR-0016.3.

### T-1.12.5: Multi-tenant CI smoke test
- **What:** Multi‑tenant smoke test creating a second tenant and verifying isolation.
- **Test first:** This IS the test. `tests/acceptance/test_multitenant_smoke.py`:
  - Create `t_acme`.
  - Register a service in `t_acme`.
  - Verify `t_default` operator cannot see it.
  - Verify a `t_default` JWT is rejected at a `t_acme` service.
  - All within ≤ 60 s.
- **Implement:** Fix any issues found.
- **Acceptance:** Test passes. Phase 1 exit criterion 6 satisfied.
- **Refs:** Req 13; S-MT-1, S-MT-2.

---

## Milestone 1.13 — Admin Settings + Audit Chain Verification (NEW)

### T-1.13.1: Admin Settings endpoint (NEW per REQ-14)
- **What (NEW):** Implement `GET /v1/admin/settings` and `PATCH /v1/admin/settings` (PlatformAdmin only) with closed `AdminSettings` schema (per ADR‑0016.6).
- **Test first:** `tests/unit/admin_api/test_admin_settings.py`:
  - GET as PlatformAdmin returns full `AdminSettings` (`internal_auth`, `oidc`, `audit`).
  - GET as non‑PlatformAdmin returns 403.
  - PATCH with valid partial body merges; missing keys retain.
  - PATCH with unknown key returns 422 (`additionalProperties=false` in Pydantic).
  - PATCH attempting to disable `internal_auth` while `can_be_disabled=false` returns 409 with `mintkey:code=internal_auth_cannot_be_disabled`.
  - Successful PATCH emits `settings.updated` audit + `platform_admin.access` audit.
- **Implement:** `admin-api/src/admin_api/api/settings.py`, `services/settings_svc.py`. Settings stored in `tenant_settings` with `tenant_id IS NULL` for platform‑level settings.
- **Sonnet hint:** Single session.
- **Acceptance:** All tests pass.
- **Refs:** Req 14; ADR-0016.6.

### T-1.13.2: Audit chain verification job (NEW per REQ-15)
- **What (NEW):** Implement the audit chain verification job that walks each tenant's chain and emits `audit.chain.verified` or `audit.chain.tampered` events.
- **Test first:** `tests/unit/audit_verify/test_chain_verify.py`:
  - For an intact chain of N events, `verify_chain(tenant_id)` returns `ok=True` and emits `audit.chain.verified` with `chain_length=N`.
  - For a tampered chain (manually corrupt one row's `payload`), `verify_chain` returns `ok=False` and emits `audit.chain.tampered` with `first_bad_event_id` matching the corrupted row.
  - Verifying ≤ 1 M events completes in ≤ 30 s.
- **Implement:** `audit-verify-job/main.py` packaged as a one‑shot container; invoked manually via `docker compose run audit-verify-job` or via the on‑demand endpoint (T-1.13.3).
- **Clarifications (added):**
  - Genesis hash: `sha256("mintkey-audit-genesis-v1:" || tenant_id)`.
  - Hash recomputation: `sha256(canonical_json(event_minus_hash) || prev_hash)`.
- **Sonnet hint:** Two sessions — (1) the verification logic; (2) the audit emission + container packaging.
- **Acceptance:** All tests pass.
- **Refs:** Req 15; ADR-0014.7.

### T-1.13.3: Audit chain on-demand verification endpoint (NEW)
- **What (NEW):** Implement `POST /v1/admin/audit/verify-chain?tenant_id=<tid>` (PlatformAdmin only).
- **Test first:** `tests/unit/admin_api/test_audit_verify_endpoint.py`:
  - Synchronous run completes within ≤ 30 s for chains of ≤ 1 M events.
  - Returns `{ok, chain_length, last_event_id, last_hash, verified_at}` on success.
  - Returns `{ok: false, first_bad_event_id, expected_hash, actual_hash}` on tamper detection.
- **Implement:** `admin-api/src/admin_api/api/audit_admin.py`. Implementation calls into the same `verify_chain()` helper as the scheduled job (T-1.13.2).
- **Sonnet hint:** Single session.
- **Acceptance:** Tests pass.
- **Refs:** Req 15; ADR-0014.7.

### T-1.13.4: PlatformAdmin cross-tenant access audit (NEW)
- **What (NEW):** Emit `platform_admin.access` audit events on every PlatformAdmin cross‑tenant **read** (audit query, changes feed, list endpoints with `app.platform_admin_view='on'`) per ADR‑0017.4.
- **Test first:** `tests/unit/admin_api/test_platform_admin_audit.py`:
  - PlatformAdmin queries audit log for tenant A → emits `platform_admin.access` with `resource_type=audit`, `viewed_tenant_ids=[A]`, `result_count=N`.
  - PlatformAdmin queries with "All tenants" view → emits with `viewed_tenant_ids=["__all__"]`.
  - Non‑PlatformAdmin operations do NOT emit `platform_admin.access`.
- **Implement:** `admin-api/src/admin_api/middleware/platform_admin_audit.py`. Hooks into every endpoint that uses `app.platform_admin_view='on'`.
- **Clarifications (added):**
  - This event is emitted in the **target tenant's** audit chain (so the tenant's own audit history shows when a platform admin viewed their data).
- **Sonnet hint:** Single session.
- **Acceptance:** Tests pass.
- **Refs:** Req 13 AC6; Req MT-5; ADR-0017.4.

### T-1.13.5: Acknowledge tamper endpoint (NEW)
- **What (NEW):** Implement `POST /v1/admin/audit/acknowledge-tamper?tenant_id=<tid>&event_id=<eid>` (PlatformAdmin only). Records that an operator has reviewed a tampered chain so subsequent verifications don't re‑emit `audit.chain.tampered` for the same event_id.
- **Test first:** `tests/unit/admin_api/test_acknowledge_tamper.py`:
  - After a tamper is detected and acknowledged, subsequent `verify-chain` calls do NOT re‑emit `audit.chain.tampered` for the same `event_id`.
  - A new tamper detection (different `event_id`) DOES emit a fresh event.
  - Acknowledgment itself is audited as `audit.chain.tamper_acknowledged`.
- **Implement:** `admin-api/src/admin_api/api/audit_admin.py`, persistence in a new `audit_chain_acknowledgments` table (platform‑scoped).
- **Sonnet hint:** Single session.
- **Acceptance:** Tests pass.
- **Refs:** Req 15.

---

## Phase 1 Exit Criteria Checklist

- [ ] T-1.0.10: All containers start and pass health checks within 120 s (15 long-running + 2 one-shot)
- [ ] T-1.0.11: RLS coverage 100% on tenant-scoped tables; no `qual='true'` policies
- [ ] T-1.0.15: No SQL injection patterns (no f-string SQL)
- [ ] T-1.1.1: Operator internal login with identical-body / equalized-timing
- [ ] T-1.1.3: CSRF + signed-request middleware enforced on state-changing endpoints
- [ ] T-1.2.1: Service CRUD with global change channels and NOTIFY in same transaction
- [ ] T-1.3.1: Credential encryption verified (unique DEK, tamper detection, ServiceIdentity auth)
- [ ] T-1.3.3: Zero plaintext in any container log or OTel span
- [ ] T-1.3.5: Vault Adapter encrypted-DEK cache (NOT in proxy plugin)
- [ ] T-1.4.1: Agent API key shown once; audit carries fingerprint, not key
- [ ] T-1.4.2: Closed Constraints schema enforced
- [ ] T-1.5.3: JWT issuance with `tnt = tenant_id` (prefixed ULID), `kid` in header
- [ ] T-1.5.5: Token issuance p99 ≤ 50 ms
- [ ] T-1.5.7: JWKS force-refresh rate-limited
- [ ] T-1.6.8: End-to-end brokered call passes
- [ ] T-1.6.9: Proxy p50 ≤ 10 ms, p99 ≤ 30 ms added latency
- [ ] T-1.6.10: Control plane outage doesn't break in-flight calls
- [ ] T-1.7.3: Every state-change handler emits audit event
- [ ] T-1.7.5: Mandatory audit hash chain
- [ ] T-1.8.3: Credential rotation propagates in ≤ 30 s with zero failures
- [ ] T-1.9.2: Agent revocation propagates in ≤ 5 s
- [ ] T-1.9.3: Reconciliation endpoint returns 410 on unknown `since`
- [ ] T-1.10.1: Two-layer redaction (SDK + Collector); zero credentials in spans
- [ ] T-1.10.4: End-to-end trace visible in Jaeger
- [ ] T-1.11.1: Mock backend exposes 7 auth-scheme endpoints + scrubber test target
- [ ] T-1.11.2: Full E2E smoke test passes in ≤ 90 s
- [ ] T-1.11.5/6/7: OpenAPI parity, SQLAlchemy mirror diff, Mermaid render CI gates
- [ ] T-1.12.2: Zero cross-tenant data leakage
- [ ] T-1.12.3: Cross-tenant JWT replay rejected
- [ ] T-1.12.4: PlatformAdmin RLS escape works correctly
- [ ] T-1.12.5: Multi-tenant smoke test passes
- [ ] T-1.13.1: Admin Settings endpoint works
- [ ] T-1.13.2: Audit chain verification job works
- [ ] T-1.13.4: PlatformAdmin cross-tenant reads emit `platform_admin.access`

---

## Notes for any Sonnet session picking up a task

1. **Read the task's `Refs` first** — the requirements ID, design section, and ADRs are all small, focused contexts. Avoid reading the entire repo before starting.
2. **Test first, always.** The "Test first" line is the gate; don't write implementation before the test fails for the right reason.
3. **One task per session.** If a task has a "Sonnet hint" line dividing it into sessions, treat each as its own session.
4. **No unprompted refactoring.** Per Karpathy rule 3 (`CLAUDE.md` at repo root): touch only what the task requires.
5. **Validate via tools, not assertions.** Per `CLAUDE.md` Principle 1: every claim of correctness must be backed by a tool's output (test runner, validator, lint).
6. **If a task seems too large**, surface the issue (post a comment in the task file) before attempting; don't silently scope-cut.
7. **Boil the ocean on investigation, simplicity on output.** Per `CLAUDE.md` Principle 0.
