# KIRO.md — Mintkey

Mintkey is a self-hostable credential broker for AI agents. Operators register backend services
with real credentials. Agents discover those services over MCP, request short-lived scoped JWTs,
and call backends through an egress proxy (Kong) that injects the real credential in-flight.
The agent never holds a usable credential. See [README.md](README.md) for the full project story.

---

## Quick links

| Document | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | Canonical coding-agent instructions — read this before any implementation work |
| [.kiro/steering/](.kiro/steering/) | Governance rules, architecture principles, and spec conventions |
| [docs/architecture/](docs/architecture/) | Architect-owned source of truth: 20 ADRs, contracts, flows, threat model |
| [docs/patterns/](docs/patterns/) | Builder-owned step-by-step recipes for common operations |

---

## Tech stack at a glance

| Technology | Role | Where the code lives |
|---|---|---|
| Python 3.12 + FastAPI | Admin REST API + MCP Server (CRUD, broker, audit) | `admin-api/`, `mcp-server/` |
| Go 1.22 | Security-critical services: Vault Adapter, Egress Proxy plugin, Kong-syncer, Broker | `services/`, internal Go modules |
| TypeScript (AdminJS 7.x) | Admin UI — BFF over the admin-api REST API | `admin-ui/` |
| PostgreSQL 16 + Liquibase | Primary data store; schema owned by Liquibase changelogs | `admin-api/db/changelog/` |
| Kong DB-less + Go plugin | Egress proxy: injects credentials in-flight per request | `services/proxy-plugin/` |
| Keycloak | Operator OIDC identity provider (canonical per ADR-0020) | `docker-compose.yml` |
| Trivy + CodeQL | Container image scan + SAST; run in CI on every PR | `.github/workflows/` |

---

## How to make a change

1. **Read steering** — open `.kiro/steering/` and find the relevant principle (P-1..P-10).
2. **Find or write the pattern** — open `docs/patterns/` for the matching recipe (e.g. `add-rest-endpoint.md`).
3. **Make the change** — contract-first (edit the OpenAPI / MCP schema / event schema before code); implement test-first.
4. **Run tests** — `make lint && make test`; capture exit codes (not "looks good").
5. **Open a PR** — link the ADR or contract that authorises the change; include red-team grep output.

---

## Key invariants

- **P-1** — The agent never holds a usable credential; plaintext exists only inside the Vault Adapter and the proxy's request scope.
- **P-2** — Every state change emits an audit event via the single `audit.emit()` helper; no second path.
- **P-3** — Tenant isolation is structural: every domain table has `tenant_id` + RLS; cross-tenant access is impossible by construction.
- **P-4** — Contracts (OpenAPI, MCP schemas, event schemas, vault proto) are written before code; CI enforces round-trip parity.
