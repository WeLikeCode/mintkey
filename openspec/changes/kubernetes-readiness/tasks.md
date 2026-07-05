# Tasks — Kubernetes Readiness

Each chunk is dispatched to a Sonnet IMPLEMENTER (test-first, surgical) and independently verified by a fresh Opus REVIEWER. PASS/FAIL/ESCALATE, 3-strike hard-stop. No chunk merges without its restart/replica regression proof. Land in order: §1 (ADR) → §2/§3/§4/§5 (the four fixes, independently reviewable) → §6 (env/docs) → §7 (integration proof).

## 1. ADR & contract (land first)

- [ ] 1.1 Write **ADR-0029** `docs/architecture/01-architecture/adr/0029-kubernetes-readiness-restart-safety.md` (status Proposed): the four fixes, the broker key-source priority (Vault → file, prod fails closed), OIDC state → Postgres TTL store, admin-ui keypair bootstrap + prod signed-write enforcement, DB-role password parameterization. State explicitly that JWKS/REST/MCP wire shapes are unchanged. Add `docs/architecture/adrs/0029-…` symlink + `adr/README.md` index row.
- [ ] 1.2 `openspec validate kubernetes-readiness --strict` passes.
- [ ] 1.3 Confirm no change needed to `docs/architecture/contracts/rest/openapi.yaml`, `mcp/tools.yaml`, or `vault-adapter/vault.proto` (the broker↔vault signing-key read reuses existing vault RPCs — cite which); note the finding in the ADR.

## 2. Fix A1 — broker signing-key persistence (Go)

- [ ] 2.1 (test-first) Key loader in `apps/broker` with two sources: Vault Adapter via `svcid_broker` (preferred) and `MINTKEY_BROKER_SIGNING_KEY_FILE` (fallback). Generate-once-and-store if the vault has no key yet. `MINTKEY_ENV=production` MUST fail closed if neither source yields a key (no ephemeral generation).
- [ ] 2.2 Replace `apps/broker/cmd/broker/main.go:45-47` ephemeral `ed25519.GenerateKey` with the loader; keep `KeyRing` retention so prior public keys stay in JWKS until token max-TTL elapses.
- [ ] 2.3 (test-first) Regression tests: (a) token issued, broker reloaded from the same source → token still validates against `/.well-known/jwks.json`; (b) two issuers with the same loaded key → each validates the other's tokens; (c) production + no key source → startup error, no ephemeral key.
- [ ] 2.4 vault-adapter: ensure `svcid_broker` has a signing-key read/create path (identity + scope + compose/env); if the vault surface needs a new key namespace, keep it within the existing `vault.proto` RPCs (no proto change) or escalate.

## 3. Fix A2 — OIDC state store (Python + Liquibase)

- [ ] 3.1 Liquibase changeset (next free number, register in `db.changelog-master.yaml`): `oidc_login_state(state text PK, code_verifier text, redirect_uri text, created_at timestamptz, expires_at timestamptz)` with MARK_RAN precondition + rollback. Reviewer decides RLS placement (auth-flow state, not tenant data).
- [ ] 3.2 Update SQLAlchemy mirror; `tests/acceptance/test_sqlalchemy_mirror.py` green.
- [ ] 3.3 (test-first) Replace `_state_store` dict in `apps/admin-api/src/admin_api/auth/oidc.py` with a repository backed by the table: insert on authorize (:113 path), single-use `SELECT…DELETE` on callback (:136 path), reject missing/expired; TTL from `MINTKEY_OIDC_STATE_TTL_SECONDS` (default 600).
- [ ] 3.4 (test-first) Tests: login state written by one request is resolved by a callback served from a *fresh* store instance (simulated replica/restart); expired state → rejected; state is single-use (replay → rejected).

## 4. Fix A3 — admin-ui keypair bootstrap (Python seed-job + admin-api)

- [ ] 4.1 (test-first) seed-job generates the Ed25519 admin-ui keypair into `bootstrap_secrets` (`admin_ui_private.pem` 0400, `admin_ui_public.pem`) if absent, using the existing idempotent ensure-secret-file helper.
- [ ] 4.2 (test-first) admin-api write-auth: under `MINTKEY_ENV=production` remove the unsigned-write fallback (reject unsigned/invalid-signature writes); keep dev fallback only when not production. Do not break `apps/admin-ui/e2e/tests/22-write-auth-contract.spec.ts` (update it to cover both modes).
- [ ] 4.3 Tests: seed-job idempotent (second run leaves keypair unchanged, mode 0400); production + unsigned write → rejected; dev + unsigned → still allowed (unchanged loop).

## 5. Fix A4 — DB role password parameterization (Liquibase + config)

- [ ] 5.1 Edit `apps/admin-api/db/changelog/015-app-role-passwords.yaml`: replace literal passwords with Liquibase property substitution (`${db_app_password}`, `${db_subscriber_password}`); wire the properties from `MINTKEY_DB_APP_PASSWORD` / `MINTKEY_DB_SUBSCRIBER_PASSWORD` at migrate invocation. Preserve rollback.
- [ ] 5.2 Ensure `DATABASE_URL` for admin-api/subscriber is composed from the same secret values (not a second hardcoded copy).
- [ ] 5.3 Tests: migrate with a non-default `MINTKEY_DB_APP_PASSWORD` → `mintkey_app` authenticates with it; unset → `.env.example` default still works (compose loop unchanged).

## 6. Env & docs

- [ ] 6.1 `.env.example`: add `MINTKEY_BROKER_SIGNING_KEY_FILE`, `MINTKEY_DB_APP_PASSWORD`, `MINTKEY_DB_SUBSCRIBER_PASSWORD`, `MINTKEY_OIDC_STATE_TTL_SECONDS` with dev defaults + comments.
- [ ] 6.2 Update `docs/DEPLOYMENT.md` (remove/qualify the "single-replica only" caveat for the now-fixed paths), `docs/NETWORK.md`/`PORTS.md` credential table, `docs/AUTH.md:239` (close the admin-ui-key gap note).

## 7. Integration proof (gates the whole change)

- [ ] 7.1 Live end-to-end on compose: issue an agent token → `docker compose restart broker` → the **same** token still authorizes a brokered proxy call (`Via: kong`). Capture output.
- [ ] 7.2 Two broker replicas (compose scale or a second service): tokens from each validate against the shared JWKS.
- [ ] 7.3 Operator OIDC login completes after an admin-api restart mid-flow.
- [ ] 7.4 All repo validators green: `openspec validate --strict`, openapi snapshot, RLS, sqlalchemy mirror, audit coverage, broker Go tests, admin-api unit tests, red-team canary.
