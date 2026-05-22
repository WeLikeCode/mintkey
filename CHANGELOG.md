# Mintkey Changelog

This changelog tracks **Mintkey product changes only**. Versions follow semver
pre-release (`0.1.0-preview.N`) during pre-alpha.

> **Note on prior internal versions:** entries tagged `1.0.0-mvp`, `1.0.1`,
> `1.1.0`, and `0.3.0-impl` below are preserved for historical context and
> correspond to **internal development milestones only**. They DO NOT correspond
> to any released artifact or published tag. The first versioned public release
> will be `v0.1.0-preview.1`.

---

## [0.1.0-preview.1] — 2026-05-19

First versioned public release of Mintkey. See [`docs/RELEASE.md`](docs/RELEASE.md)
for the manual release procedure.

### Added (post-prealpha-readiness, 2026-05-17 — 2026-05-19)

- **`/KIRO.md`** at repo root — < 100-line link hub for builders (P-1..P-4 invariants, tech-stack table, "how to make a change" recipe).
- **`docs/patterns/`** — pattern library: `add-rest-endpoint.md`, `add-mcp-tool.md`, `add-audit-event.md`.
- **`examples/`** at repo root — `python-agent-snippet/`, `typescript-agent-snippet/`, `openai-compatible/` end-to-end agent walkthroughs against the Mintkey proxy.
- **`docs/guides/agent-never-sees-secret.md`** — structured walkthrough proving zero credential exposure (Setup → Token request → Proxy call → Audit log check → OTel trace check → Conclusion).
- **`tests/stubs/README.md`** — plan-only specification for 3 priority stubs (Vault Adapter in-memory Go gRPC, Proxy Recorder Go HTTP, OIDC Mock Python FastAPI).
- **`docs/architecture/01-architecture/security-notes/weak-hash-migration.md`** — formal weak-hash migration design (3 CodeQL sites, accept-for-prealpha rationale, revisit trigger).
- **`make demo`** and **`make demo-mock`** Makefile targets — single-command Docker stack startup + auto-validation.
- **`scripts/demo-mock-flow.sh`** — PAT-free mock-backend end-to-end demo (shellcheck-clean).
- **`scripts/dev-backup.sh`**, **`scripts/dev-restore.sh`**, **`scripts/dev-backup-cron.example.sh`** — postgres dev backup/restore toolkit.
- **Dev-test namespace** — parallel isolated Mintkey environment via Compose override; 16 host ports offset by +100; 15 unit tests + 4 integration tests for isolation properties. (Previously logged as `[0.3.0] — 2026-05-19`.)
- **Grafana Request Monitoring dashboard** — pre-baked dashboard with 4 panels (Request Rate, Request Count, Outcome Breakdown, Agent-Service Matrix), OTel spanmetrics-derived metrics, stable Prometheus datasource UID. (Previously logged as `[0.2.0] — 2026-05-16`.)
- **`docs/architecture/00-vision/06-roadmap.md`** — 46 EvidenceRef parentheticals across Sections 1 and 3; backup/restore claim corrected to distinguish dev-workflow scripts from production DR.
- **`.kiro/specs/post-prealpha-readiness/evidence.md`** — 24-row claim-to-evidence ledger.
- **`docs/DEBUG.md` +6 entries** — Stack not running, KEK mismatch, Jaeger auth, `make smoke` failures, Backup before reset, MCP config mismatch.

### Changed (post-prealpha-readiness + release prep)

- **`SECURITY.md`** — added "GitHub UI Dismissal Steps" subsections for 8 accepted Scorecard residuals; resolved truncated `GO-2026-XXXX` to `GO-2026-4918` (CVE-2026-33814 — `golang.org/x/net` HTTP/2 infinite loop, patched at v0.53.0, dep-bump documented as follow-up); added "Audit hash chain integrity" section citing `tests/acceptance/test_audit_append_only.py` per ADR-0014.7; added "Fixable Scorecard residuals — backlog" section.
- **`docs/architecture/00-vision/07-kiro-readiness.md`** — 3 status-table rows flipped: KIRO.md ⏳→✅, Pattern library ❌→🟢 partial, Stub services ❌→🟢 plan.
- **Container scan workflow (`.github/workflows/container-scan.yml`)** — Trivy `exit-code` is now conditional on `github.event_name`: `1` on `pull_request` (blocks new HIGH/CRITICAL CVEs); `0` on `push` / `schedule` / `workflow_dispatch` (SARIF upload only — Security tab is the source of truth per SECURITY.md Trivy-on-Debian-base policy).
- **`pyproject.toml` versions consolidated** — `admin-api`, `mcp-server`, `mock-backend` bumped from `0.1.0.dev0` / `0.1.0` to `0.1.0-preview.1` to match the other Mintkey packages.

