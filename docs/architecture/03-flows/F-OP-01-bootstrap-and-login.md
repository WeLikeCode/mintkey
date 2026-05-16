# F‑OP‑01 — Operator bootstrap and first login

## Goal
A new Mintkey deployment provisions a default tenant, a bootstrap admin operator (with internal auth), and a Keycloak realm; the operator logs in and reaches the AdminJS dashboard.

## Actors
- **Builder / Operator** (human, browser)
- **Compose runtime** (`docker compose up`)
- **seed‑job** (one‑shot container)
- **Postgres**, **Keycloak**, **AdminJS**, **Admin API**

## Pre‑conditions
- Docker + compose installed.
- Repo cloned; `.env` defaults (or operator‑provided overrides) present.
- No prior state on Postgres volume or `./data/bootstrap-secrets` host file.

## Post‑conditions
- DB schema applied via Liquibase ([ADR‑0015](../01-architecture/adr/0015-liquibase-schema-source-of-truth.md)).
- Tenant `t_default` row created.
- Operator row with `role=Admin` + Argon2id‑hashed password.
- Keycloak realm `mintkey` imported with the `mintkey-admin` client.
- Bootstrap password printed to compose logs and written to `./data/bootstrap-secrets` (mode 0400).
- `tenant.bootstrap_completed` audit event emitted.
- Admin API health endpoint returns 200.
- Operator successfully logs in via Keycloak OIDC (ADR-0020); internal-login is the break-glass path only.

## Sequence diagram — bootstrap

```mermaid
sequenceDiagram
    actor Builder
    participant Compose
    participant Seed as seed-job
    participant DB as Postgres
    participant KC as Keycloak
    participant API as Admin API
    participant FS as Host filesystem

    Builder->>Compose: docker compose up
    Compose->>DB: start postgres
    DB-->>Compose: ready
    Compose->>KC: start keycloak
    KC-->>Compose: ready
    Compose->>Seed: start (depends_on Postgres + Keycloak)
    Seed->>DB: liquibase update
    Note over DB: schema, RLS policies, mintkey_app + mintkey_migrate roles
    Seed->>DB: INSERT tenants (id, slug=t_default, display_name)
    Seed->>Seed: generate 32-byte random password
    Seed->>Seed: argon2id hash the password
    Seed->>DB: INSERT operators (role=Admin, hashed password, oidc_sub=null)
    Seed->>KC: POST realm export realm-mintkey.json
    KC-->>Seed: realm imported
    Seed->>DB: INSERT audit tenant.bootstrap_completed
    Seed->>FS: write ./data/bootstrap-secrets (mode 0400)
    Seed->>Compose: log: bootstrap admin user and password
    Seed-->>Compose: exit 0
    Compose->>API: start admin-api
    API->>API: load Vault Adapter boot secret from /run/secrets
    API->>DB: SELECT 1 (readiness check)
    API-->>Builder: GET /v1/health → 200
```

## Sequence diagram — First login — Keycloak OIDC (primary)

> Full OIDC flow detail and token-validation sequence: [`docs/AUTH.md`](../../AUTH.md).

```mermaid
sequenceDiagram
    participant Browser
    participant UI as admin-ui
    participant API as admin-api
    participant KC as Keycloak

    Browser->>UI: GET /admin (no session)
    UI->>Browser: 302 /admin/login
    Browser->>UI: GET /admin/login (Keycloak button)
    Browser->>UI: GET /auth/start
    UI->>Browser: 302 admin-api /v1/auth/oidc/login
    Browser->>API: GET /v1/auth/oidc/login
    API->>Browser: 302 Keycloak (PKCE)
    Browser->>KC: login
    KC->>Browser: 302 admin-api callback (code, state)
    Browser->>API: GET /v1/auth/oidc/callback
    API->>KC: token exchange + JWKS verify
    API->>Browser: 302 /admin (sets mintkey_session)
    Note over UI,API: requireSession → /v1/auth/whoami
```

## Sequence diagram — Break-glass login (internal-auth)

> Requires `mintkey admin reset-password` to enable. Use only when Keycloak is unavailable.

```mermaid
sequenceDiagram
    actor Builder
    participant UI as AdminJS
    participant API as Admin API
    participant DB as Postgres

    Builder->>UI: open https://localhost:8081
    UI-->>Builder: redirect to /login (no session cookie)
    Builder->>UI: select "Internal auth (bootstrap)"
    Builder->>UI: enter username "admin@local" + bootstrap password
    UI->>API: POST /v1/auth/internal-login (signed JWT envelope per ADR-0014.6)
    API->>DB: SELECT operators WHERE username = $1
    API->>API: argon2id verify password (constant time)
    alt password valid
        API->>DB: BEGIN, SET LOCAL app.current_tenant = t_default
        API->>DB: INSERT sessions (operator_id, tenant_id, expires_at)
        API->>DB: INSERT audit auth.login.success
        API->>DB: COMMIT
        API-->>UI: Set-Cookie mintkey_session, 200 OK { tenant_id, role }
        UI-->>Builder: redirect to /dashboard
    else password invalid
        API->>DB: INSERT audit auth.login.failed
        API-->>UI: 401 (constant-time response)
        UI-->>Builder: error message
    end
```

