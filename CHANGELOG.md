# Changelog

All notable changes to this template are recorded here. Engagements track which template version they bootstrapped from in `.kiro/setup-state.json` (`template_version` field).

## [0.1.0] — 2026-05-08

Initial release. Template skeleton generalized for cross-engagement reuse.

### Includes

- **Bootstrap wizard** with 16 mandatory + 9 optional questions and explicit refusal conditions ([bootstrap/questionnaire.md](bootstrap/questionnaire.md))
- **Steering loading protocol** with the three real Kiro inclusion modes (default-load / `fileMatch` / `manual`), frontmatter spec, anti-pollution rules, and audit tool ([.kiro/steering/STEERING-PROTOCOL.md](.kiro/steering/STEERING-PROTOCOL.md))
- **8-skill catalog** including `architecture-advisor`, `think-tiger`, `adversarial-review`, `spec-first-check`, `adr-from-decision`, `risk-register-update`, `assumption-validate`, `decision-log-append` ([.kiro/steering/skills-catalog.md](.kiro/steering/skills-catalog.md))
- **5 default-loaded protocol rules** (steering files, no frontmatter): architect-doc-ownership, real-risks-not-padding, role-ownership-architect-vs-developer, smallest-first-cut, steering-load-discipline ([.kiro/steering/](.kiro/steering/))
- **Reference templates** bundled with the skills that consume them: ADR template (`.kiro/skills/adr-from-decision/references/`), risk register template (`.kiro/skills/risk-register-update/references/`), assumption register template (`.kiro/skills/assumption-validate/references/`)
- **5 onboarding tracks** for architect / backend / frontend / data-ml / lead ([docs/onboarding/](docs/onboarding/))
- **Contracts directory** with SDD authoring guide ([contracts/README.md](contracts/README.md))
- **Architect-owned `docs/architecture/`** with banner enforcement ([docs/architecture/README.md](docs/architecture/README.md))
- **4 archetype layouts** (single-app, polyglot-monorepo, microservices, modular-monolith) ([archetypes/README.md](archetypes/README.md))
- **Tooling spec** for audit, vibe-check, spec-trace, contract-lint, doctor, template-diff ([tools/README.md](tools/README.md))

### Designed against (anti-patterns this version actively prevents)

- Loading all steering files into every agent context
- Padding risk registers with speculative entries
- Editing `docs/architecture/` directly (architect-owned)
- Vibe coding (no spec, no code)
- Treating prototype / PoC code as production-architecture truth
- Architect work being assigned to TLs / developers
- ADRs that are decoration (zero referencing tests / code)

## [0.2.0] — 2026-05-08

### Added

- **Wizard script** ([bootstrap/setup-wizard.sh](bootstrap/setup-wizard.sh) + [bootstrap/lib/wizard-helpers.sh](bootstrap/lib/wizard-helpers.sh)) — interactive bash that asks the 25 questions, validates with refusal conditions (kebab-case codename, ≥120-char business goal with platitude denylist, architect email required, three-real-risks structured input), detects conflicts, and renders all engagement files including ADR-0001-bootstrap recording the choices.
- **Generic steering templates** ([bootstrap/templates/](bootstrap/templates/)) for `product`, `structure`, `architecture-principles`, `tech`, `repo-governance` — all with `[REQUIRES-UPDATE]` markers the architect fills in. Architecture-principles ships 8 generic baseline principles (P-1 through P-8) plus slots for engagement-specific additions.
- **Archetype recommendation** ([archetypes/RECOMMENDATIONS.md](archetypes/RECOMMENDATIONS.md)) — pragmatic guidance on which 2 of the 4 archetypes to scaffold first (polyglot-monorepo + single-app), with concrete proposals for each.

### Roadmap

- 0.3: Build the polyglot-monorepo + single-app archetype scaffolds per RECOMMENDATIONS.md
- 0.4: Tooling scripts (kiro-steering-audit, vibe-check, spec-trace, contract-lint, doctor)
- 0.5: CI templates for major providers (GitLab, GitHub Actions, Azure DevOps)
- 0.6: 2-3 worked example engagements (clinical-trials, iot-predictive, fintech-kyc) so engagements have anonymized references to draw on

### Known limitations

