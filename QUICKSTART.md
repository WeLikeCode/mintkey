# Mintkey — Developer Quickstart

Mintkey is an AI credential broker. Operators register backend services with credentials. Agents discover services via MCP, request short-lived JWTs, and call services through Kong (which injects real credentials in-flight). Multi-tenant by architecture.

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Docker + Compose | v24+ | `brew install docker` |
| Go | 1.22+ | `brew install go` |
| Python | 3.12 | `brew install python@3.12` |
| uv | latest | `pip install uv` |
| Node.js + pnpm | 20+ / 8+ | `brew install node && npm i -g pnpm` |
| protoc | 3.x | `brew install protobuf` |

---

## 1. Start the full stack

```bash
# Clone and enter the repo
git clone https://github.com/WeLikeCode/mintkey.git mintkey && cd mintkey

# Start all services (Postgres, Vault Adapter, Broker, Kong, MCP, Admin API, Admin UI, Jaeger, Prometheus)
docker compose up -d

# Wait for health checks (~60 s)
docker compose ps   # all containers should be "healthy"
```

The seed job runs automatically on first start and bootstraps:
- Default tenant `t_default`
- Platform admin operator (password written to `data/bootstrap-secrets/admin_password`)
- 4 service-identity boot secrets
- AdminJS Ed25519 keypair
- Broker Ed25519 signing keypair
- Genesis audit event

```bash
# View the bootstrap admin password
docker run --rm -v mintkey_bootstrap_secrets:/secrets alpine cat /secrets/admin_password
```

---

## 2. Access the services

| Service | URL | Notes |
|---|---|---|
| Admin UI (AdminJS) | http://localhost:8081 | Sign in with Keycloak (see docs/AUTH.md) |
| Admin API | http://localhost:8080/v1 | REST API |
| Admin API docs | http://localhost:8080/docs | FastAPI OpenAPI UI |
| MCP Server | http://localhost:8082 | MCP endpoint for agents |
| Kong proxy | http://localhost:8000 | Brokered call entry point |
| Jaeger | http://localhost:16686 | Distributed traces |
| Prometheus | http://localhost:9090 | Metrics |

Deploying Mintkey on a LAN or behind a reverse proxy? See [docs/NETWORK.md](docs/NETWORK.md) for the env-var setup (`MINTKEY_MCP_PUBLIC_URL` / `MINTKEY_PROXY_PUBLIC_URL`).

---

## 3. Run the test suite

### Quick unit tests (no Docker required)

```bash
make test-unit
```

This runs:
- Python unit tests (`tests/unit/`)
- Go unit tests (`go test ./...`)

### Architecture tests (no Docker required)

```bash
make test-arch
```

Validates:
- RLS coverage (100% of tenant-scoped tables have policy)
- No SQL injection patterns (no f-string SQL)
- Audit chokepoint (every write handler calls `audit_emit`)
- OpenAPI parity (FastAPI output vs. checked-in YAML)
- SQLAlchemy mirror diff (Liquibase vs. `mintkey_models/db.py`)

### Full test suite

```bash
make test
```

### Integration tests (requires Docker)

```bash
MINTKEY_INTEGRATION_TEST=true make test-integration
```

Integration tests use testcontainers (Postgres, Vault Adapter) and cover:
- Credential rotation propagation (≤ 30 s)
- Agent revocation propagation (≤ 5 s)
- Token issuance p99 ≤ 50 ms
- Proxy latency p50 ≤ 10 ms, p99 ≤ 30 ms

---

## 4. Run the E2E smoke test

```bash
make smoke
```

Runs the full E2E-01 builder happy path against the running stack:
1. Bootstrap + login
2. Register mock backend service
3. Register API key credential
4. Run service test (validates connectivity)
5. Create agent + grant permissions
6. MCP discovery (`list_services`)
7. Token request (`request_token`)
8. Brokered call through Kong
9. Audit log verification (9 expected event types)
10. Jaeger trace verification (5 expected spans)
11. Red-team grep (zero plaintext credentials in logs/spans)

