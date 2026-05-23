# Structure

Top-level repo layout for Mintkey. Read this before touching any file.

## Repo map

```
mintkey/
├── README.md                        # Entry point
├── BOOTSTRAP.md                     # 15-min setup guide
├── CHANGELOG.md
├── Makefile                         # doctor, lint, test, build targets
│
├── apps/                            # All deployable services
│   ├── admin-api/                   # Admin REST API — Python + FastAPI
│   │   ├── src/admin_api/
│   │   │   ├── api/                 # FastAPI routers
│   │   │   ├── services/            # Business logic
│   │   │   ├── db/                  # SQLAlchemy models + session
│   │   │   ├── auth/                # OIDC + sessions + internal-auth fallback
│   │   │   ├── audit/               # Audit emission helper
│   │   │   └── middleware/          # Tenant context, OTel, CSRF
│   │   └── db/changelog/            # Liquibase YAML changelogs (schema source of truth)
│   ├── mcp-server/                  # MCP Server — Python + Anthropic mcp SDK
│   │   └── src/mcp_server/
│   │       ├── tools/               # One file per MCP tool
│   │       ├── auth/                # Bearer Agent API Key handler
│   │       └── middleware/          # Tenant context, OTel
│   ├── admin-ui/                    # Admin Console — AdminJS (Node 20 + Express)
│   ├── mock-backend/                # Stubbed REST API for end-to-end demo
│   ├── seed-job/                    # One-shot seed job (bootstrap admin + Keycloak realm)
│   ├── audit-verify-job/            # Scheduled audit chain verification
│   ├── jaeger-auth/                 # Jaeger OIDC auth proxy
│   ├── broker/                      # Credential Broker — EdDSA JWT issuer (Go)
│   ├── vault-adapter/               # Vault Adapter — credential storage (Go)
│   ├── kong-syncer/                 # Kong declarative YAML pusher (Go)
│   └── proxy-plugin/                # Kong go-pdk plugin — credential injection (Go)
│
├── packages/                        # Shared libraries
│   ├── python/mintkey-models/       # Shared Python package (Pydantic v2 + SQLAlchemy Mapped)
│   └── go/                          # Shared Go packages (root module, not go.work sub-modules)
│       ├── audit/                   # Audit emission helper
│       ├── auditq/                  # Audit queue
│       ├── changes/                 # Postgres LISTEN/NOTIFY client
│       ├── otelinit/                # OTel bootstrap
│       ├── svcid/                   # Service identity boot-secret client
│       ├── ulid/                    # ULID helpers
│       └── vault/                   # Vault proto + Go stubs
│
├── infra/                           # Infrastructure config
│   ├── compose/                     # docker-compose.yml, docker-compose.test.yml
│   ├── observability/               # prometheus.yml, alert_rules.yml, otel-collector-config.yaml, grafana/
│   └── keycloak/                    # Keycloak realm placeholders
│
├── docker-compose.yml               # Root shim (includes infra/compose/docker-compose.yml)
│
├── .kiro/
│   ├── steering/                    # Always-loaded governance rules + product/structure/tech
│   ├── skills/                      # Agent skills (SKILL.md per skill)
│   ├── hooks/                       # Event-triggered automation
│   └── specs/                       # Per-feature Kiro SDD specs
│
├── bootstrap/
│   ├── questionnaire.md
│   ├── setup-wizard.sh
│   └── templates/                   # Steering file templates
│
├── docs/
│   ├── architecture/                # ARCHITECT-OWNED — never edit existing files directly
│   │   ├── 00-vision/               # Problem, vision, personas, glossary, roadmap
│   │   ├── 01-architecture/         # C4 views, quality attributes, threat model, ADRs
│   │   ├── 02-tech-stack/           # Tech stack dashboard
│   │   ├── 03-flows/                # Sequence diagrams per flow
│   │   ├── 04-observability/        # OTel span names, metrics, dashboards
│   │   ├── 05-deployment/           # Compose + Helm topology
│   │   ├── adrs/                    # Canonical ADR location (ADR-0001..NNNN)
│   │   ├── contracts/               # REST OpenAPI, MCP tools, event schemas, vault proto
│   │   ├── proposal/                # Pre-ADR proposals (P-NNN)
│   │   ├── risk-register.md         # Architect-owned; seeded by wizard
│   │   └── open-questions.md        # Living register of open architectural questions
│   ├── onboarding/                  # Role-based tracks (architect, backend, frontend, lead)
│   └── requirements/
│       ├── requirements.csv         # Canonical requirements tracker
│       └── sources/                 # BA artifacts ingested by requirements-extract skill
│
├── contracts/                       # Load-bearing specs for code generation
│   ├── openapi/                     # REST contracts
│   ├── asyncapi/                    # Event contracts
│   ├── jsonschema/                  # Reusable payload types
│   └── fixtures/                    # Canonical examples (CI validates)
│
├── remediation/                     # Remediation session tracking
│   ├── active/                      # Ongoing sessions
│   ├── archive/2026/05/             # 44 completed sessions (historical; read-only)
│   └── SESSION_TEMPLATE/            # Scaffold for new sessions
│
├── tests/
│   ├── acceptance/                  # Behavioral tests citing ADR / spec IDs
│   ├── integration/                 # Integration tests per service
│   ├── unit/                        # Implementation-coupled
│   └── architecture/                # Architecture tests (RLS, audit coverage)
│
├── archetypes/                      # Wizard-pickable layouts
└── go.work                          # Go workspace root
```

## Ownership rules

- `docs/architecture/` — **architect-owned**. Agents and developers suggest diffs in drafts; architect applies.
- `.kiro/steering/` — **architect-owned**. Same rule.
- `contracts/` — **architect-owned** for governance; developers implement against them.
- `apps/`, `packages/` — developer-owned; must reference a spec or ADR.

## Language map

| Directory | Language | Key libraries |
|---|---|---|
| `apps/broker/` | Go 1.22+ | go-jose/v4, pgx/v5, chi/v5 |
| `apps/vault-adapter/` | Go 1.22+ | modernc.org/sqlite, AES-256-GCM |
| `apps/kong-syncer/` | Go 1.22+ | pgx/v5, chi/v5 |
| `apps/proxy-plugin/` | Go 1.22+ | Kong go-pdk |
| `apps/admin-api/` | Python 3.12+ | FastAPI, SQLAlchemy 2.x async, Pydantic v2, authlib |
| `apps/mcp-server/` | Python 3.12+ | Anthropic mcp SDK, FastAPI, SQLAlchemy 2.x async |
| `apps/admin-ui/` | Node 20 | AdminJS 7.x, Express, passport-openidconnect, pino |
| `packages/python/mintkey-models/` | Python 3.12+ | Pydantic v2, SQLAlchemy 2.x Mapped |

## Key conventions

- IDs use ULID with type prefix: `agent_…`, `svc_…`, `cred_…`, `perm_…`, `tnt_…`
- Every domain table carries `tenant_id UUID NOT NULL` + Postgres RLS policy
- Every state-change handler emits an audit event via the `audit` helper — no exceptions
- Credentials are decrypted only inside the Vault Adapter and consumed only inside the proxy request scope
- Schema source of truth is Liquibase YAML changelogs in `apps/admin-api/db/changelog/`