- Wizard is interactive bash — no GUI. Adequate for a CLI-first architect; might want a minimal web UI later.
- Archetype skeletons still not populated (only RECOMMENDATIONS.md describes what to build).
- Tooling (audit, spec-trace, vibe-check, doctor) specified in `tools/README.md` but scripts not implemented.
- Generic steering templates use `[REQUIRES-UPDATE]` markers — the architect must fill in engagement-specific content. The wizard does NOT auto-write rich content; it scaffolds, the architect refines.

### Anti-patterns explicitly NOT addressed (out of scope)

- Specific cloud provider patterns (AWS / GCP / Azure / on-prem) — engagement-specific
- Specific frameworks (NestJS / FastAPI / Spring) — wizard records the choice; template doesn't prescribe
- CI/CD pipeline implementations beyond skeletons — engagement-specific
- Customer-facing public docs — out of scope, this is internal scaffolding

---

*Template ownership: Enterprise Business Architect Practice. Maintained by {{architect handle}}.*

---

# Mintkey Implementation Changelog

All notable implementation changes to the Mintkey credential broker MVP.

## [1.1.0] — 2026-05-15

### Added
- **Keycloak SSO end-to-end** for admin-ui, Grafana, and Jaeger (ADR-0020).
  Operators sign in once via the Keycloak `mintkey` realm; admin-api owns the
  OIDC `client_secret`; admin-ui delegates auth via `/v1/auth/whoami`.
- **CLI break-glass**: `mintkey admin reset-password --email <e>` / `clear-password`
  for emergency access when Keycloak is unreachable (D2-b).
- **LAN-friendly canonical public-URL env vars**: `MINTKEY_MCP_PUBLIC_URL`,
  `MINTKEY_PROXY_PUBLIC_URL`, `MINTKEY_KEYCLOAK_PUBLIC_URL`,
  `MINTKEY_KEYCLOAK_INTERNAL_URL`, `MINTKEY_ADMIN_API_PUBLIC_URL`,
  `MINTKEY_ADMIN_UI_PUBLIC_URL`, `MINTKEY_GRAFANA_PUBLIC_URL`,
  `MINTKEY_JAEGER_PUBLIC_URL`. Legacy aliases (`MCP_BASE_URL`,
  `MINTKEY_MCP_URL`, `MINTKEY_PROXY_URL`, `KONG_PROXY_URL`) accepted with
  one-time WARN log.
- **`docs/NETWORK.md`** (operator-facing) and **`docs/AUTH.md`** (Keycloak flow,
  break-glass, troubleshooting).
- **DB migrations**: `014-operators-keycloak` (oidc_sub UNIQUE),
  `015-app-role-passwords` (deterministic mintkey_app + _subscriber
  passwords, fixing first-boot connection failure), `016-sessions-auth-method`
  (tracks auth_method per session so the UI can display the right badge).

### Changed
- **admin-ui**: replaced `buildAuthenticatedRouter` + `passport-openidconnect`
  with `buildRouter` + custom `requireSession` middleware + `express-session`
  (SSO-G).
- **discovery.py** step-3 instruction prefix corrected from `/proxy/<path>` to
  `/v1/call/<svc>/<path>` (NET-REDUX-1).
- **agent-bootstrap skill** scrubbed of Docker-internal hostnames (NET-REDUX-1).
- **Kong admin port** bound to `127.0.0.1:8001` (was 0.0.0.0); data plane on 8000
  unchanged (D4).
- **Jaeger UI** moved behind `jaeger-auth` oauth2-proxy sidecar; direct Jaeger
  port is internal-only (SSO-E).

### Fixed
- **admin-api** expected `iss` claim now uses `MINTKEY_KEYCLOAK_PUBLIC_URL` (was
  the internal URL, which broke browser-side login) (SSO-REDUX-2).
- **PKCE S256** now realm-enforced on all three Keycloak clients (admin-api,
  Grafana, Jaeger) (SSO-REDUX-2).
- **admin-ui** no longer hangs on action POSTs: removed global `express.json()`
  which was draining the request body before formidable could read it
  (SSO-REDUX-3).
- **admin-ui action handlers** now thread the operator's session into admin-api
  via `operatorOptsFromAdmin()` — fixes test-connection and several other
  actions that were returning 403/500 (UI-E2E `fcac7053`).
