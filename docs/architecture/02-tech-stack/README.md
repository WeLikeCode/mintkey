# Iteration 2 — Tech stack

This is the **iteration‑2 dashboard**. It tracks every per‑container technology decision: what's already pinned, what's open as a proposal, and what remains to be ADR'd before iteration 2 closes.

Iteration 2's exit criterion (from the [iteration plan](../00-vision/05-iteration-plan.md)): *a `docker-compose.yml` could be written from the docs alone*. We close iteration 2 when every cell in the matrices below is filled with an ADR reference.

## Stack matrix — decided

| Container / concern                | Choice                                                        | Source ADR / proposal |
|------------------------------------|---------------------------------------------------------------|------------------------|
| **Egress Proxy (D1)**              | Kong Gateway DB‑less                                          | [ADR‑0004](../01-architecture/adr/0004-egress-proxy-kong.md) |
| **Egress Proxy plugin**            | Go + `go-pdk` (shared Go stack)                                | [ADR‑0004](../01-architecture/adr/0004-egress-proxy-kong.md), [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md) |
| **Kong‑syncer**                    | Go (shared Go stack)                                          | [ADR‑0004](../01-architecture/adr/0004-egress-proxy-kong.md), [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md) |
| **Credential Broker (C5)**         | Go + `go-jose/v4` (Ed25519); shared Go stack                   | [ADR‑0006](../01-architecture/adr/0006-token-format-and-binding.md), [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md) |
| **Vault Adapter (C6)**             | Go + AES‑256‑GCM + pure‑Go SQLite; shared Go stack             | [ADR‑0003](../01-architecture/adr/0003-credential-storage-strategy.md), [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md) |
| **Admin REST API (C2)**            | Python 3.12 + FastAPI + SQLAlchemy 2.x async + Pydantic v2     | [ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md), [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md) |
| **MCP Server (C4)**                | Python 3.12 + Anthropic `mcp` SDK; shared `mintkey-models`     | [ADR‑0009](../01-architecture/adr/0009-mcp-server-stack-python.md), [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md) |
| **Admin Console (C1)**             | AdminJS 7.x (Node 20 + Express + `@adminjs/sql` + `passport-openidconnect`) | [ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md), [ADR‑0013](../01-architecture/adr/0013-adminjs-pin.md) |
| **Admin REST API DB driver**       | `asyncpg`                                                     | [ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md), [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md) |
| **DB engine**                      | PostgreSQL 16                                                 | [ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md) |
| **Schema migrations**              | Liquibase, YAML changelogs                                    | [ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md) |
| **Authentication (operator)**      | Generic OIDC; Keycloak default IdP; `authlib` Python; `passport-openidconnect` Node; Argon2id internal fallback | [ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md), [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md), [ADR‑0013](../01-architecture/adr/0013-adminjs-pin.md) |
| **Authentication (agent)**         | Agent API Key, hashed at rest, constant‑time compare           | [ADR‑0005](../01-architecture/adr/0005-admin-tech-stack.md), [ADR‑0006](../01-architecture/adr/0006-token-format-and-binding.md) |
| **Vault Adapter v1 backend**       | Encrypted SQLite file on externally mounted volume             | [ADR‑0003](../01-architecture/adr/0003-credential-storage-strategy.md), [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md) |
| **Token format (agent)**           | JWS Ed25519 JWT with `tnt` claim                              | [ADR‑0006](../01-architecture/adr/0006-token-format-and-binding.md), [ADR‑0008](../01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md) |
| **Proxy URL form**                 | Explicit `/v1/call/<svc>/<path>` + virtual‑host alias         | [ADR‑0007](../01-architecture/adr/0007-proxy-deployment-topology.md) |
| **Tenancy isolation**              | Row‑level + Postgres RLS by default; DB‑per‑tenant opt‑in     | [ADR‑0008](../01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md) |
| **Change channel transport**       | Postgres `LISTEN/NOTIFY`; tenant‑scoped channels              | [ADR‑0010](../01-architecture/adr/0010-change-channel-postgres-listen-notify.md) |
| **Logging**                        | Go `slog` JSON; Python `structlog` JSON; Node `pino` JSON      | [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md), [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md), [ADR‑0013](../01-architecture/adr/0013-adminjs-pin.md) |
| **Linting & types**                | `golangci-lint` (Go); `ruff` + `mypy --strict` (Python); `eslint` + TS strict (Node) | [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md), [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md), [ADR‑0013](../01-architecture/adr/0013-adminjs-pin.md) |
| **Testing**                        | Go `testing` + testify + testcontainers‑go; Python `pytest` + testcontainers; Node `vitest` + supertest | [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md), [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md), [ADR‑0013](../01-architecture/adr/0013-adminjs-pin.md) |
| **Package management**             | Go modules + Renovate; `uv` (Python); `pnpm` (Node)            | [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md), [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md), [ADR‑0013](../01-architecture/adr/0013-adminjs-pin.md) |

