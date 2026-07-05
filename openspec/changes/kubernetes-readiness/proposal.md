# Kubernetes Readiness — restart- and replica-safe core services

## Why

Mintkey runs correctly under Docker Compose but is **not deployable to Kubernetes** as-is. The blocker is not missing manifests — it is four code-level behaviors that break the moment a service becomes a Pod that can restart, roll, or scale. `docs/DEPLOYMENT.md` already flags the stack as "Production HA: NOT validated — single-replica only." This change makes the core services survive pod restarts and run at their designed replica count, which is the prerequisite for any k8s deployment (see the sibling `helm-chart` change, which depends on this one).

Four independent defects, each verified in the current tree:

1. **Broker signing key is ephemeral** (`apps/broker/cmd/broker/main.go:45-47`): the Ed25519 JWS private key is generated in-process on every start (`ed25519.GenerateKey`) and never persisted. Every pod restart / rolling update invalidates **every previously-issued token**, and running >1 broker replica behind a Service is already broken — each replica signs with a different key and only its own `/.well-known/jwks.json` validates its own tokens. The code comment already names the intended fix ("T-1.0.8+ … fetched from Vault Adapter using svcid_broker") but it was never implemented.
2. **OIDC login state is an in-process dict** (`apps/admin-api/src/admin_api/auth/oidc.py:94` `_state_store = {}`, written at :113, popped at :136): the PKCE `state`/`code_verifier` for an in-flight operator login lives only in one process's memory. A second admin-api replica or a restart mid-login breaks the auth-code callback. This is the concrete reason admin-api is pinned single-replica.
3. **Admin-UI signing keypair is never generated** (`admin_ui_private.pem` / `admin_ui_public.pem`, ADR-0019, consumed by `apps/admin-ui/src/lib/signed-request.ts`): the keypair is referenced by env vars and mounted from a volume that nothing populates — not seed-job, not `install.sh`, not the Makefile. In its absence admin-api falls back to accepting **unsigned writes** (`docs/AUTH.md:239`: "must be fixed before any deployment"). A tunnel-exposed admin API accepting unsigned writes is a real exposure.
4. **DB app-role passwords are hardcoded in a committed migration** (`apps/admin-api/db/changelog/015-app-role-passwords.yaml:9-10`: `ALTER ROLE mintkey_app WITH PASSWORD 'mintkey_app_password'`): the passwords live in git history and cannot be rotated by injecting a k8s Secret — changing them requires a new migration.

## What Changes

- **Broker key persistence** — the broker loads its Ed25519 private key from a durable source instead of generating a throwaway one. Primary path: fetch from the **Vault Adapter** (`svcid_broker`, the already-intended design). Deployment-portable fallback: load from a file path (`MINTKEY_BROKER_SIGNING_KEY_FILE`) that a k8s Secret can mount. The `KeyRing` retains prior public keys so tokens signed before a key rotation still validate (JWKS serves current + recent keys). Multiple replicas load the **same** key and therefore serve a consistent JWKS.
- **OIDC state externalization** — `_state_store` moves out of process memory into a shared, TTL'd store (Postgres table `oidc_login_state`, keyed by `state`, with `expires_at`). admin-api becomes restart- and (for the login flow) multi-replica-safe.
- **Admin-UI key bootstrap** — the seed-job generates the Ed25519 admin-ui keypair (if absent) into the `bootstrap_secrets` volume/Secret, mirroring how it already provisions OIDC client secrets. `MINTKEY_ENV=production` enforces signed writes (no unsigned-write fallback).
- **DB role password parameterization** — the role passwords come from env/secret at migrate time (Liquibase property substitution or a post-migrate step reading `MINTKEY_DB_APP_PASSWORD` / `MINTKEY_DB_SUBSCRIBER_PASSWORD`), sourced from a k8s Secret. Migration 015 stops embedding literals.

## Capabilities

### New Capabilities
- `broker-key-persistence`: the broker signs with a durable key loaded from Vault Adapter or a mounted file, serves a stable multi-replica JWKS, and retains prior keys across rotation so previously-issued tokens still validate.
- `oidc-state-store`: OIDC PKCE login state is persisted in a shared TTL'd store so the auth-code flow survives admin-api restarts and multi-replica routing.
- `admin-ui-key-bootstrap`: the admin-ui signed-request keypair is generated at bootstrap and signed writes are enforced under `MINTKEY_ENV=production`.
- `db-role-secret-parameterization`: database app-role passwords are injected from secrets at migrate time, not embedded in a committed migration.