- **Permissions endpoint URL**: `POST /v1/tenants/{tid}/agents/{aid}/permissions`
  (was `/v1/tenants/{tid}/permissions` which 405'd) (UI-E2E `e21ba22e`).

## [1.0.1] — 2026-05-11

### Added
- **admin-api** (`admin-api/`) — FastAPI service: health/ready endpoints, tenant-context middleware, CSRF, OTel, Liquibase changelogs (`db/changelog/001–010.yaml`), full CRUD for services/credentials/agents/permissions/audit, rotation + revocation endpoints, admin settings, audit chain verify/acknowledge, PlatformAdmin tenant management
- **mintkey-models** (`mintkey-models/`) — SQLAlchemy 2.x async Mapped types, `audit_emit()` with per-tenant advisory lock + hash chain, `set_tenant_context()`, OTel `RedactingSpanProcessor`, `AdminUiSignedRequest` verification
- **mcp-server** — FastAPI MCP service: agent auth, `list_services` / `describe_service` / `get_openapi` / `request_token` tools, change-channel subscriber
- **services/broker** — Ed25519 JWT issuance, JWKS endpoint, force-refresh rate limiter, multi-tenant token claims
- **services/kong-syncer** — LISTEN/NOTIFY subscriber, Kong declarative YAML push, reconciliation on startup
- **services/proxy-plugin** — full Kong Go plugin: JWT verify → permissions → Vault gRPC → credential injection (7 auth schemes) → response scrub → audit; revocation sets, egress allowlist
- **services/vault-adapter** — AES-256-GCM envelope encryption, SQLite DEK store, gRPC server (Put/Get/Revoke/ListVersions/ValidateServiceIdentity/RotateCredential), encrypted-DEK cache
- **internal** — shared Go packages: `audit`, `changes`, `ulid`, `otelinit`, `svcid`, `cfg`, `models`
- **audit-verify-job** — standalone hash-chain verification job
- **mock-backend** — 11 FastAPI endpoints covering all 7 auth schemes plus utility endpoints (timeout, 5xx, redirects, echo)
- **docker-compose.yml** + `go.work` — full local stack wiring all services
- **tests** — unit tests (`tests/unit/`), acceptance + architecture tests (`tests/acceptance/`, `tests/architecture/`), `conftest.py`, `requirements.txt`

## [1.0.0-mvp] — 2026-05-11

First complete implementation of the Mintkey MVP. All Phase 1 core backend tasks are implemented and tested.

### Foundation (M1.0)
- **Liquibase changelogs** (`admin-api/db/changelog/001–010.yaml`) — 10 domain tables, RLS policies with PlatformAdmin escape, 3 DB roles, indexes
- **mintkey-models** (`mintkey-models/`) — SQLAlchemy 2.x async Mapped types, `audit_emit()` with per-tenant advisory lock + hash chain, `set_tenant_context()`, OTel `RedactingSpanProcessor`, `AdminUiSignedRequest` verification, Pydantic `ConstraintsSchema`
- **Shared Go packages** (`internal/`) — `audit`, `changes`, `ulid`, `otelinit`, `svcid` packages
- **Admin API skeleton** (`admin-api/`) — FastAPI with `/v1/health`, `/v1/ready`, tenant-context middleware, CSRF middleware, OTel instrumentation
- **Vault Adapter** (`services/vault-adapter/`) — AES-256-GCM envelope encryption, SQLite DEK store, gRPC server with `ValidateServiceIdentity`, encrypted-DEK cache with change-channel invalidation
- **Credential Broker** (`services/broker/`) — Ed25519 JWT issuance, JWKS endpoint, force-refresh rate limiter
- **Kong-syncer** (`services/kong-syncer/`) — LISTEN/NOTIFY subscriber, Kong declarative YAML push
- **Proxy Plugin** (`services/proxy-plugin/`) — JWT verification, credential injection (7 auth schemes), Vault gRPC client, response scrubber, audit emission, revocation sets, JWKS cache with TTL

### Auth (M1.1)
- Internal Argon2id login with identical-body timing equalization and DUMMY_HASH
- OIDC login via Keycloak with `passport-openidconnect`
- Session middleware with CSRF double-submit cookie

### Services + Credentials (M1.2–M1.3)
- Service CRUD with SSRF protection (RFC1918/link-local/metadata IP block), global `pg_notify`, audit events
- Credential create/rotate endpoints (plaintext never returned, DEK per-store-op)
- Vault Adapter `PutCredential` / `GetCredential` / `ValidateServiceIdentity` RPCs

### Agents + Permissions (M1.4)
- Agent CRUD with API key shown once (fingerprint in audit, never the key)
- Permission grants with closed Pydantic `ConstraintsSchema` (`extra="forbid"`)

### MCP + Token (M1.5)
- MCP Server: agent auth, `list_services` / `describe_service` / `get_openapi`, `request_token` with constraint evaluation
- JWT claims: `tnt` = prefixed ULID, `kid` in JWS header, 10-min TTL
- Change-channel subscriber (global `mintkey:service` + `mintkey:agent`)

### Brokered Call (M1.6)
- Proxy Plugin end-to-end: JWT verify → permissions check → Vault fetch → credential inject → upstream call → response scrub
- `proxy.hit` audit events, OTel span `mintkey.proxy.handle_request`
- Revocation sets with `mintkey:agent` NOTIFY subscriber

### Audit (M1.7)
- `GET /v1/tenants/{tid}/audit` with cursor pagination, 6 optional filters (all bound-parameter SQL)
- Mandatory hash chain: `prev_hash + hash` per event, per-tenant advisory lock
- AST-walking architecture test: every state-change handler calls `audit_emit()`

### Rotation + Revocation (M1.8–M1.9)
- Credential rotation with DEK cache invalidation (`mintkey:credential` channel)
- Agent revocation with immediate propagation to proxy plugin's in-memory set
- Reconciliation endpoint: `GET /v1/changes?since=<event_id>` with 410 on unknown cursor

### Observability (M1.10)
- Two-layer OTel redaction: `RedactingSpanProcessor` (SDK) + `attributes/redact` + `redaction` processors (Collector)
- Jaeger integration with trace propagation through all services
- `prometheus.yml` configured; `/metrics` scrape targets for all containers

### Multi-tenancy (M1.12)
- `POST /v1/tenants` (PlatformAdmin only) with genesis hash + `audit_chain_state` init
- RLS policy with `platform_admin_view` escape on all tenant-scoped tables
- Cross-tenant isolation: zero data leakage verified by TestClient fuzzing test
- Cross-tenant JWT replay rejection

### Admin Settings + Chain Verification (M1.13)
- `GET/PATCH /v1/admin/settings` with closed `AdminSettings` Pydantic schema
- `POST /v1/admin/audit/verify-chain` — on-demand per-tenant hash chain verification
- `POST /v1/admin/audit/acknowledge-tamper` — tamper acknowledgment with audit event
- `platform_admin.access` emission on every PlatformAdmin cross-tenant read

### CI Gates
- OpenAPI parity gate (FastAPI runtime vs. checked-in YAML)
- SQLAlchemy mirror diff (Liquibase vs. `mintkey_models/db.py`)
- Mermaid render gate (all `\`\`\`mermaid` blocks)
- No-SQL-injection architecture test (no f-string SQL, no dynamic `text()`)
- Audit chokepoint architecture test (every write handler calls `audit_emit`)

### Mock Backend
- 11 FastAPI endpoints covering all 7 auth schemes plus utility endpoints (timeout, 5xx, redirects, echo)

## [0.3.0-impl] — 2026-05-10

### Added
- Initial implementation sessions: Milestone 1.0 (Foundation), 1.1 (Login), 1.2 (Services), 1.3 (Credentials), 1.4 (Agents), 1.5 (MCP + Token), 1.6 (Brokered Call), 1.7 (Audit), 1.8 (Rotation), 1.9 (Revocation), 1.10 (Observability), 1.11 (Smoke), 1.12 (Multi-tenant), 1.13 (Admin Settings)
- All 47 original Phase 1 Exit Criteria checklist items marked complete
- 37 additional checklist items added (24 `[x]` for implemented tasks, 13 `[ ]` for remaining AdminJS UI + Prometheus + Grafana + CI pipeline work)