## Quality attribute scenarios touched
- [S‑SEC‑1](../01-architecture/03-quality-attributes.md) — bootstrap password is shown only on first run; written to `./data/bootstrap-secrets` 0400.
- [S‑AUD‑1](../01-architecture/03-quality-attributes.md) — all login attempts (success + failure) audited.
- [S‑MT‑2](../01-architecture/03-quality-attributes.md) — tenant onboarding timing (compose up to operator dashboard) ≤ 60 s on a warm cache.

## Failure modes
| Failure | Detection | Behavior |
|---------|-----------|----------|
| Liquibase migration syntax error | seed‑job exits non‑zero | compose halts; operator inspects logs and fixes the changelog |
| Postgres unreachable when seed starts | seed connection retry then fail | `depends_on: condition: service_healthy` ensures DB ready first |
| Keycloak realm import fails | seed log | seed continues (internal auth works); OIDC unavailable until repair |
| Bootstrap password file already exists | seed detects, refuses | operator must rotate via the `seed --rotate-bootstrap` subcommand to avoid silent overwrite |
| Wrong password on login | Argon2id verify | `auth.login.failed` audit; 401 with constant‑time delay |
| Argon2id parameters too high | login slow | doc the recommended params (memory 64 MiB, iterations 3, parallelism 4) |

## Test plan

### Unit tests
- `seed.generate_bootstrap_password` returns 32 random bytes; Argon2id hashing roundtrip.
- `auth.internal_login` handler: valid/invalid password, locked operator, deleted operator.
- Liquibase changelog hash stable.
- RLS policy applied on every domain table (the architecture test from [ADR‑0014.8](../01-architecture/adr/0014-iter-1-2-corrections.md)).

### Integration tests (testcontainers)
- Spin Postgres + run Liquibase → assert all expected tables, columns, RLS policies, roles.
- Spin Postgres + Keycloak + admin‑api + seed‑job → assert seed completes, operator row exists, audit event emitted, Keycloak realm imported.
- Spin everything + admin‑ui → POST `/v1/auth/internal-login` with bootstrap creds → assert 200 + cookie + audit row.

### Live smoke
- Part of E2E‑01 Phase 1 + Phase 2.

## Kiro spec inputs

Contracts touched:
- OpenAPI: `POST /v1/auth/internal-login`, `GET /v1/auth/whoami`, `POST /v1/auth/logout` ([`docs/contracts/rest/openapi.yaml`](../contracts/rest/openapi.yaml)).
- Audit events: `tenant.bootstrap_completed`, `auth.login.success`, `auth.login.failed.user_unknown`, `auth.login.failed.bad_password`, `auth.login.failed.account_locked`, `auth.logout` ([`docs/contracts/events/audit-event.schema.json`](../contracts/events/audit-event.schema.json)).
- Internal: Liquibase changelogs at `admin-api/db/changelog/`; Keycloak realm export at `seed/keycloak/realm-mintkey.json`.

Components implementing this flow:
- `seed-job` (Python or Go small one‑shot)
- `admin-api` (Python, FastAPI handlers `auth.internal_login`)
- `admin-ui` (AdminJS, login page + Custom Action to call FastAPI)

For each, Kiro generates:
- **Requirements** — derived from "Goal" + "Pre/Post‑conditions" above. Acceptance criteria mapped to S‑SEC‑1, S‑AUD‑1, S‑MT‑2.
- **Design** — internal modules: `seed.bootstrap`, `seed.keycloak_import`, `auth.internal_login`. References [ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md), [ADR‑0008](../01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md), [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md), [ADR‑0014](../01-architecture/adr/0014-iter-1-2-corrections.md), [ADR‑0015](../01-architecture/adr/0015-liquibase-schema-source-of-truth.md), [ADR‑0016](../01-architecture/adr/0016-round-2-corrections.md).
- **Tasks** — TDD sequence:
  1. Write seed‑job test asserting Liquibase migrations apply and tables exist.
  2. Implement `seed.bootstrap` to make the test pass.
  3. Write integration test for Keycloak realm import.
  4. Implement `seed.keycloak_import`.
  5. Write `auth.internal_login` failing test (returns 401 for unknown user).
  6. Implement until pass.
  7. Add audit‑emission tests (success and failure).
  8. Add the architecture test (RLS coverage) and the migration‑driven SQLAlchemy diff test.
  9. Refactor for shared logger / OTel.