Requires `docker compose up -d` first.

---

## 5. Development workflow

### Admin API (Python/FastAPI)

```bash
cd admin-api
uv sync
uv run uvicorn admin_api.main:app --reload --port 8080
```

Run tests:
```bash
uv run pytest tests/unit/admin_api/ -v
```

### MCP Server (Python/FastAPI)

```bash
cd mcp-server
uv sync
uv run uvicorn mcp_server.main:app --reload --port 8082
```

### Vault Adapter + Broker + Kong-syncer + Proxy Plugin (Go)

```bash
# From repo root (Go workspace)
go build ./apps/vault-adapter/...
go build ./apps/broker/...
go build ./apps/kong-syncer/...
go build ./apps/proxy-plugin/...

# Run all Go tests
go test ./... -v
```

### mintkey-models (shared Python library)

```bash
cd mintkey-models
uv sync
uv run pytest tests/ -v
```

### Admin UI (TypeScript/AdminJS)

```bash
cd admin-ui
pnpm install
pnpm dev    # development server on :3001
pnpm test   # vitest unit tests
pnpm build  # production build
```

---

## 6. Linting

```bash
make lint
```

Runs:
- Python: `ruff check` + `mypy --strict`
- Go: `golangci-lint run`
- TypeScript: `eslint --max-warnings=0`
- YAML: OpenAPI spec validator + MCP tools YAML lint

---

## 7. Adding a new auth scheme

See `CLAUDE.md` → "How to add an X (pattern library)". The key files to touch:
1. `docs/architecture/contracts/vault-adapter/vault.proto` — add enum value
2. `apps/proxy-plugin/internal/credential/injector.go` — add injection case (≤ 3 files per S-MOD-1)
3. `mintkey_models/schemas.py` — add enum value
4. `apps/admin-api/src/admin_api/api/services.py` — update validation
5. Write test first for the injector

---

## 8. Database schema changes

Liquibase is the source of truth (ADR-0015). **Never add a column in SQLAlchemy.**

```bash
# 1. Write a new Liquibase changeset
vim apps/admin-api/db/changelog/011-new-column.yaml

# 2. Apply migrations (local Postgres)
docker compose run --rm liquibase update

# 3. Regenerate SQLAlchemy mirror
sqlacodegen --generator declarative postgresql://mintkey_app:...@localhost:5432/mintkey > /tmp/mirror.py
diff packages/python/mintkey-models/mintkey_models/db.py /tmp/mirror.py  # must be empty

# 4. Update the Pydantic model if needed
# 5. Run the RLS coverage test
pytest tests/architecture/test_rls_coverage.py -v
```

---

## 9. Troubleshooting

**Services not starting**: Check `docker compose logs <service>`. Common issues:
- Postgres not ready: seed job retries up to 30 times
- Vault Adapter KEK missing: set `MINTKEY_VAULT_KEK_FILE` or `MINTKEY_VAULT_KEK_B64`
- AdminJS private key missing: run `docker compose run --rm seed-job`

**Audit chain verification fails**: Run `POST /v1/admin/audit/verify-chain?tenant_id=<tid>` with `X-Platform-Admin: true` header to diagnose.

**Port conflicts**: Edit `docker-compose.yml` to change host-side ports. Internal ports must not change.

**Go workspace issues**: `go work sync` from repo root resolves most module issues.

---

## 10. Architecture reference

- `docs/architecture/` — 20 ADRs (18 Accepted, ADR-0018 Proposed), contracts, flows, threat model
- `CLAUDE.md` — operating principles and guardrails for Claude Code sessions
- `AGENTS.md` — verification commands and Mintkey-specific anti-patterns
- `.kiro/specs/mintkey-mvp/tasks.md` — Phase 1 task list with Exit Criteria Checklist