## Impact

- **Contracts / ADRs (edit first)**: new **ADR-0029** `docs/architecture/01-architecture/adr/0029-kubernetes-readiness-restart-safety.md` (broker key sourcing, OIDC state persistence, admin-ui key bootstrap, DB-role secret parameterization; restart/replica-safety guarantees) + `adrs/` symlink + `adr/README.md` index row. No REST/MCP wire-surface change (JWKS shape unchanged); the broker↔vault-adapter call reuses the existing vault gRPC surface.
- **DB**: Liquibase `oidc_login_state` table (new changeset, next free number); edit `015-app-role-passwords.yaml` to read a Liquibase property; SQLAlchemy mirror update.
- **Services**: broker (Go — key loader with Vault + file sources, keep `KeyRing` retention); admin-api (Python — OIDC state store repository + config; enforce signed writes in production); seed-job (Python — admin-ui keypair generation into bootstrap_secrets); vault-adapter (grant `svcid_broker` a signing-key read path if not already present).
- **Config**: new env — `MINTKEY_BROKER_SIGNING_KEY_FILE` (or vault identity for the broker), `MINTKEY_DB_APP_PASSWORD`, `MINTKEY_DB_SUBSCRIBER_PASSWORD`, `MINTKEY_OIDC_STATE_TTL_SECONDS`. Document in `.env.example`, `PORTS.md`/`docs/NETWORK.md`.
- **Tests**: broker — key loaded from file/vault; two brokers with the same key produce cross-validatable tokens; token issued before a simulated restart still validates against JWKS after reload. admin-api — OIDC state survives a simulated process swap; expired state rejected; signed-write enforcement on. seed-job — keypair generated once, idempotent, correct mode. DB — role password from property; RLS + sqlalchemy mirror gates green.
- **Out of scope**: the Helm chart / k8s manifests themselves (sibling `helm-chart` change); Keycloak HA; making Kong/proxy-plugin multi-replica beyond what already works; secret *storage backend* choices (KEK modes already support file mode — a deployment config concern, handled in `helm-chart`).

## Issue Intake (remediation gate)

1. **Problem statement**: Four core services hold restart-fatal in-process state (broker signing key, OIDC login state) or ship unprovisioned/hardcoded secrets (admin-ui keypair, DB role passwords), making any pod restart or multi-replica deployment break token validation, operator login, or write-auth.
2. **User-visible symptom**: After a broker restart, every agent's issued JWT is rejected (JWKS no longer contains its signing key); operator login intermittently fails behind >1 admin-api replica; admin API silently accepts unsigned writes; DB passwords can't be rotated without a code change.
3. **Expected behavior**: Broker restart/roll and ≥2 replicas keep previously-issued tokens valid; operator login survives restart/multi-replica; admin-ui writes require a real signature under production; DB role passwords come from injected secrets.
4. **Evidence**: `broker/cmd/broker/main.go:45-47`; `admin-api/.../auth/oidc.py:94,113,136`; `docs/AUTH.md:239` + `admin-ui/src/lib/signed-request.ts` with no generator in seed-job/install.sh/Makefile; `admin-api/db/changelog/015-app-role-passwords.yaml:9-10`.
5. **Scope**: ADR-0029; broker key loader + KeyRing retention; OIDC state store + Liquibase table; seed-job keypair gen + prod signed-write enforcement; DB-role password parameterization; env/docs; tests + gates.
6. **Out of scope**: see "Out of scope" above.
7. **Risk level**: HIGH — touches token-signing, auth-code login, and write-auth. Orchestrator pattern + independent review per chunk; no chunk merges without the restart/replica regression test proving the fix.
8. **Verification target**: repo validators green (`openspec validate kubernetes-readiness --strict`, openapi snapshot, RLS, sqlalchemy mirror, audit coverage) **plus** live proofs: (a) issue a token, `docker restart`/pod-restart the broker, the old token still validates; (b) two broker replicas' tokens cross-validate; (c) OIDC login completes across a simulated admin-api process swap; (d) production mode rejects an unsigned admin-ui write.
9. **Owner decisions**: broker key source priority = Vault Adapter first, mounted file fallback (both delivered); OIDC state store = Postgres (no new Redis dependency); confirm with reviewer before adding any new infra service.
