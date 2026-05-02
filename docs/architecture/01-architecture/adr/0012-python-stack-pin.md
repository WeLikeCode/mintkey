# ADR‑0012: Python stack pin for Admin REST API and MCP Server

## Status
Accepted — 2026-05-10. Appendix to [ADR‑0005](0005-admin-tech-stack.md) and [ADR‑0009](0009-mcp-server-stack-python.md).

## Context
Two Mintkey services are Python:
- **Admin REST API (C2)** per [ADR‑0005](0005-admin-tech-stack.md).
- **MCP Server (C4)** per [ADR‑0009](0009-mcp-server-stack-python.md).

They share Pydantic models (via `mintkey-models`), DB driver, OTel SDK, OIDC client, password hashing, and session machinery. This ADR pins the shared library set and resolves the open library choices flagged in ADR‑0005 and ADR‑0009.

## Decision

### Pinned libraries

| Concern              | Choice                                                                              | Rationale |
|----------------------|--------------------------------------------------------------------------------------|-----------|
| Python version       | **3.12+**                                                                            | Already in ADR‑0005; modern type system; `asyncio` matures |
| Web framework        | **FastAPI**                                                                          | Already in ADR‑0005 |
| ASGI server (dev)    | **uvicorn**                                                                          | FastAPI default |
| ASGI server (prod)   | **gunicorn** with uvicorn workers                                                    | Process model + auto‑restart |
| Validation           | **Pydantic v2**                                                                      | Already in ADR‑0005 |
| DB driver            | **`asyncpg`**                                                                        | Already in ADR‑0005; native async; fast; supports `LISTEN/NOTIFY` |
| ORM / query layer    | **SQLAlchemy 2.x async** with `Mapped` types                                          | Most idiomatic Python; pairs with Pydantic v2; shared schema for both services |
| Migrations           | **Liquibase** (already in ADR‑0005)                                                  | Language‑agnostic; runs as a one‑shot job |
| OIDC client          | **`authlib`**                                                                        | More mature than `oauthlib`; FastAPI‑friendly |
| Sessions             | **`starlette-sessions`** + DB‑backed session store via SQLAlchemy + `itsdangerous` for cookie signing | Server‑side session storage; HttpOnly Secure SameSite=Strict cookie |
| CSRF                 | **`fastapi-csrf-protect`** (or Starlette CSRF middleware)                            | Standard for state‑changing endpoints |
| Password hashing     | **`argon2-cffi`** (Argon2id)                                                         | OWASP recommendation |
| Logging              | **`structlog`** with stdlib bridge → JSON output                                      | Structured; OTel‑correlated; pairs with `slog` JSON in Go services |
| OTel                 | `opentelemetry-instrumentation-fastapi` + `opentelemetry-instrumentation-asyncpg` + `opentelemetry-instrumentation-sqlalchemy` + `opentelemetry-sdk` | Auto‑instrumentation across the FastAPI + DB stack |
| MCP SDK              | **`mcp`** (Anthropic Python SDK)                                                     | Already in ADR‑0009 |
| Change‑channel client| `mintkey.changes` (small wrapper around `asyncpg` `add_listener`)                    | Per [ADR‑0010](0010-change-channel-postgres-listen-notify.md) |
| Testing              | **`pytest`** + `pytest-asyncio` + `httpx` + `testcontainers`                         | Real Postgres + Keycloak via testcontainers |
| Linting              | **`ruff`** (replaces flake8, isort, black) + `mypy --strict`                         | Modern, fast |
| Type checking        | **`mypy --strict`**                                                                  | No implicit `Any`; aggressive |
| Package management   | **`uv`** (Astral)                                                                    | Fastest installer; modern; replaces pip+pip‑tools or poetry |
| Project layout       | **src layout** with `pyproject.toml` per service; uv workspace at repo root          | Standard; supports the shared `mintkey-models` package |

### Shared `mintkey-models` package
- Pydantic models for `Tenant`, `Operator`, `OperatorTenantMembership`, `Service`, `Credential`, `Agent`, `PermissionGrant`, `AuditEvent`, `ChangeEvent`, `Session`.
- Models are shared between Admin REST API and MCP Server.
- SQLAlchemy `Mapped` classes mirror the Pydantic models (single source of truth for fields). The mapping uses `pydantic-sqlalchemy` patterns (or hand‑mirrored for clarity at our scale).
- Published as a local workspace package via `uv` workspace.

