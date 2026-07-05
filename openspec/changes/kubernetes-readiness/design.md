# Design — Kubernetes Readiness

> **Status:** Proposed — 2026-07-05
> **Branch:** `feat/kubernetes-readiness` (implementer creates)
> **Canonical plan:** this folder (`proposal.md` + `specs/` + `tasks.md`) + ADR-0029.
> **Origin:** external readiness analysis for deploying Mintkey to the SpotUs DEV k3s cluster; this document is the design record the specs reference.

## 1. Goal

Make the core services **restart-safe** and, where designed, **multi-replica-safe**, without changing any external wire surface (JWKS, REST, MCP shapes are unchanged). Four narrowly-scoped fixes; no re-architecture.

## 2. Fix A1 — Broker signing-key persistence

**Today** (`apps/broker/cmd/broker/main.go:45-47`): `ed25519.GenerateKey(rand.Reader)` on startup → `activeKID` → `KeyRing` → `issuer.New`. Ephemeral. The `KeyRing` (`apps/broker/internal/keys/`) already supports holding multiple public keys and serving them as JWKS — that mechanism is reused, not replaced.

**Decision — key source priority:**
1. **Vault Adapter** (preferred, the design the code comment already promises): the broker fetches its private key via the vault gRPC surface using `svcid_broker`. If the key does not exist yet, the broker (or a bootstrap step) generates it **once** and stores it in the vault; subsequent starts/replicas load the same one.
2. **Mounted file** (`MINTKEY_BROKER_SIGNING_KEY_FILE`, 32-byte seed or PEM, mode 0400): deployment-portable fallback for environments where a k8s Secret is simpler than a vault round-trip at boot. `MINTKEY_ENV=production` MUST reject an ephemeral fallback (fail closed if neither source yields a key).

**Rotation / retention:** on a key change, the new key becomes `activeKID` for signing while the previous public key(s) stay in the `KeyRing` (and JWKS) until their tokens' max TTL elapses, so tokens signed just before rotation still validate. Multiple replicas loading the same active key serve identical JWKS; a client hitting any replica's JWKS validates any replica's token.

**Why not per-replica keys + shared JWKS aggregation:** aggregating every replica's public key into a shared JWKS store is more moving parts and still churns on scale events. A single durable key is simpler and matches the "broker is a stateless compute over a durable key" model.

## 3. Fix A2 — OIDC state externalization

**Today** (`apps/admin-api/src/admin_api/auth/oidc.py`): `_state_store: dict = {}` holds `{state: {code_verifier, redirect_uri}}` between the authorize redirect (:113) and the callback (:136). Process-local.

**Decision:** persist to Postgres, table `oidc_login_state(state PK, code_verifier, redirect_uri, created_at, expires_at)`. Insert on authorize, `SELECT … DELETE` (single-use) on callback, reject if missing/expired. TTL from `MINTKEY_OIDC_STATE_TTL_SECONDS` (default 600s). No Redis — avoids a new infra dependency; the login-state write rate is trivial. Rows are self-expiring; a lightweight periodic delete (or `WHERE expires_at > now()` on read + opportunistic cleanup) reaps them. RLS: this is auth-flow state, not tenant data — place it outside the RLS-scoped tables or scope appropriately per the reviewer's call.

## 4. Fix A3 — Admin-UI keypair bootstrap

**Today:** `ADMIN_UI_PRIVATE_KEY_PATH` / `ADMIN_UI_PUBLIC_KEY_PATH` point into `bootstrap_secrets`, but nothing writes them; admin-api's write-auth (ADR-0019) then accepts unsigned writes as a dev fallback.

**Decision:** seed-job generates the Ed25519 keypair into `bootstrap_secrets` if absent (same idempotent "ensure secret file" helper it already uses for OIDC client secrets; mode 0400 on the private key). Under `MINTKEY_ENV=production`, admin-api **removes the unsigned-write fallback** — a write without a valid signature is rejected. Dev behavior (unsigned allowed) is preserved only when not production, to avoid breaking the existing dev loop and e2e (`apps/admin-ui/e2e/tests/22-write-auth-contract.spec.ts`).

## 5. Fix A4 — DB role password parameterization

**Today** (`apps/admin-api/db/changelog/015-app-role-passwords.yaml:9-10`): literal `ALTER ROLE mintkey_app WITH PASSWORD 'mintkey_app_password'`.

**Decision:** replace the literals with Liquibase property substitution — `ALTER ROLE mintkey_app WITH PASSWORD '${db_app_password}'` — where the property comes from `MINTKEY_DB_APP_PASSWORD` / `MINTKEY_DB_SUBSCRIBER_PASSWORD` (env → `liquibase.parameter.*` or a `-Dparam` at invocation), injected from a k8s Secret. `DATABASE_URL` (which embeds `mintkey_app:<pw>`) must be built from the same secret. Keep dev defaults in `.env.example` so the compose loop is unchanged when the vars are unset. Note: this rotates the password *value*; existing dev DBs re-run the (idempotent) `ALTER ROLE`.

## 6. What this change deliberately does NOT do

- No Helm chart / manifests (sibling `helm-chart` change consumes these fixes).
- No Keycloak HA, no Kong scaling work, no Vault production-cluster (dev-mode vault stays opt-in).
- No change to token/JWKS/REST/MCP wire shapes — purely where secrets/state live.

## 7. Verification (the tests that prove each fix)

| Fix | Regression proof (must exist before merge) |
|---|---|
| A1 | issue token → restart broker → same token validates; two brokers, same key → tokens cross-validate; production + no key source → broker refuses to start |
| A2 | begin login on "replica 1" state, complete callback resolving state from the store (simulated second process); expired state → rejected |
| A3 | seed-job run twice → keypair present, unchanged, mode 0400; production + unsigned write → 401/403 |
| A4 | migrate with `MINTKEY_DB_APP_PASSWORD=X` → role authenticates with X; `.env.example` default still works unset |