### Changed (OSS readiness pass)

- Canonical version `0.1.0-preview.1` applied across `admin-ui/package.json`,
  `packages/python/mintkey-models/pyproject.toml`, `docs/architecture/contracts/rest/openapi.yaml`,
  and README status table — replacing the inconsistent mix of `1.0.0`,
  `0.1.0-experimental`, and `0.1.0`.
- `docs/RELEASE.md` added: manual release procedure, versioning policy, GHCR
  image target names, and deferred items (release workflow E-5, SBOM/provenance).
- CHANGELOG header rewritten to separate template scaffold history from Mintkey
  product history.

### Fixed

- **Kong-syncer startup retry** — fixed startup race against postgres LISTEN/NOTIFY readiness with exponential backoff and bounded retry budget.
- **CodeQL / Scorecard residual campaign (S5–S11)** — weak-hash classification (3 BLOCKED sites preserved, design doc added), SARIF upload reliability, JS XSS guards, SQL-injection architecture test, path-traversal guards, SSRF allowlist verification, secret-detection regex audit.

### Security

- **Image digest pinning** — all 9 `docker-compose.yml` images are now `@sha256:`-pinned.
- **Container scan trigger expansion** — `push` events on `main` + `workflow_dispatch` now trigger Trivy alongside the weekly cron schedule.
- **SECURITY.md "Trivy on Debian-base images" acceptance policy** — formalized acceptance criteria and revisit cadence for upstream Debian CVE residuals that no Mintkey code change can fix.

---

## Pre-alpha historical entries (internal)

> The following entries record **internal Mintkey development milestones**.
> Version numbers used here (`1.x.x`, `0.3.0-impl`) were informal and do not
> correspond to any public release, tagged commit, or artifact.

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
- **admin-api** (`apps/admin-api/`) — FastAPI service: health/ready endpoints, tenant-context middleware, CSRF, OTel, Liquibase changelogs (`db/changelog/001–010.yaml`), full CRUD for services/credentials/agents/permissions/audit, rotation + revocation endpoints, admin settings, audit chain verify/acknowledge, PlatformAdmin tenant management
- **mintkey-models** (`packages/python/mintkey-models/`) — SQLAlchemy 2.x async Mapped types, `audit_emit()` with per-tenant advisory lock + hash chain, `set_tenant_context()`, OTel `RedactingSpanProcessor`, `AdminUiSignedRequest` verification
- **mcp-server** (`apps/mcp-server/`) — FastAPI MCP service: agent auth, `list_services` / `describe_service` / `get_openapi` / `request_token` tools, change-channel subscriber
- **apps/broker** — Ed25519 JWT issuance, JWKS endpoint, force-refresh rate limiter, multi-tenant token claims
- **apps/kong-syncer** — LISTEN/NOTIFY subscriber, Kong declarative YAML push, reconciliation on startup
- **apps/proxy-plugin** — full Kong Go plugin: JWT verify → permissions → Vault gRPC → credential injection (7 auth schemes) → response scrub → audit; revocation sets, egress allowlist
- **apps/vault-adapter** — AES-256-GCM envelope encryption, SQLite DEK store, gRPC server (Put/Get/Revoke/ListVersions/ValidateServiceIdentity/RotateCredential), encrypted-DEK cache
- **packages/go** — shared Go packages: `audit`, `changes`, `ulid`, `otelinit`, `svcid`, `cfg`, `models`
- **audit-verify-job** — standalone hash-chain verification job
- **mock-backend** — 11 FastAPI endpoints covering all 7 auth schemes plus utility endpoints (timeout, 5xx, redirects, echo)
- **docker-compose.yml** + `go.work` — full local stack wiring all services
- **tests** — unit tests (`tests/unit/`), acceptance + architecture tests (`tests/acceptance/`, `tests/architecture/`), `conftest.py`, `requirements.txt`

## [1.0.0-mvp] — 2026-05-11

First complete implementation of the Mintkey MVP. All Phase 1 core backend tasks are implemented and tested.

