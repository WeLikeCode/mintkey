# Known Gaps and Issues (as of 2026-05-11)

## Schema / Code Drift
- `permission_grants.updated_at` — column does not exist (code incorrectly references it)
- `audit_events` — column is `at` not `created_at` (code uses `created_at`)
- `tenants.name` — may be missing
- `audit_chain_state.genesis_hash` — may be missing

## asyncpg incompatibilities
- `::type` PostgreSQL cast syntax is invalid in asyncpg prepared statements
- Must use `CAST(:param AS type)` everywhere: jsonb, uuid, text[], timestamptz

## Services running as nginx placeholders
- `mcp-server` — nginx placeholder; real Python implementation exists at `mcp-server/src/mcp_server/`
- `mock-backend` — nginx placeholder; real Python implementation exists at `mock-backend/src/mock_backend/rest/`
- Both now have Dockerfiles (created 2026-05-11)

## Vault Adapter gRPC not wired
- `admin-api/src/admin_api/services/vault_client.py` is in-memory stub
- Real vault-adapter gRPC runs at `vault-adapter:8084`
- Need to generate Python stubs from `docs/architecture/contracts/vault-adapter/vault.proto`

## MCP Server auth middleware missing
- `mcp_server/main.py` had no middleware to validate agent keys
- Middleware added 2026-05-11 in create_app()

## CSRF
- CSRF token was never set on login response — fixed 2026-05-11
- Dynamic proxy paths needed prefix matching in CSRF exempt list — fixed 2026-05-11

## Seed job
- Stops at step 5 of 12; steps 6-12 not implemented

## Admin UI
- `@adminjs/sql` adapter never registered
- `session` table never created
- Two competing session middlewares

## service_api_keys table
- Added in Liquibase changelog 012 but grants not applied at table creation time (fixed 2026-05-11)
- Need per-table GRANT after table creation in same changeset

## Completed fixes (2026-05-11)
- CSRF cookie set on login
- CSRF prefix matching for proxy paths
- asyncpg cast syntax in permissions.py, api_keys.py, sessions.py
- permission_grants INSERT column list fixed (removed updated_at, added created_by)
- api_keys.py created_by uses agent_id UUID not string literal
- proxy.py cross-tenant RLS bypass with placeholder UUID + platform_admin_view='on'
- service_api_keys GRANT in 012 changelog
- Smoke test rewritten as Python (bash arithmetic pitfalls)
- mock-backend GET /echo added
- mcp-server auth middleware added
- docker-compose mcp-server and mock-backend updated to use real Python builds
