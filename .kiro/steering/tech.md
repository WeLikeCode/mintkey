# Tech Stack

Pinned choices for Mintkey. All decisions have an ADR. Do not introduce new tools without an ADR.

## Languages

| Component | Language | Version |
|---|---|---|
| Credential Broker, Vault Adapter, Kong-syncer, Proxy plugin | Go | 1.22+ |
| Admin REST API, MCP Server | Python | 3.12+ |
| Admin Console | Node.js | 20 |

## Go services — shared library set (ADR-0011)

| Concern | Library |
|---|---|
| HTTP routing | `go-chi/chi/v5` |
| Postgres driver | `jackc/pgx/v5` |
| Type-safe queries | `sqlc` |
| JWT sign + verify | `go-jose/go-jose/v4` (EdDSA Ed25519) |
| Encryption | stdlib `crypto/cipher` AES-256-GCM |
| Vault file backend | `modernc.org/sqlite` (pure Go, no CGO) |
| OTel SDK | `go.opentelemetry.io/otel` + otelhttp + otelgrpc + otelpgx |
| Logger | stdlib `log/slog` JSON handler |
| Config | `caarlos0/env/v10` |
| ULID | `oklog/ulid/v2` |
| Testing | stdlib `testing` + `stretchr/testify` + `testcontainers-go` |
| Linting | `golangci-lint` (errcheck, goimports, revive, gosec) |
| Container image | `gcr.io/distroless/static-debian12:nonroot` |

## Python services — shared library set (ADR-0012)

| Concern | Library |
|---|---|
| Web framework | FastAPI |
| ASGI server (prod) | gunicorn + uvicorn workers |
| Validation | Pydantic v2 |
| DB driver | `asyncpg` |
| ORM | SQLAlchemy 2.x async (`Mapped` types) |
| OIDC client | `authlib` |
| Sessions | `starlette-sessions` + `itsdangerous` |
| Password hashing | `argon2-cffi` (Argon2id) |
| Logger | `structlog` JSON |
| OTel | `opentelemetry-instrumentation-fastapi` + asyncpg + sqlalchemy |
| MCP SDK | `mcp` (Anthropic Python SDK) |
| Testing | `pytest` + `pytest-asyncio` + `httpx` + `testcontainers` |
| Linting | `ruff` + `mypy --strict` |
| Package manager | `uv` |

## Node / AdminJS (ADR-0013)

| Concern | Library |
|---|---|
| Admin framework | AdminJS 7.x |
| HTTP server | `@adminjs/express` |
| DB adapter | `@adminjs/sql` |
| Auth | `passport-openidconnect` |
| Sessions | `connect-pg-simple` |
| Logger | `pino` |
| Testing | `vitest` + `supertest` |
| Package manager | `pnpm` |

## Infrastructure

| Component | Choice | ADR |
|---|---|---|
| Database | PostgreSQL 16 | ADR-0005 |
| Schema migrations | Liquibase (YAML changelogs) | ADR-0015 |
| Egress proxy | Kong Gateway DB-less | ADR-0004 |
| Identity provider | Keycloak (default); any OIDC-compliant IdP | ADR-0005 |
| Change channel | Postgres `LISTEN/NOTIFY` | ADR-0010 |
| Token format | JWS Ed25519 JWT, 10-min default TTL | ADR-0006 |
| Credential storage v1 | Encrypted SQLite on mounted volume (AES-256-GCM) | ADR-0003 |
| Observability | OTel Collector → Jaeger (traces) + Prometheus (metrics) + Grafana | ADR-0005 |

## Deferred (post-MVP)

- HashiCorp Vault backend (Vault Adapter v2) — Phase 2
- SQL + KMS backend (Vault Adapter v3) — Phase 2
- Kubernetes Helm chart — Phase 2
- gRPC / WebSocket / MCP-to-MCP — Phase 3
- Per-tenant KEK — Phase 2