### Foundation (M1.0)
- **Liquibase changelogs** (`apps/admin-api/db/changelog/001–010.yaml`) — 10 domain tables, RLS policies with PlatformAdmin escape, 3 DB roles, indexes
- **mintkey-models** (`packages/python/mintkey-models/`) — SQLAlchemy 2.x async Mapped types, `audit_emit()` with per-tenant advisory lock + hash chain, `set_tenant_context()`, OTel `RedactingSpanProcessor`, `AdminUiSignedRequest` verification, Pydantic `ConstraintsSchema`
- **Shared Go packages** (`packages/go/`) — `audit`, `changes`, `ulid`, `otelinit`, `svcid` packages
- **Admin API skeleton** (`apps/admin-api/`) — FastAPI with `/v1/health`, `/v1/ready`, tenant-context middleware, CSRF middleware, OTel instrumentation
- **Vault Adapter** (`apps/vault-adapter/`) — AES-256-GCM envelope encryption, SQLite DEK store, gRPC server with `ValidateServiceIdentity`, encrypted-DEK cache with change-channel invalidation
- **Credential Broker** (`apps/broker/`) — Ed25519 JWT issuance, JWKS endpoint, force-refresh rate limiter
- **Kong-syncer** (`apps/kong-syncer/`) — LISTEN/NOTIFY subscriber, Kong declarative YAML push
- **Proxy Plugin** (`apps/proxy-plugin/`) — JWT verification, credential injection (7 auth schemes), Vault gRPC client, response scrubber, audit emission, revocation sets, JWKS cache with TTL

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
- `infra/observability/prometheus.yml` configured; `/metrics` scrape targets for all containers

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
- Mermaid render gate (all ` ```mermaid` blocks)
- No-SQL-injection architecture test (no f-string SQL, no dynamic `text()`)
- Audit chokepoint architecture test (every write handler calls `audit_emit`)

### Mock Backend
- 11 FastAPI endpoints covering all 7 auth schemes plus utility endpoints (timeout, 5xx, redirects, echo)

## [0.3.0-impl] — 2026-05-10

### Added
- Initial implementation sessions: Milestone 1.0 (Foundation), 1.1 (Login), 1.2 (Services), 1.3 (Credentials), 1.4 (Agents), 1.5 (MCP + Token), 1.6 (Brokered Call), 1.7 (Audit), 1.8 (Rotation), 1.9 (Revocation), 1.10 (Observability), 1.11 (Smoke), 1.12 (Multi-tenant), 1.13 (Admin Settings)
- All 47 original Phase 1 Exit Criteria checklist items marked complete
- 37 additional checklist items added (24 `[x]` for implemented tasks, 13 `[ ]` for remaining AdminJS UI + Prometheus + Grafana + CI pipeline work)

---

## Template scaffold history (informational)

> The following section records the history of the **Kiro project template**
> that Mintkey was bootstrapped from. It is preserved for traceability but has
> no bearing on Mintkey product versions or releases.

## [0.3.0] — 2026-05-19

### Added

- **Dev-test namespace** — parallel isolated Mintkey environment via Docker Compose multi-file override (`docker-compose.test.yml` + `.env.test`). All 16 host ports offset by +100; volumes, networks, and data fully isolated under project name `mintkey-test`.
- **Makefile targets**: `dev-test`, `dev-test-down`, `dev-test-logs`, `dev-test-reset`, `smoke-test-ns` for full lifecycle management of the test namespace.
- **CI port-drift validation** (`tools/validate-test-override.py`) — asserts port offsets, image pins, and env vars stay in sync; added to GitHub Actions CI workflow.
- **Documentation**: `docs/DEV-TEST.md` (concept, port table, usage, troubleshooting) and `PORTS.md` updated with test namespace column.
- **Tests**: 15 unit tests for the validation script + 4 integration tests for namespace isolation properties.

## [0.2.0] — 2026-05-16

### Added

- **Grafana Request Monitoring dashboard** — pre-baked dashboard at `infra/observability/grafana/provisioning/dashboards/request-monitoring.json` with 4 panels (Request Rate, Request Count, Outcome Breakdown, Agent-Service Matrix) and agent/service template variables
- **OTel Collector spanmetrics connector** — derives `mintkey_proxy_calls_total` and `mintkey_proxy_duration_milliseconds_*` from `mintkey.proxy.handle_request` spans with actor, service, and outcome dimensions
- **Explicit Prometheus datasource UID** — `uid: prometheus` added to provisioning for stable dashboard references
- **Validation tests** — unit tests for OTel config structure and dashboard JSON correctness

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