### Project layout (Python services in the repo)

```
pyproject.toml              # uv workspace root
.python-version             # 3.12
admin-api/
  pyproject.toml
  src/admin_api/
    main.py                 # FastAPI app
    api/                    # routers
    services/               # business logic; calls Vault Adapter, Audit, etc.
    db/                     # SQLAlchemy models, session, migrations runner
    auth/                   # OIDC + sessions + internal-auth fallback
    audit/                  # audit emission helper
    middleware/             # tenant context, OTel, CSRF
  db/changelog/             # Liquibase YAML changelogs
  tests/
mcp-server/
  pyproject.toml
  src/mcp_server/
    main.py                 # mcp SDK app
    tools/                  # one file per MCP tool
    auth/                   # Bearer Agent API Key handler
    db/                     # SQLAlchemy session
    middleware/             # tenant context, OTel
  tests/
mintkey-models/             # shared package
  pyproject.toml
  src/mintkey_models/
    __init__.py
    schemas.py              # Pydantic v2 models
    sql.py                  # SQLAlchemy 2.x Mapped types
```

### Code style
- `ruff` config: line length 100; checks: `E`, `F`, `I`, `B`, `C4`, `SIM`, `UP`, `RUF`, `S` (security).
- `mypy --strict`; no `Any`; explicit `Optional`.
- Async‑first; sync code only when integrating with sync libs.

### Multi‑tenancy
- Per [ADR‑0008](0008-multi-tenancy-row-level-with-db-tier.md), every DB transaction in either Python service issues `SET LOCAL app.current_tenant = '<uuid>'` at the start. A FastAPI middleware (Admin API) and an MCP tool middleware (MCP Server) handle this uniformly. RLS is the safety net.
- The application uses the `mintkey_app` Postgres role; the migration role is reserved for Liquibase.

## Consequences

### Positive
- Two Python services share one library set → faster onboarding; consistent upgrades.
- `uv` is dramatically faster than pip+poetry; better DX for CI.
- SQLAlchemy 2.x async is the modern Python idiom; pairs cleanly with Pydantic v2.
- `authlib` is the de‑facto Python OIDC choice and is FastAPI‑friendly.
- `argon2-cffi` is the right password hashing for the internal‑auth fallback.
- Shared `mintkey-models` eliminates the "two implementations of the same model" tax.

### Costs
- SQLAlchemy 2.x has a learning curve compared to raw SQL.
- ORM adds a dependency on the SQLAlchemy upgrade cadence (their async layer is stable but new).

### Risks
- `mcp` SDK pace (per [ADR‑0009](0009-mcp-server-stack-python.md) risks).
- `ruff` is rapidly evolving; rules may change between versions. Mitigation: pin `ruff` per release.

## Implications
- Both Python services build the same Docker image base (`python:3.12-slim` with `uv`‑installed deps).
- Both use the same `audit` helper and the same `mintkey.changes` client.
- Both share the `mintkey-models` package as a workspace dependency.
- `Liquibase` runs as a one‑shot job in compose before the Admin API container starts (per [ADR‑0005](0005-admin-tech-stack.md)).

## Open follow‑ups
- Specific Python 3.12.x patch version pin.
- Whether to introduce `attrs` anywhere or stay all‑Pydantic. *Lean: stay all‑Pydantic for consistency.*
- Whether to split MCP tool handlers into a separate package shared with future MCP‑to‑MCP proxy logic (Phase 3). *Lean: yes, when Phase 3 begins.*

## Related
- [ADR‑0005 admin tech stack](0005-admin-tech-stack.md).
- [ADR‑0009 MCP server stack](0009-mcp-server-stack-python.md).
- [ADR‑0010 change channel](0010-change-channel-postgres-listen-notify.md) — `mintkey.changes` Python package.
- [ADR‑0011 shared Go stack](0011-shared-go-stack.md) — counterpart for Go services.
