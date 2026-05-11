# Codebase Structure

```
mintkey/
├── admin-api/                      # Python FastAPI — operator REST API + proxy
│   ├── Dockerfile                  # build context: repo root (needs mintkey-models)
│   ├── requirements.txt
│   ├── db/changelog/               # Liquibase changelogs (schema source of truth)
│   │   ├── db.changelog-master.yaml
│   │   ├── 001-initial-schema.yaml … 012-service-api-keys.yaml
│   └── src/admin_api/
│       ├── main.py                 # FastAPI app factory + router registration
│       ├── api/
│       │   ├── auth.py             # POST /v1/auth/internal-login, logout, whoami
│       │   ├── agents.py           # CRUD /v1/tenants/{tid}/agents
│       │   ├── api_keys.py         # CRUD /v1/tenants/{tid}/agents/{aid}/api-keys
│       │   ├── audit.py            # GET /v1/tenants/{tid}/audit
│       │   ├── audit_admin.py      # POST /v1/admin/audit/verify-chain + acknowledge-tamper
│       │   ├── changes.py          # GET /v1/changes
│       │   ├── credentials.py      # POST/GET /v1/tenants/{tid}/services/{sid}/credentials
│       │   ├── health.py           # GET /v1/health + /v1/ready
│       │   ├── internal.py         # POST /v1/internal/validate-agent-key + proxy-hit
│       │   ├── permissions.py      # POST/DELETE /v1/tenants/{tid}/agents/{aid}/permissions
│       │   ├── proxy.py            # ALL /v1/proxy/call/{svc_id}/{path} (credential-injecting)
│       │   ├── services.py         # CRUD /v1/tenants/{tid}/services
│       │   ├── settings.py         # GET/PATCH /v1/admin/settings (PlatformAdmin)
│       │   └── tenants.py          # POST /v1/tenants (PlatformAdmin)
│       ├── auth/
│       │   ├── internal.py         # DUMMY_HASH for timing equalization
│       │   └── sessions.py         # session cookie helpers
│       ├── changes/publisher.py    # notify_change() helper
│       ├── db/
│       │   ├── deps.py             # get_db_session FastAPI dependency
│       │   └── session.py          # async engine + session factory
│       ├── middleware/
│       │   ├── csrf.py             # CSRF double-submit cookie middleware + @no_csrf
│       │   └── platform_admin_audit.py
│       └── services/vault_client.py  # VaultAdapterClient (in-memory stub; real gRPC T-1.3.1)
│
├── mcp-server/                     # Python FastAPI — MCP tool server for agents
│   ├── Dockerfile                  # build context: repo root
│   ├── requirements.txt
│   └── src/mcp_server/
│       ├── main.py                 # FastAPI app + agent-key auth middleware
│       ├── auth/agent_key.py       # validate via admin-api /v1/internal/validate-agent-key
│       ├── db/session.py           # async DB session
│       ├── tools/
│       │   ├── discovery.py        # GET /v1/tools/list_services, describe_service, get_openapi
│       │   └── request_token.py    # POST /v1/tools/request_token
│       └── policy/constraints.py  # rate_limit + time_window constraint evaluators
│
├── mock-backend/                   # Python FastAPI — demo backend (all auth schemes)
│   ├── Dockerfile                  # build context: ./mock-backend
│   ├── pyproject.toml
│   └── src/mock_backend/rest/main.py  # /health, /api-key-header, /bearer, /basic-auth, /echo, etc.
│
├── mintkey-models/mintkey_models/  # Shared Python package
│   ├── audit.py                    # audit_emit() — canonical audit chokepoint
│   ├── tenant_ctx.py               # set_tenant_context() helper
│   ├── schemas.py                  # Pydantic schemas
│   └── db.py                       # shared SQLAlchemy models
│
├── services/                       # Go microservices (go.work workspace)
│   ├── vault-adapter/              # gRPC credential store (port 8084)
│   ├── broker/                     # JWT credential broker (port 8083)
│   ├── kong-syncer/                # Kong DB-less config sync (port 8085)
│   └── proxy-plugin/               # Kong go-pdk egress plugin (port 8086)
│
├── admin-ui/                       # AdminJS 7.x operator web UI (port 8081)
│
├── seed-job/                       # One-shot bootstrap job
├── audit-verify-job/               # Scheduled audit chain verification
├── scripts/
│   ├── e2e_smoke.py               # Comprehensive end-to-end smoke test
│   └── e2e-smoke.sh               # Shell wrapper for smoke test
├── docs/architecture/             # SOURCE OF TRUTH — 17 ADRs, contracts, flows
│   ├── 01-architecture/adr/       # 0001-0017 accepted ADRs
│   ├── contracts/rest/openapi.yaml  # Canonical REST contract
│   ├── contracts/vault-adapter/vault.proto  # Vault Adapter gRPC IDL
│   └── contracts/events/          # Audit + change event JSON schemas
├── docker-compose.yml             # Full 15-service stack
├── go.work / go.work.sum          # Go workspace
└── AGENTS.md / CLAUDE.md          # Operating principles (read first!)
```

## Key env vars (from docker-compose)
- `DATABASE_URL` — asyncpg URL for Python; pgx URL for Go
- `VAULT_GRPC_ADDR` — vault-adapter gRPC address (e.g. `vault-adapter:8084`)
- `ADMIN_API_BASE_URL` — for mcp-server calling admin-api (e.g. `http://admin-api:8080`)
- `MINTKEY_VAULT_KEK` — hex-encoded 32-byte AES-256 KEK (dev only; use keyfile in prod)
- `MINTKEY_ENV` — `dev` or `production`