## Stack matrix — open (iteration 2 closing)

| Container / concern                | Status                                          | Where |
|------------------------------------|--------------------------------------------------|--------|
| ~~Credential Broker (C5) stack~~   | ✅ Pinned                                        | [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md) |
| ~~Vault Adapter v1 (C6) stack~~    | ✅ Pinned                                        | [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md) |
| ~~OIDC libraries (Python)~~        | ✅ `authlib` chosen                              | [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md) |
| ~~Python DB pattern~~              | ✅ SQLAlchemy 2.x async                          | [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md) |
| ~~AdminJS pin set~~                | ✅ Pinned                                        | [ADR‑0013](../01-architecture/adr/0013-adminjs-pin.md) |
| ~~Test stack per language~~        | ✅ Pinned                                        | [ADR‑0011](../01-architecture/adr/0011-shared-go-stack.md), [ADR‑0012](../01-architecture/adr/0012-python-stack-pin.md), [ADR‑0013](../01-architecture/adr/0013-adminjs-pin.md) |
| **Audit Service (C7)** placement   | OPEN — in‑process with Admin API for v1 (implicit in ADR‑0005); upgrade to its own service later. Small ADR if needed. | n/a |
| **Observability detail**           | OPEN — span naming, attribute allowlist, sampling | new ADR after iteration 4 contracts stabilize |

## Stack matrix — explicitly deferred (post‑iteration‑2)

- HashiCorp Vault backend (Vault Adapter v2) — Phase 2 / [ADR‑0003](../01-architecture/adr/0003-credential-storage-strategy.md) follow‑up.
- SQL+KMS backend (Vault Adapter v3) — Phase 2 / [ADR‑0003](../01-architecture/adr/0003-credential-storage-strategy.md) follow‑up.
- gRPC, WebSockets, SSE, MCP‑to‑MCP — Phase 3 / [ADR‑0007](../01-architecture/adr/0007-proxy-deployment-topology.md) follow‑up.
- Per‑tenant KEK — Phase 2 / [ADR‑0008](../01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md) follow‑up.
- HTTP/3 — Phase 2.

## Iteration 2 plan

### Sequencing
1. ~~**Settle P‑008 (MCP Server)**~~ — Done. Python + Anthropic `mcp` SDK ([ADR‑0009](../01-architecture/adr/0009-mcp-server-stack-python.md)).
2. ~~**Settle P‑009 (change channel)**~~ — Done. Postgres `LISTEN/NOTIFY` ([ADR‑0010](../01-architecture/adr/0010-change-channel-postgres-listen-notify.md)).
3. **Pin the shared Go stack** — Broker, Vault Adapter, Kong‑syncer, Egress Proxy plugin share the same Go base; one ADR pins the shared libraries (logger, OTel SDK, gRPC server, JWT lib, encryption lib, Postgres driver, change‑channel client) and a tiny per‑container ADR can add anything specific.
4. **Pin the Python stack** — appendix ADR to ADR‑0005 / ADR‑0009 finalizing the OIDC client lib, sessions lib, audit emission helper, DB pattern (`sqlc`‑style vs. SQLAlchemy 2.x), test stack.
5. **Pin the AdminJS stack** — appendix ADR to ADR‑0005 finalizing the AdminJS resources, the Postgres adapter, the OIDC integration.
6. **Audit Service placement** — small ADR: in‑process with Admin API for v1; promote to its own service when warranted.
7. **Observability detail** — span names, metric names, allowed attributes; this depends on the contract surface so it lands after iteration 4 starts.

### Iteration 2 exit criteria
- Every cell in the "open" matrix above resolves to an ADR.
- Every cell in the "decided" matrix has a pinned library version (recorded in the ADR).
- A reviewer can read iteration‑2 ADRs end‑to‑end and write a credible `docker-compose.yml`.
- The [Kiro readiness](../00-vision/07-kiro-readiness.md) "coding conventions" row gains a per‑language entry.

## Cross‑cutting principles for every iteration‑2 ADR
- **Pin a version**, not a range. Renovate handles drift.
- **Record the rationale in the ADR**, not just the choice. "Why this lib over the obvious alternative" is what makes the ADR valuable.
- **Note the test posture**: which test framework, which fixtures, which stubs.
- **Note the OTel posture**: which auto‑instrumentation, which manual spans.
- **Note the multi‑tenancy posture**: where `tenant_id` enters/exits, which middleware sets `app.current_tenant`.
