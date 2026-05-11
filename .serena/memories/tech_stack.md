# Tech Stack

## Python services (admin-api, mcp-server, mock-backend)
- Python 3.12
- FastAPI + Pydantic v2 (extra="forbid" on request models)
- SQLAlchemy 2.x async + asyncpg
- Argon2id (argon2-cffi) for key hashing
- authlib for OIDC/JWT
- structlog for structured logging
- httpx for async HTTP client calls
- uvicorn as ASGI server
- uv as package manager (but requirements.txt for Docker builds)
- ruff for linting/formatting
- mypy --strict for type checking
- pytest + pytest-asyncio for testing

## Go services (vault-adapter, broker, kong-syncer, proxy-plugin)
- Go 1.22, workspace layout (go.work at repo root)
- pgx/v5 for PostgreSQL
- chi/v5 for HTTP routing
- go-jose/v4 for JWT
- sqlc for SQL codegen
- slog for structured logging
- modernc.org/sqlite for vault-adapter (SQLite credential store)
- grpc-go for vault-adapter gRPC server
- distroless base images

## Admin UI
- AdminJS 7.x + Express
- @adminjs/sql adapter
- passport-openidconnect
- connect-pg-simple
- pino for logging
- vitest for testing
- pnpm (workspace with pnpm-workspace.yaml)

## Infrastructure
- PostgreSQL 16 (RLS enforced; migrations via Liquibase 4.27)
- Kong 3.6 DB-less mode
- Keycloak 24 for OIDC
- OTel Collector + Jaeger + Prometheus + Grafana
- Docker Compose (15 long-running services + 2 one-shot jobs)

## Key package locations
- Shared Python models: `mintkey-models/mintkey_models/`
- Admin API: `admin-api/src/admin_api/`
- MCP Server: `mcp-server/src/mcp_server/`
- Mock backend: `mock-backend/src/mock_backend/rest/main.py`
- Go workspace root: repo root (`go.work`)
- Go services: `services/{vault-adapter,broker,kong-syncer,proxy-plugin}/`
- DB changelogs: `admin-api/db/changelog/`
