# Orchestration plan — 2026-06-02-email-proxy

Repo: `/Users/alexandruiacobescu/gooseProjects/mintkey`
Session dir: `/Users/alexandruiacobescu/gooseProjects/mintkey/remediation/active/2026-06-02-email-proxy/`
Session start commit: `1e74d45dfe9841cf3a0196b1caa153a1e6cf65ca` (branch `chore/docs-pr-a-install-and-contracts`)
Target branch (to create at C-0): `feat/email-proxy`
Spec: `.kiro/specs/email-proxy/{requirements,design,tasks}.md`
Authoritative ADR: `docs/architecture/01-architecture/adr/0024-email-proxy-support.md`
Closest precedent (mirror): `apps/ssh-proxy/` (PR #138 + ADR-0023 cascade from `2026-06-01-ssh-credential-flow`)

> READ-ONLY planner output. No code touched. Orchestrator (a future session) reads this to start dispatching.

---

## 1. Issue intake (orchestrator-skill required, 9 fields)

### 1.1 Problem statement
Mintkey ships zero email-proxy capability. Agents have no way to send or receive email through the broker; operators have no Admin-UI surface to register Gmail/Outlook/IMAP credentials. ADR-0024 is approved and the Kiro spec is complete, but no code, contracts, schemas, compose entries, or UI exist. This remediation lands the full vertical slice (contracts → backend Go service → admin-api + UI → infra + docs).

### 1.2 User-visible symptom
- `mintkey_discover` does not list any `email_*` services.
- Admin UI has no "Email services" resource.
- `docker compose up` does not start an `email-proxy` container.
- `vault.proto` enum stops at `AUTH_SCHEME_SSH_PASSWORD = 13`; no email auth schemes exist.

### 1.3 Expected behavior
End-to-end happy path: operator registers a Gmail service via OAuth2 in Admin UI → refresh token stored in vault-adapter → agent with `send:email` scope on that service calls MCP tool `send_email` → email-proxy validates brokered JWT, fetches credential, sends via SMTP, emits sanitised audit event into the hash chain. Plus matching IMAP read paths and the 9 MCP tools listed in design.md §"MCP Tools Design".

### 1.4 Evidence
- `.kiro/specs/email-proxy/requirements.md` — 16 user stories, ~80 ACs, NFR-1..NFR-36
- `.kiro/specs/email-proxy/design.md` — full architecture, 3 sequence diagrams, REST + MCP contracts, directory layout, security considerations SEC-01..SEC-08
- `.kiro/specs/email-proxy/tasks.md` — 7-milestone, 55-task breakdown (this planner mirrors but condenses into orchestrator chunks)
- `docs/architecture/01-architecture/adr/0024-email-proxy-support.md` — approved ADR (referenced from spec)
- `apps/ssh-proxy/` — full precedent: `cmd/`, `internal/{auth,backend,config,server,vault,audit,metrics,trace,...}`, `Dockerfile`, `go.mod` (module `github.com/mintkey/mintkey/services/ssh-proxy`)
- `docs/architecture/contracts/vault-adapter/vault.proto:99-107` — `AUTH_SCHEME_SSH_*` lives at 11/12/13; email needs 14/15/16
- `.github/workflows/container-scan.yml:102-106` — ssh-proxy matrix entry to copy
- `infra/compose/docker-compose.yml:503-529` — ssh-proxy service block to mirror
- `infra/compose/docker-compose.ghcr.yml`, `infra/compose/docker-compose.test.yml` — also need entries
- `docs/HOW-TO.md` — needs an email-proxy section
- `install.sh`, `scripts/dev-install.sh`, `.env.example` — need email-proxy env wiring

### 1.5 Scope
**MAY change**:
- `apps/email-proxy/**` (NEW Go service)
- `docs/architecture/contracts/vault-adapter/vault.proto` (3 new enum values)
- `docs/architecture/contracts/rest/openapi.yaml` (email endpoints + schemas)
- `docs/architecture/contracts/mcp/tools.yaml` (9 new tools)
- `docs/architecture/contracts/events/{audit-event,change-event}.schema.json` (new event types + target_types)
- `docs/architecture/contracts/events/span-attributes.md`
- `mintkey/internal/otel/allowlist.go`, `mintkey_otel/allowlist.py`
- `apps/admin-api/src/admin_api/api/email_services.py` (NEW)
- `apps/admin-api/db/changelog/XXX-email-services.yaml` (NEW migration)
- `apps/admin-ui/src/resources/email_services.ts` (NEW)
- `apps/admin-ui/src/components/{actions,sections}/EmailService*.{tsx,test.tsx}` (NEW)
- `apps/mcp-server/skills/agent-bootstrap.md` (mention email scopes)
- `infra/compose/docker-compose.yml`, `docker-compose.ghcr.yml`, `docker-compose.test.yml`
- `.github/workflows/container-scan.yml` (matrix entry)
- `install.sh`, `scripts/dev-install.sh`, `.env.example`
- `docs/HOW-TO.md`, `docs/architecture/01-architecture/adr/README.md` (ADR index)
- `grafana/dashboards/email-proxy.json` (NEW)
- `go.work` (add email-proxy module)
- `CHANGELOG.md` (or `RELEASE_NOTES.md`)

**MUST NOT touch**:
- ssh-proxy code (frozen; copy patterns, don't refactor)
- vault-adapter credential storage path (only add the three enum values; reuse existing `email_password`/`email_oauth2`/`email_app_password` payload handling)
- Canonical agent rows (Claudiu_1, Hermes_agent1, Hermes_2, Codex_1, spotus-test-agent) — use `scripts/with-test-agent.sh` for any e2e
- ADR-0024 itself (already approved + adversarial-reviewed per latest commit `1e74d45`)
- Broker JWKS issuance (consumer only — re-use existing pattern from ssh-proxy)

### 1.6 Out of scope (Phase 1)
- Email templates, webhooks, auto-reply rules (Phase 2 per requirements.md §"Out of Scope")
- PGP/S/MIME encryption (Phase 3)
- Attachment virus scanning (Phase 2)
- Transparent IMAP :993 / SMTP :587 listeners — **DEFERRED**: design.md describes a "hybrid" approach with both protocol listeners AND REST API. Phase 1 will ship REST-only on :8088 to keep scope finite. Listener ports become a Phase 1.5 chunk gated on OQ-2.
- Real Gmail/Outlook account tests in CI (use mocked providers; reserve live test for a manual gate)

### 1.7 Risk level
**High** — security-sensitive (new credential surface, OAuth2 flow, outbound SMTP), introduces a new audit-event family, adds a new data-plane container, touches several contract files (vault.proto, openapi.yaml, tools.yaml, audit-event schema). Failure modes include: credential leakage in logs, OAuth2 CSRF, IMAP/SMTP injection, rate-limit bypass, audit hash chain drift.

### 1.8 Verification target
For each chunk: `go test ./apps/email-proxy/...` green, contract tests pass (`make contracts-test` or equivalent), admin-api pytest green, admin-ui Vitest green, Playwright smoke for OAuth2 setup form, live `make dev` rebuild → register a mock-provider email service → agent calls `send_email` via MCP → 200 with `message_id` → audit event lands in DB with sanitised fields. Final C-FINAL reviewer runs the full 9-AC suite below.

### 1.9 Owner decisions needed (Open Questions)
See §5 below.

---

## 2. Definition-of-Done — 9 acceptance criteria

| # | AC | Status |
|---|---|---|
| AC-1 | **Contracts**: vault.proto adds `AUTH_SCHEME_EMAIL_PASSWORD=14`, `AUTH_SCHEME_EMAIL_OAUTH2=15`, `AUTH_SCHEME_EMAIL_APP_PASSWORD=16`. openapi.yaml + mcp/tools.yaml + audit-event.schema.json + change-event.schema.json + span-attributes.md all reflect email surface. `make contracts-test` green. | red |
| AC-2 | **Backend skeleton**: `apps/email-proxy/` builds (`go build ./...`), unit tests `go test ./... -short` green, Dockerfile produces a runnable image. Module path `github.com/mintkey/mintkey/services/email-proxy`. `go.work` updated. | red |
| AC-3 | **Auth + security primitives**: JWT validation via broker JWKS (Ed25519, force-refresh on unknown kid per ADR-0016.2), RFC 5322 address parser rejects `\r\n` injection, domain allowlist enforced, rate limiting via Postgres advisory locks. Red-team tests pass (`tests/security/test_email_proxy_redteam.py`). | red |
| AC-4 | **REST API + 9 endpoints**: all endpoints in design.md §"REST API Design" implemented and reachable on :8088 with brokered-JWT auth. Permission checks enforce `read:email` / `send:email` / `write:email` / `delete:email`. Handler unit tests cover success + 4xx paths. | red |
| AC-5 | **IMAP/SMTP clients + connection pool**: per-service IMAP pool (default 5 conns, 5-min idle), UIDVALIDITY tracking, SMTP per-op connect. OAuth2 (Gmail + Outlook) with singleflight refresh. Mock-provider integration tests green. | red |
| AC-6 | **Audit + observability**: emits all 13 event types listed in design.md §10 via `auditq.Queue` → admin-api → Postgres with per-tenant hash chain (`prev_hash`+`hash`). Search queries logged length-only; recipient counts only; subject truncated to 100 chars. Prom metrics + OTel spans wired with attribute allowlist. | red |
| AC-7 | **Admin-API + DB**: `email_services` table created via Liquibase migration with FK to `services`, RLS policy applied. CRUD + OAuth2 authorize/callback endpoints land. Services + email_services insert in single transaction (AC-10.6 / AC-11.10). | red |
| AC-8 | **Admin-UI**: `email_services` AdminJS resource with list/detail/create/edit/delete, OAuth2 setup component with cryptographic `state` CSRF protection, re-authorize flow on `auth_expired`, intro section. Vitest + Playwright happy-path green. | red |
| AC-9 | **Infra + docs + integration**: `email-proxy` container in `docker-compose.yml`, `.ghcr.yml`, `.test.yml`; container-scan matrix entry; `install.sh` + `dev-install.sh` + `.env.example` updated; HOW-TO.md section; ADR README index entry; CHANGELOG; agent-bootstrap.md mentions email scopes; Grafana dashboard imports clean. Full `make dev` → register Gmail (mock) → agent sends email → audit event visible. | red |

---

## 3. Chunk plan

| # | Chunk | Owner files | Depends on | Effort | Status | Round |
|---|---|---|---|---|---|---|
| **C-0** | BASELINE-REVIEWER — read intake, confirm spec/ADR/precedent, capture current state, branch from `1e74d45`, record `go build` + contracts test baselines. No code. | (read-only) | — | 0.25d | pending | — |
| **C-1** | **Contracts**. vault.proto enum values 14/15/16, openapi.yaml schemas + 9 endpoints, mcp/tools.yaml 9 tools, audit-event.schema.json + change-event.schema.json event/target_type additions, span-attributes.md updates, OTel allowlist (Go+Py). `make contracts-test` green. | `docs/architecture/contracts/**`, `mintkey/internal/otel/allowlist.go`, `mintkey_otel/allowlist.py` | C-0 | 1.0d | pending | — |
| **C-2** | **Go skeleton + config + JWT auth + JWKS**. `apps/email-proxy/{cmd,internal/{config,auth}}`, `go.mod`, `Dockerfile`, `go.work` entry. JWT validation against broker JWKS (Ed25519, kid force-refresh). Unit tests for config + jwt + jwks. `go build ./...` + `go test ./... -short` green. | `apps/email-proxy/cmd/email-proxy/main.go` (stub), `apps/email-proxy/internal/{config,auth}/*.go`, `apps/email-proxy/{go.mod,Dockerfile}`, `go.work` | C-1 | 1.5d | pending | — |
| **C-3** | **Security primitives**. RFC 5322 parser, IMAP/SMTP injection prevention (header sanitiser, parameterised SEARCH), domain allowlist, rate limiter (Postgres advisory locks). 100% branch coverage on red-team payloads. | `apps/email-proxy/internal/security/{injection,rfc5322,ratelimit}.go` + tests | C-2 | 1.5d | pending | — |
| **C-4** | **IMAP client + connection pool**. go-imap wrapper: connect (password + OAuth2 XOAUTH2), list mailboxes, fetch envelopes, fetch full message, search (parameterised), move, delete, flags. Per-service pool with UIDVALIDITY tracking, 5-conn default, 5-min idle. Mock-IMAP unit tests. | `apps/email-proxy/internal/{imap,pool}/*.go` + tests | C-2 | 2.5d | pending | — |
| **C-5** | **SMTP client + send + MIME**. go-message MIME builder, SMTP send with per-op connect (no pool), attachments up to 25MB / message 50MB, multiple recipients, address validation via security.rfc5322. Mock-SMTP unit tests. | `apps/email-proxy/internal/smtp/*.go` + tests | C-2, C-3 | 1.5d | pending | — |
| **C-6** | **OAuth2 handlers**. Gmail + Outlook providers, Provider interface, token exchange + refresh, singleflight to prevent refresh storms, expiration detection → `email.service.auth_expired` event. Mock-provider unit tests. | `apps/email-proxy/internal/oauth2/*.go` + tests | C-2 | 2.0d | pending | — |
| **C-7** | **REST API server + handlers + middleware**. chi router, JWT middleware, logging middleware, 9 endpoints, health/ready, error sanitiser, request size limits. Handler tests with mocked pool/SMTP/OAuth2/Vault. | `apps/email-proxy/internal/api/*.go` + tests | C-3, C-4, C-5, C-6 | 2.0d | pending | — |
| **C-8** | **Audit emitter + metrics + tracing + wire-up in main.go**. auditq.Queue integration (Event struct, prev_hash/hash chain), all 13 audit event types, Prom metrics, OTel spans (allowlist-enforced). Wire all components in `cmd/email-proxy/main.go`, graceful shutdown. | `apps/email-proxy/internal/{audit,metrics,trace}/*.go`, `apps/email-proxy/cmd/email-proxy/main.go` | C-7 | 1.5d | pending | — |
| **C-9** | **Admin-API endpoints + DB migration**. Liquibase migration `XXX-email-services.yaml` with FK + RLS. CRUD + test-connection + OAuth2 authorize/callback endpoints. Single-transaction insert for `services` + `email_services`. Pytest green. | `apps/admin-api/src/admin_api/api/email_services.py` + test, `apps/admin-api/db/changelog/XXX-email-services.yaml`, `apps/admin-api/db/changelog/db.changelog-master.yaml` | C-1 | 2.0d | pending | — |
| **C-10** | **Admin-UI resource + create form + OAuth2 component + intro**. AdminJS resource registration, EmailServiceCreateForm with provider switch, EmailServiceOAuth2Setup with cryptographic state CSRF, re-authorize flow, EmailServicesIntro. Vitest + Playwright smoke. | `apps/admin-ui/src/resources/email_services.ts`, `apps/admin-ui/src/components/{actions,sections}/EmailService*.{tsx,test.tsx}` | C-9 | 2.5d | pending | — |
| **C-11** | **Compose + container-scan + install + env**. `infra/compose/docker-compose.yml` + `.ghcr.yml` + `.test.yml` add `email-proxy` service. `.github/workflows/container-scan.yml` matrix entry. `install.sh`, `scripts/dev-install.sh`, `.env.example` updated. | `infra/compose/docker-compose*.yml`, `.github/workflows/container-scan.yml`, `install.sh`, `scripts/dev-install.sh`, `.env.example` | C-8 | 0.75d | pending | — |
| **C-12** | **Docs + observability dashboard + bootstrap skill + CHANGELOG**. `docs/HOW-TO.md` section, `docs/architecture/01-architecture/adr/README.md` ADR-0024 index entry (likely already present — verify), `docs/user-guide/email-proxy.md`, `docs/api-reference/email-proxy.md`, `grafana/dashboards/email-proxy.json`, `apps/mcp-server/skills/agent-bootstrap.md` email-scope note, `CHANGELOG.md` entry. | docs + grafana + skills + CHANGELOG | C-8 | 1.0d | pending | — |
| **C-13** | **Architecture + red-team + integration tests**. `tests/architecture/test_email_proxy_security.py` (no plaintext creds in logs, audit events emitted, JWKS not shared secret), `tests/security/test_email_proxy_redteam.py` (injection, domain bypass, rate-limit bypass, OAuth2 storm). `tests/integration/email_proxy/test_email_flow.py` against mock providers. | `tests/architecture/*`, `tests/security/*`, `tests/integration/email_proxy/*` | C-7, C-8, C-9, C-10 | 2.0d | pending | — |
| **C-FINAL** | **Full DoD reviewer**. Fresh Opus reviewer: run AC-1..AC-9, verify red-team suite, run `make dev` end-to-end (mock-provider Gmail + IMAP), confirm `mintkey_discover` shows email_*, agent `send_email` via MCP returns 200, audit row visible in Postgres. Cross-check tasks.md status markers match reality. | (read-only verification) | C-1..C-13 | 0.5d | pending | — |

**Total effort**: ~22 dev-days (3 dev-weeks elapsed if parallelised; ~4.5 weeks sequential). Matches Kiro spec's ~9-week single-dev estimate after subtracting acceptance-test polish + adversarial review (which are folded into C-13 + C-FINAL).

---

## 4. Parallelisation notes

After C-0 + C-1 + C-2 land (sequential):
- **C-3 (security)**, **C-4 (IMAP+pool)**, **C-5 (SMTP)**, **C-6 (OAuth2)** all operate on disjoint `apps/email-proxy/internal/{security,imap,pool,smtp,oauth2}/` subdirs → can dispatch as **parallel implementer fan-out**.
- **C-9 (admin-api + DB)** is disjoint from C-3..C-6 (Python + SQL, not Go) → can run in parallel with the C-3..C-6 wave once C-1 contracts land.
- **C-10 (admin-ui)** must serialise after C-9 (depends on admin-api endpoints).
- **C-11 (compose/CI)** and **C-12 (docs/dashboards)** are disjoint from each other and from the test work — can run parallel with C-13.
- **C-7 (REST API)** and **C-8 (wire-up)** must serialise after the C-3..C-6 wave converges.

Suggested dispatch wave plan (orchestrator):
1. Wave 1 (serial): C-0 → C-1 → C-2
2. Wave 2 (parallel ×4 Go + ×1 Python): C-3, C-4, C-5, C-6, C-9
3. Wave 3 (serial Go, parallel UI): C-7 → C-8 || C-10 (after C-9)
4. Wave 4 (parallel ops/docs): C-11 || C-12
5. Wave 5 (tests): C-13
6. Wave 6: C-FINAL

---

## 5. Open questions for owner

**RESOLVED 2026-06-02 by owner — all 4 with recommended options:**

- **OQ-1** ✅ **REST-only on `:8088`** for Phase 1. Transparent IMAP `:993` + SMTP `:587` listeners deferred to Phase 1.5 (separate chunk, post-DoD). Locks Dockerfile EXPOSE list + directory layout.
- **OQ-2** ✅ **New `MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID` + `MINTKEY_VAULT_EMAIL_PROXY_TOKEN` pair**. Matches ssh-proxy precedent + ADR-0014.4 isolation. `install.sh` + `scripts/dev-install.sh` provision them in the .env writer.
- **OQ-3** ✅ **OAuth2 `client_id` + `client_secret` on admin-api env** (single per-provider, not per-tenant). Per design.md §"OAuth2 Setup Flow". **Action item**: include an ADR-0024 corrigendum entry in C-12 documenting the env-var choice + R-7 scrubbing requirement (never echoed in `/healthz`, config dumps, error JSON).
- **OQ-4** ✅ **New `oauth2_state` Postgres table, 10-min TTL + opportunistic GC**. Server-side single-use. New Liquibase migration (verify next available number at C-9 dispatch — likely 022 or 023 depending on what merges between now and then).

**OQ-5 (CI mock provider) — deferred to implementer's discretion.** Recommendation stands: emersion go-imap in-process for unit+integration, real Gmail/Outlook on nightly + manual gate.

### Post-baseline (C-0) blockers resolved 2026-06-02

C-0 BASELINE-REVIEWER surfaced two HARD blockers requiring owner decisions before C-1 dispatch. Both resolved with recommended options:

- **B1 ✅ OAuth2 refresh `client_secret` location**: admin-api proxies the refresh. New internal endpoint `POST /v1/internal/oauth2/{provider}/refresh?service_id=...` — email-proxy calls it (with its identity token); admin-api holds `client_secret` env, performs the Google/Microsoft `/token` POST, returns new `access_token`. Single source of truth; matches ADR-D7 intent. **C-1 must add this endpoint to `openapi.yaml`'s internal section.**
- **B2 ✅ Audit event count**: 13-event superset from `tasks.md` Task 1.5 (includes `email.mailboxes.listed`, `email.messages.listed`, `email.message.flags_updated`, `email.message.read`). **C-1 writes `audit-event.schema.json` with the 13.** C-12 will update `design.md §10` + ADR-0024 to match (currently list only 10).

C-0 also flagged one SOFT correction:
- **S1 ✅ vault-adapter payload handling not pre-existing**: Plan §1.5 incorrectly claimed vault-adapter has existing `email_password`/`email_oauth2`/`email_app_password` payload handlers. Grep confirms zero matches. **Fold into C-1**: alongside proto enum additions, add Go encoder/decoder for the 3 new schemes in `apps/vault-adapter/internal/credstore/` (or wherever the existing per-scheme encoders live). +0.5d to C-1.

Plus several smaller items for C-1 brief:
- env-var naming: use `_TOKEN` (short form, matches ssh-proxy precedent) not `_IDENTITY_TOKEN` from design.md.
- healthz/metrics port: pick :8090 (or another free port — verify against PORTS.md). `:8087` is already used by ssh-proxy healthz.
- tasks.md Task 5.4 still says "Port 993/587 exposed" — contradicts OQ-1 (REST-only). C-12 corrigendum batch updates tasks.md too.
- ADR-0024 corrigendum (C-12) must additionally document: email-proxy's TWO endpoints divergence from ADR-0023 (services.base_url canonical) — `imap_host`/`smtp_host` stay on `email_services` row, services.base_url remains nullable for email services.

---

## 6. Risk flags

- **R-1 (security — credential surface)**: New auth_schemes, new outbound network class (SMTP egress). Red-team chunk C-13 is non-optional; do not let it slip to a follow-up. Specifically test that email body / attachment content / OAuth2 tokens never appear in logs, audit rows, OTel span attributes, or error messages.
- **R-2 (breaking change — vault.proto enum)**: Adding `AUTH_SCHEME_EMAIL_*` extends the proto enum. Confirm `vault-adapter` rebuild + `kong-syncer` + admin-api proto-gen all roll forward cleanly. C-1 should include a `proto/regen` check.
- **R-3 (contract drift)**: 5 contract files change at once (vault.proto, openapi.yaml, tools.yaml, 2 schema.json). Run `make contracts-test` and any spec-syntax linter (the repo has `_review-syntax-and-kiro.md` precedent) BEFORE wave 2 dispatches.
- **R-4 (audit hash chain)**: New event types must not break the per-tenant prev_hash → hash invariant. Add a chain-continuity check in C-13.
- **R-5 (RLS)**: `email_services` table needs an RLS policy matching `services`. If forgotten, cross-tenant credential leak. C-9 must include an architecture test that grep-asserts the RLS policy exists on the new table.
- **R-6 (rate-limit advisory lock key collision)**: `hashtext('email_rate_limit:' || agent_id || ':' || service_id)` could collide with future rate limiters. Recommend a namespace prefix table or `hashtextextended` with a dedicated namespace constant.
- **R-7 (OAuth2 client_secret in env)**: Per OQ-3, if admin-api holds client_secret in env-var, ensure it's NOT echoed in `/healthz` / config endpoints and is scrubbed from any error dumps.
- **R-8 (scope creep — hybrid IMAP/SMTP listeners)**: Design doc keeps oscillating between REST-only and full protocol listeners. OQ-1 MUST be resolved before C-2 or the directory layout / Dockerfile EXPOSE list churns.

---

## 7. Current round

Round 1, C-1 PASS (2026-06-02). All contract-level additions for email-proxy landed. Validation:
- `vault.proto`: AUTH_SCHEME_EMAIL_PASSWORD=14, AUTH_SCHEME_EMAIL_OAUTH2=15, AUTH_SCHEME_EMAIL_APP_PASSWORD=16 added.
- `openapi.yaml`: AuthScheme named + inline enums extended; 9 /v1/email-proxy/ paths + 3 admin-api email-services paths + 1 /v1/internal/oauth2/{provider}/refresh; new schemas: EmailService, RegisterEmailServiceRequest, Mailbox, EmailMessage, EmailAttachment, EmailMessageFlags, EmailSendRequest, OAuth2RefreshResponse.
- `mcp/tools.yaml`: 9 mintkey_*_email tools + auth_scheme enum extended.
- `audit-event.schema.json`: 13 email.* event types in oneOf + discriminator.mapping.
- `change-event.schema.json`: 3 email.service.* events in oneOf + discriminator.mapping + mintkey:service channel.
- `docs/architecture/contracts/otel/span-attributes.md`: new file, 6 email attrs.
- `packages/go/otelinit/allowlist.go`: new file, emailAllowedAttrs map + IsEmailAllowed() + isSensitive updated.
- `packages/python/mintkey-models/mintkey_models/otel_redaction.py`: EMAIL_SPAN_ATTRS frozenset + _is_redacted_name updated.
- `apps/vault-adapter/internal/emailvault/payloads.go`: new file, encoder/decoder for 3 email schemes with validation.
- `apps/vault-adapter/internal/emailvault/payloads_test.go`: 19 unit tests, all PASS.
- `apps/admin-api/tests/unit/admin_api/test_email_proxy_contract_parity.py`: 19 assertions, all PASS.
- Full admin-api unit suite: 138 passed, no regressions.
- YAML lint (openapi.yaml, tools.yaml): PASS. JSON lint (audit-event, change-event): PASS. ruff check src/: PASS.
- `make contracts-test`: target does not exist (noted for C-2 follow-up).
- pb.go regen deferred to C-2 (per discipline — no protoc in this chunk).

## 8. Round history (append-only)

- 2026-06-02 — planner session produced this `00-plan.md`. tasks.md banner added. No code touched.
- 2026-06-02 — C-1 IMPLEMENTER: all contract-level additions landed. 19 Go tests + 19 pytest assertions green. Single commit on feat/email-proxy.

## 9. Notes

- Chunks must comply with `hard-rules.md` (test-first, no `--no-verify`, no `Co-Authored-By: Claude` trailer, conventional commits).
- Use `scripts/with-test-agent.sh` for e2e tests needing `mk_agent_*` keys — never UPDATE canonical agents.
- Rebuilds via `make dev` from repo root, never raw `docker compose -f infra/...`.
- Branch off `1e74d45` (HEAD of `chore/docs-pr-a-install-and-contracts`) as `feat/email-proxy`. Confirm at C-0 that this commit carries the latest ADR-0024 adversarial-review fixes.
- Tasks.md milestone breakdown remains the design-time reference; this orchestrator plan is the dispatch unit.
- Tasks 1.1 (ADR-0024) and 1.8 (Kiro spec) are already `Complete` per tasks.md.
