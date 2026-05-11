# Mintkey — Project Overview

**Purpose**: Credential broker for AI agents. Operators register backend services (Twilio, etc.) with encrypted credentials. AI agents discover services via MCP, authenticate with agent API keys, and call services through a credential-injecting reverse proxy — the proxy injects the real credential into the outbound request so agents never see plaintext credentials.

**Multi-tenant**: All data is tenant-scoped via PostgreSQL RLS policies. Single-tenant UX by default.

**Architecture is settled** — 17 accepted ADRs in `docs/architecture/01-architecture/adr/`. Implementation must conform; do not invent contract surfaces.

## Core Components

| Service | Lang | Port | Purpose |
|---|---|---|---|
| admin-api | Python 3.12 + FastAPI | 8080 | Operator REST API + credential-injecting proxy |
| mcp-server | Python 3.12 + FastAPI | 8082 | MCP tool server for agents |
| broker | Go 1.22 | 8083 | JWT credential broker |
| vault-adapter | Go 1.22 | 8084 (gRPC) | Encrypted credential store (AES-256-GCM + SQLite) |
| kong-syncer | Go 1.22 | 8085 | Kong DB-less config sync |
| proxy-plugin | Go 1.22 | 8086 | Kong go-pdk egress plugin |
| admin-ui | Node.js (AdminJS 7.x) | 8081 | Operator web UI |
| mock-backend | Python 3.12 + FastAPI | 8999 | Test/demo backend (all auth schemes) |
| postgres | PostgreSQL 16 | 5432 | Primary DB |
| keycloak | Keycloak 24 | 8443 | OIDC provider |
| kong | Kong 3.6 | 8000/8001 | Egress proxy |

## Key Security Invariants
- Plaintext credentials NEVER logged, audited, returned, or cached beyond request scope (ADR-0014.4, S-SEC-1)
- Every state change emits an audit event with hash chain (ADR-0014.7)
- All SQL uses bound parameters — no f-string interpolation (ADR-0008, T-1.0.15)
- Every domain table has tenant_id + RLS policy (ADR-0008, ADR-0014.8)
- Liquibase is the schema source of truth — never add columns in SQLAlchemy (ADR-0015)
- Wire IDs are ULIDs with prefix: tenant_, agent_, svc_, cred_, perm_, audit_, svckey_ (ADR-0017.11)
