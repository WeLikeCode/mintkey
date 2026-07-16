# CLAUDE.md — Mintkey

> **Authoritative project instructions for any Claude Code session in this repository.** Read this first; it overrides defaults.

---

## What this project is

**Mintkey** is a credential broker for AI agents. Operators register backend services with credentials. Agents discover services over MCP, request short‑lived JWTs, and call services through Kong (which injects credentials in‑flight). Multi‑tenant by architecture, single‑tenant by default UX.

The **architecture is settled**. It lives in [`docs/architecture/`](docs/architecture/) and is the source of truth. 20 ADRs (18 Accepted, ADR-0018 Proposed, ADR-0020 Accepted 2026-05-15) define every wire surface and behavioral guarantee. Implementation must conform.

This repo is the **implementation phase**. Code is generated from the architectural specs (Kiro‑driven, spec‑driven, test‑driven).

---

## Operating principles

These take precedence over your defaults.

### Principle 0 — Boil the ocean

> **No effort is too great. Time does not exist — only solutions.**

When you are researching, verifying, debugging, or exploring an option space:

- **Read more, not less.** If the answer might be in `docs/architecture/`, read all of it. If a spec is ambiguous, read every related ADR. If a test fails, trace every component on the path.
- **Run more tools, not fewer.** Lint, validate, type‑check, integration‑test, spike, red‑team. The cost of one extra check is a few seconds; the cost of one missed defect can be days.
- **Spawn subagents in parallel** for independent multi‑perspective reviews when the problem warrants it (security, alignment, syntax, performance — different lenses, different findings).
- **Trace through end‑to‑end.** Don't guess at the integration; follow the call from agent → MCP → broker → proxy → backend.
- **Reconcile contradictions before writing code.** If two ADRs disagree, surface it and fix it; do not paper over.

This principle governs the **process** and the **investigation**. It does **not** override Principle 4 (Simplicity First) on the **output** — boil the ocean to find the minimum solution, then ship the minimum solution.

### Principle 1 — Validate with tools, never with hallucinations

> If you cannot point to a tool's output that proves a claim, treat the claim as a hypothesis.

- **Schema validity**: run `openapi-spec-validator` / Redocly on `docs/architecture/contracts/rest/openapi.yaml`; run `Draft202012Validator.check_schema` on JSON schemas; `protoc --descriptor_set_out=/dev/null` on protos.
- **Mermaid syntax**: render every fenced ` ```mermaid ` block with `mmdc` (the mermaid-cli) before claiming it renders. Heuristic checks (no `;` in sequence message text, no raw `<X>` outside `<br/>`) are insufficient on their own.
- **DB schema**: never assert that a column exists. Run Liquibase migrations against a fresh Postgres and inspect `information_schema.columns` (or run the `sqlacodegen` diff CI step).
- **RLS coverage**: query `pg_policies` after migrations; assert every domain table has a `tenant_isolation` policy whose `qual` references `current_setting('app.current_tenant')`.
- **Plaintext credential leakage**: grep all log emissions and OTel span attributes for known credential fingerprints in red‑team mode. Zero matches required.
- **End‑to‑end behavior**: `docker compose up` + the Phase 1 milestone 1.11 smoke test. If you didn't see it pass in CI output, it didn't pass.
- **Tests**: report counts and exit codes from the actual test runner. "Tests pass" without showing the output is a hallucination, not a status.

When a tool is missing or unfamiliar, **install or learn it**, then run it. Do not skip verification because the tool isn't already there.

### Principle 2 — Implement autonomously where the contract is clear; ask where it isn't

- The contract is in `docs/architecture/contracts/`, the flows in `docs/architecture/03-flows/`, the decisions in `docs/architecture/01-architecture/adr/`. If your task is unambiguous against these, proceed without asking.
- When the task crosses a boundary not covered by an existing ADR or contract, **stop and surface the question** rather than improvise. Add it to [`docs/architecture/01-architecture/open-questions.md`](docs/architecture/01-architecture/open-questions.md) as `OQ-NNN`.
- Do not invent contract surfaces. If the OpenAPI doesn't have an endpoint and you think it should, propose it (write a small proposal under `docs/architecture/proposal/` or, for tiny additions, a TODO in the relevant ADR's open follow-ups).

Before any concrete-fix work begins: confirm the 9 intake fields are filled (`remediation/ISSUE_INTAKE_TEMPLATE.md`). If they aren't, ask the user — do NOT start.

### Principle 3 — When working autonomously, follow the loop

For any non‑trivial change:

1. **Read the relevant ADRs and contracts.** Cite them in the plan.
2. **State the plan as numbered steps with explicit verify checks per step** (Karpathy's Goal‑Driven Execution, below).
3. **Write the failing test first** (TDD). Reference the quality‑attribute scenario `S-*-*` it satisfies.
4. **Implement the minimum code that turns the test green** (Karpathy's Simplicity First, below).
5. **Run all relevant validators** (Principle 1). Capture the exit codes and salient output.
6. **Re‑read the diff** before declaring done; it should trace line‑by‑line to the user's request (Karpathy's Surgical Changes, below).
7. **Update the audit / open‑questions register / relevant doc** if the change affected an architectural surface.

Loop until the verify checks pass. Do not declare done on partial completion.

---

## Karpathy's four principles for Claude Code

*Quoted from Andrej Karpathy's published guidance for LLM coding pitfalls. Authoritative source linked at the bottom of this file.*

### 1. Think before coding

> **Don't assume. Don't hide confusion. Surface tradeoffs.**

LLMs often pick an interpretation silently and run with it. This principle forces explicit reasoning:

- **State assumptions explicitly** — if uncertain, ask rather than guess.
- **Present multiple interpretations** — don't pick silently when ambiguity exists.
- **Push back when warranted** — if a simpler approach exists, say so.
- **Stop when confused** — name what's unclear and ask for clarification.

### 2. Simplicity first

> **Minimum code that solves the problem. Nothing speculative.**

Combat the tendency toward overengineering:

- No features beyond what was asked.
- No abstractions for single‑use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If 200 lines could be 50, rewrite it.

**The test**: would a senior engineer say this is overcomplicated? If yes, simplify.

### 3. Surgical changes

> **Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports / variables / functions that YOUR changes made unused.
- Don't remove pre‑existing dead code unless asked.

**The test**: every changed line should trace directly to the user's request.

### 4. Goal‑driven execution

> **Define success criteria. Loop until verified.**

Transform imperative tasks into verifiable goals by stating a brief plan:

1. `[Step]` → verify: `[check]`
2. `[Step]` → verify: `[check]`
3. `[Step]` → verify: `[check]`

Strong success criteria let the LLM loop independently. Weak criteria (*"make it work"*) require constant clarification.

---

## Reconciling the principles

There's apparent tension between **"Boil the ocean"** (be exhaustive in process) and **"Simplicity first"** (be minimal in output). Resolve it this way:

| Phase | Apply |
|---|---|
| **Investigation** | Boil the ocean. Read everything. Run every relevant validator. Spawn subagents for parallel reviews. Don't ship until you've verified. |
| **Output** | Simplicity first. Minimum code. Surgical edits. Match existing style. Trace every line back to the request. |

A senior engineer can spend 8 hours studying a 50‑line patch — and ship those 50 lines. That's the model.

---

## Mintkey‑specific guardrails

These come from the architectural decisions and are not negotiable without an ADR change.

### Schema and storage
- **Liquibase is the source of truth for the database schema** ([ADR‑0015](docs/architecture/01-architecture/adr/0015-liquibase-schema-source-of-truth.md)). **Never add a column in SQLAlchemy.** Schema changes happen in Liquibase changelogs only; SQLAlchemy `Mapped` types are generated/mirrored from the introspected schema and verified by CI diff.
- **PostgreSQL 16** is the default DB engine.
- **Every domain table has a `tenant_id UUID NOT NULL` column** and an RLS policy ([ADR‑0008](docs/architecture/01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md), [ADR‑0014.8](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md)). RLS policy is created in the same Liquibase changeset as the table.
- **Vault Adapter default backend is Postgres** (`vault.credentials` table, `vault` schema in the `mintkey` DB, Liquibase changelog `018`). Selectable via `MINTKEY_VAULT_BACKEND={postgres|sqlite}`; SQLite retained as opt‑in fallback for offline deploys. See [ADR‑0021](docs/architecture/01-architecture/adr/0021-vault-storage-backend-postgres.md). Upgrading from a pre‑2026‑05‑31 SQLite deployment: run `make migrate-vault-sqlite-to-pg` first — see [`docs/HOW-TO.md` §5](docs/HOW-TO.md#5-vault-migration-sqlite--postgres).
- **SSH services: `services.base_url` is the canonical upstream host:port** (format: `ssh://host:port`). The credential row holds only auth material — private key, password, and `ssh_user`. Do NOT set `target_address` on SSH credentials; it is deprecated and will be removed. To change an SSH upstream, edit the service's `base_url`. Per [ADR‑0023](docs/architecture/01-architecture/adr/0023-ssh-upstream-base-url-canonical.md).

### IDs and time
- **All wire IDs are ULIDs with a stable prefix** ([ADR‑0017.11](docs/architecture/01-architecture/adr/0017-round-3-corrections.md)): `tenant_…`, `operator_…`, `agent_…`, `svc_…`, `cred_…`, `perm_…`, `audit_…`, `change_…`, `session_…`, `system_…`. Pattern: `^<prefix>_[0-9A-HJKMNP-TV-Z]{26}$`.
- **All timestamps are RFC 3339 UTC.**

### Audit and security
- **Every state change emits an audit event** ([ADR‑0001](docs/architecture/01-architecture/adr/0001-record-architecture-decisions.md), [ADR‑0014.7](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md)). The audit chokepoint is the FastAPI Admin REST API; AdminJS routes all writes through it.
- **The audit hash chain is mandatory** ([ADR‑0014.7](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md)): `prev_hash` + `hash` per row, per‑tenant chain.
- **The plaintext credential never appears in any log, audit payload, OTel span attribute, or response visible to the agent** ([S‑SEC‑1](docs/architecture/01-architecture/03-quality-attributes.md), [ADR‑0014.4](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md)). The Egress Proxy plugin holds plaintext only within request scope; no caching beyond the encrypted DEK.
- **The Agent API Key is returned plaintext exactly once** at agent creation; `agent.created` audit carries the fingerprint, never the key.
- **Span attributes are an explicit allowlist**; anything matching `*_token`, `*_secret`, `*_password`, `*_passphrase`, `Authorization`, `Cookie` is forbidden ([ADR‑0017.6](docs/architecture/01-architecture/adr/0017-round-3-corrections.md)).

### Budget enforcement
- **Budget counters live in `budget_counters` table** (Liquibase changeset `019`). Composite PK `(permission_id, period_start)`. RLS policy `tenant_isolation` + cascade FK to `permission_grants`. Per [ADR‑0029](team/drafts/ADR-0029-agent-budgets.md), [P‑011](docs/architecture/proposal/P-011-agent-budgets.md).
- **The proxy enforces budgets atomically** via `UPDATE SET used=used+1 WHERE used < ceiling RETURNING used, ceiling`. On exhaustion: HTTP 429 `budget_exceeded` with `Retry-After` header. The upstream is never called.
- **Budget config changes propagate via `mintkey:agent` channel** (reuses ADR‑0010). Proxy invalidates cached state within ≤ 5s (S‑OPS‑1).
- **Four budget audit events**: `budget.threshold_reached`, `budget.exceeded`, `budget.config_updated`, `budget.reset`. Emitted by proxy (Go) and admin‑api (Python) respectively.

### Tokens
- **JWT format is JWS Ed25519** with claims `iss="mintkey/broker"`, `sub` (agent), `aud` (service), `tnt` (tenant), `scope`, `jti`, `iat`, `exp`, optional `cnf.jkt`, optional `kid` ([ADR‑0006](docs/architecture/01-architecture/adr/0006-token-format-and-binding.md), [ADR‑0008](docs/architecture/01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md)).
- **Default TTL is 10 minutes**, configurable per service.
- **Verifiers force‑refresh JWKS on unknown `kid`** before rejecting ([ADR‑0016.2](docs/architecture/01-architecture/adr/0016-round-2-corrections.md)).

### Architecture immutability
- **ADRs are immutable once Accepted.** To change a decision, write a new ADR that supersedes the old one and update the old one's status. Do not edit accepted ADRs.
- **The OpenAPI YAML at `docs/architecture/contracts/rest/openapi.yaml` is canonical** ([ADR‑0017.1 / ADR‑0014.3](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md)). FastAPI emits OpenAPI; CI diffs it against the checked‑in YAML; any drift fails the build.

### Tech stack
- **Admin REST API + MCP Server**: Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2.x async + `asyncpg` + `authlib` + Argon2id + `structlog` + `ruff` + `mypy --strict` + `uv` ([ADR‑0005](docs/architecture/01-architecture/adr/0005-admin-tech-stack.md), [ADR‑0009](docs/architecture/01-architecture/adr/0009-mcp-server-stack-python.md), [ADR‑0012](docs/architecture/01-architecture/adr/0012-python-stack-pin.md)).
- **Admin UI**: AdminJS 7.x + Express + `express-session` + `pino` + `vitest` + `pnpm`. AdminJS holds NO DB connection (no `@adminjs/sql`, no `pg`, no `connect-pg-simple`); it is a BFF over the admin-api REST API per [ADR-0019](docs/architecture/01-architecture/adr/0019-admin-ui-bff-and-write-auth.md). Reads relay the `mintkey_session` cookie. State-changing calls require BOTH the cookie AND a signed Ed25519 `AdminUiSignedRequest` JWT — they must agree (`jwt.sub == session.operator_id`, `jwt.tnt == session.tenant_id`). The effective identity (tenant-context GUC, audit `actor_id`) comes from the SESSION, not the JWT.
- **Operator auth (admin-ui, Grafana, Jaeger) flows through Keycloak ([ADR-0020](docs/architecture/adrs/0020-sso-keycloak-canonical-idp.md)).** admin-api owns the OIDC `client_secret`; admin-ui never holds it. Internal-login is OFF by default — gated by `operators.internal_password_hash IS NULL`. Break-glass via `mintkey admin reset-password` CLI.
- **Egress Proxy plugin, Vault Adapter, Credential Broker, Kong‑syncer**: Go 1.22 + workspace + `pgx/v5` + `chi/v5` + `go-jose/v4` + `sqlc` + `slog` + `modernc.org/sqlite` + distroless ([ADR‑0011](docs/architecture/01-architecture/adr/0011-shared-go-stack.md)).
- **Egress proxy data plane**: Kong DB‑less + Go plugin via `go-pdk` ([ADR‑0004](docs/architecture/01-architecture/adr/0004-egress-proxy-kong.md)).
- **OIDC default**: Keycloak (in compose by default); Keycloak is the ONLY supported operator IdP per [ADR-0020](docs/architecture/adrs/0020-sso-keycloak-canonical-idp.md).

---

## Verification commands (use these, don't guess)

```sh
# OpenAPI 3.1 structural
python3 -c "import yaml,openapi_spec_validator as v; v.validate(yaml.safe_load(open('docs/architecture/contracts/rest/openapi.yaml')))"

# OpenAPI lint (richer feedback)
npx --yes @redocly/cli@latest lint docs/architecture/contracts/rest/openapi.yaml

# JSON Schemas (Draft 2020-12)
python3 -c "import json; from jsonschema import Draft202012Validator as V; \
[V.check_schema(json.load(open(p))) for p in [
  'docs/architecture/contracts/events/audit-event.schema.json',
  'docs/architecture/contracts/events/change-event.schema.json'])]"

# Proto
protoc --proto_path=docs/architecture/contracts/vault-adapter \
       --descriptor_set_out=/dev/null \
       docs/architecture/contracts/vault-adapter/vault.proto

# Mermaid (every fenced block in every doc must render)
for blk in $(grep -rln '```mermaid' docs/architecture/); do
  npx --yes -p @mermaid-js/mermaid-cli@10 mmdc -i "$blk" -o /tmp/check.svg
done

# YAML lint of MCP tools
python3 -c "import yaml; yaml.safe_load(open('docs/architecture/contracts/mcp/tools.yaml'))"

# RLS coverage (after Liquibase migrations against a test DB)
psql -c "SELECT tablename FROM pg_tables WHERE schemaname='public'
         AND tablename NOT IN (SELECT tablename FROM pg_policies);"
# (the result set must be EMPTY, modulo the documented allowlist)

# SQLAlchemy mirror diff (after Liquibase)
sqlacodegen --generator declarative postgresql://... > /tmp/sql.py
diff -u packages/python/mintkey-models/src/mintkey_models/sql.py /tmp/sql.py

# End-to-end smoke (Phase 1 milestone 1.11)
docker compose up -d
./scripts/e2e-smoke.sh
# ⚠ DESTRUCTIVE — wipes ALL 7 named volumes:
#   postgres_data (agents, services, audit, credentials, permission_grants, …),
#   vault_data + vault_kek, bootstrap_secrets, grafana_data, broker_wal, proxy_wal.
# ALWAYS run `bash scripts/dev-backup.sh` first.
# See docs/operations/backup-before-reset.md (EV-DESTRUCTIVE-006).
docker compose down -v

# Plaintext-in-logs red team
docker compose logs | grep -E "$(cat ./scripts/red-team-fingerprints.txt)"
# (output must be empty)

# Audit chokepoint architecture test
pytest tests/architecture/test_audit_coverage.py -v

# RLS architecture test (PgTAP)
pytest tests/architecture/test_rls_coverage.py -v
```

If a command fails or is missing, **install / write / fix it** — do not skip the check.

---

## Repo map

```
docs/
  architecture/                 # SOURCE OF TRUTH for the architectural design
    README.md                   # entry point + reading order
    _legacy-conventions.md      # the project's pre-existing ADR conventions doc
    00-vision/                  # problem, vision, personas, glossary, iteration plan, roadmap, kiro readiness
    01-architecture/
      01..05-*.md               # system context, container view, quality attrs, V&B, threat model
      adr/                      # 20 ADRs (18 accepted, ADR-0018 proposed)
      open-questions.md         # 22 OQ-* tracked items
    02-tech-stack/              # iteration-2 dashboard
    03-flows/                   # E2E-01 + 6 component flows
    04-observability/, 05-deployment/
    proposal/                   # 9 accepted proposals
    contracts/                  # iteration-4 wire contracts
      rest/openapi.yaml         # canonical REST contract (Kiro reads this)
      mcp/tools.yaml            # canonical MCP tool catalog
      events/{audit,change}-event.schema.json + span-attributes.md
      vault-adapter/vault.proto
      _review-{security,alignment,syntax-and-kiro}.md  # multi-perspective review reports
    adrs/                       # legacy path; symlinks to 01-architecture/adr/*
  onboarding/                   # team onboarding docs (architect, lead, backend, frontend, data-ml)
  requirements/                 # CSV-driven product requirements
.kiro/                          # Kiro spec workspace (specs, steering rules)
.claude/                        # Claude Code config + skills
BOOTSTRAP.md                    # repo bootstrap notes
```

---

## How to add an X (pattern library)

When the request maps onto a recognized pattern, follow the corresponding flow:

| Adding | Read first | Then change |
|---|---|---|
| A new REST endpoint | `docs/architecture/contracts/rest/openapi.yaml`, the relevant flow in `03-flows/` | Edit the canonical YAML; FastAPI handlers; tests; audit emission helper |
| A new MCP tool | `docs/architecture/contracts/mcp/tools.yaml`, [ADR‑0009](docs/architecture/01-architecture/adr/0009-mcp-server-stack-python.md) | tools.yaml; tool handler; tests |
| A new audit event type | `docs/architecture/contracts/events/audit-event.schema.json`, [ADR‑0014.7](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md) | event schema; audit emission call site; tests |
| A new auth scheme on a backend | `docs/architecture/contracts/vault-adapter/vault.proto` enum, [ADR‑0011](docs/architecture/01-architecture/adr/0011-shared-go-stack.md) | proto enum; OpenAPI enum; MCP tools enum; audit/change schemas; proxy plugin injection logic; **≤ 3 files in the proxy** per [S‑MOD‑1](docs/architecture/01-architecture/03-quality-attributes.md) |
| A new email service | [ADR‑0024](docs/architecture/01-architecture/adr/0024-email-proxy-support.md), [docs/HOW‑TO.md §6](docs/HOW-TO.md#6-email-services) | Register via Admin UI (email_password / email_oauth2 / email_app_password); grant `read:email` / `send:email` / `write:email` / `delete:email` per agent; agents call the 9 `mintkey_email_*` MCP tools; email‑proxy handles IMAP/SMTP without exposing credentials |
| An agent-stored secret capability change | [ADR‑0025](docs/architecture/01-architecture/adr/0025-agent-stored-secrets.md), `docs/architecture/contracts/mcp/tools.yaml` (secret_put/get/list/delete), `docs/architecture/contracts/rest/openapi.yaml` (AgentSecrets tag), `apps/mcp-server/src/mcp_server/tools/secret_*.py`, `apps/admin-api/src/admin_api/api/agent_secrets.py` | Update tool schema + handler; update OpenAPI AgentSecrets paths; audit_emit identifier-only payload; run `tests/acceptance/test_no_plaintext_in_secret_audit.py` gate; update [docs/HOW‑TO.md §12](docs/HOW-TO.md#12-agent-stored-secrets) |
| A schema column | the relevant Liquibase changelog under `apps/admin-api/db/changelog/` | new Liquibase changeset; regenerate SQLAlchemy mirror; update Pydantic model; update OpenAPI schema; CI diff must pass |
| An ADR | `docs/architecture/01-architecture/adr/README.md`, [ADR‑0001](docs/architecture/01-architecture/adr/0001-record-architecture-decisions.md) | `0NNN-name.md` in the canonical adr/ dir AND a symlink in `adrs/` (per the dual-path setup) |
| A flow | `docs/architecture/03-flows/00-overview.md` | new flow doc with sequence diagram + pre/post + quality-attributes + test plan + Kiro spec inputs |
| A budget constraint on a grant | [ADR‑0029](team/drafts/ADR-0029-agent-budgets.md), design §2 in `.kiro/specs/agent-budgets/design.md` | PATCH grant with `constraints.budget`; `budget_counters` row auto-created; proxy enforces; Grafana panel shows usage |

---

## Routing — remediation vs Kiro/spec-driven flow

Claude Code activates the `remediation-orchestrator` skill at `~/.claude/skills/remediation-orchestrator/SKILL.md` for the orchestration mechanics; this section is the project-side routing.

When a user asks you to make a code change, route the work using this table. **Same table appears in `remediation/README.md`, `CONTRIBUTING.md`, `AGENTS.md`, and `CLAUDE.md` — they must stay in lock-step.**

| Request Type | Required Path | Issue Intake | Reviewer |
|---|---|---|---|
| "Fix this bug" with clear evidence | `remediation/active/YYYY-MM-DD-<topic>/` | Full intake file (`remediation/ISSUE_INTAKE_TEMPLATE.md`) | Independent REVIEWER subagent |
| "Fix this bug" without clear evidence | Ask for issue intake first; **do not start** | Required BEFORE any chunk dispatch | After intake lands |
| Multi-file remediation | Orchestrator pattern required (`remediation-orchestrator` skill) | Full intake file | Independent REVIEWER per chunk |
| Security, release, auth, audit, credential, tenant isolation issue | Orchestrator pattern required | Full intake file | Independent REVIEWER per chunk |
| New feature | Kiro spec-driven flow (`.kiro/specs/`) | Use Kiro requirements + ADR/proposal | Per Kiro process |
| Wire contract change | Proposal/ADR + contract-first flow | Full intake + ADR/proposal link | ADR review + contract review |
| Database schema change | Liquibase-first flow (`apps/admin-api/db/changelog/`) | Full intake + changeset link | Schema review + migration verify |
| Documentation typo | Direct small PR allowed | Brief intake stub (Problem + Evidence) in PR body | Standard PR review |
| Dependency bump | Direct PR allowed if tests/verification included | Brief intake stub (Problem + Evidence + Verification) | Standard PR review |

### Issue intake is mandatory

For any remediation (rows 1-4 in the table), the 9 intake fields are required BEFORE chunk dispatch:

1. Problem statement
2. User-visible symptom
3. Expected behavior
4. Evidence
5. Scope
6. Out of scope
7. Risk level
8. Verification target
9. Owner decisions needed (if any)

If the user has not provided these, **ask before starting**. Do NOT guess. If already inside a session, write the gap to `03-escalations.md` and pause dispatch.

For doc-typo / dep-bump direct PRs (rows 8-9), a brief intake stub (Problem + Evidence + Verification) goes in the PR body's `## Issue Definition` section.

For Kiro/spec-driven work (row 5), use `.kiro/specs/mintkey-mvp/{requirements,design,tasks}.md` and the ADR flow at `docs/architecture/01-architecture/adr/`.

### Orchestrator pattern

For rows 3-4 (multi-file / security / release / auth / audit / credential / tenant isolation), the orchestrator pattern is **required**:

- ORCHESTRATOR (you) owns state and does not edit code.
- BASELINE-REVIEWER runs read-only verification first.
- IMPLEMENTER agents make surgical, test-first changes.
- Fresh REVIEWER agents independently verify each chunk.
- PASS / FAIL / ESCALATE — 3-strike hard-stop per chunk.

Full protocol in `~/.claude/skills/remediation-orchestrator/SKILL.md` (Claude Code) and `remediation/README.md` (project-level).

---

## Anti‑patterns (do NOT)

- ❌ Add a column in SQLAlchemy. Liquibase only.
- ❌ Edit an Accepted ADR. Write a new one.
- ❌ Bypass the audit chokepoint. Every state change goes through FastAPI.
- ❌ Cache plaintext credentials in the proxy plugin. Per‑request only ([ADR‑0014.4](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md)).
- ❌ Use per‑tenant change‑channel names. They're global; the filter is in the wrapper ([ADR‑0014.1](docs/architecture/01-architecture/adr/0014-iter-1-2-corrections.md)).
- ❌ Hand‑edit `docs/architecture/contracts/rest/openapi.yaml` to add nullable fields with the OAS 3.0 form. Use OAS 3.1 `type: [<T>, "null"]` ([ADR‑0017](docs/architecture/01-architecture/adr/0017-round-3-corrections.md)).
- ❌ Use `<X>` placeholders inside Mermaid sequence-diagram message text. Use `(X)` instead — `<X>` is parsed as HTML.
- ❌ Use `;` inside Mermaid sequenceDiagram message text. Use `,` or `—`.
- ❌ Claim "tests pass" without showing the runner output and exit code.
- ❌ Improve adjacent code while making an unrelated change.
- ❌ Pick an interpretation silently when the spec is ambiguous. Surface it.
- ❌ Pick `default` as the tenant slug — it's `t_default` ([ADR‑0017.9](docs/architecture/01-architecture/adr/0017-round-3-corrections.md)).
- ❌ Add UUIDs to wire surfaces. ULIDs with prefix only ([ADR‑0017.11](docs/architecture/01-architecture/adr/0017-round-3-corrections.md)).
- ❌ Create README.md / SUMMARY.md / NOTES.md unless explicitly requested.
- ❌ **Starting implementation without a clear issue definition.** If the user hasn't provided Problem + Expected + Evidence + Scope + Out-of-scope + Risk + Verification, ASK. Don't guess and start coding.
- ❌ **Bypassing the orchestrator pattern on multi-file fixes.** Multi-file remediations need ORCHESTRATOR + IMPLEMENTER + REVIEWER per chunk. Doing it solo skips the independent-review gate that catches bugs.

---

## When in doubt

1. **Search the architecture docs first.** Most "what should X do?" questions are answered in `docs/architecture/`.
2. **Read the adversarial review reports.** `docs/architecture/contracts/_review-{security,alignment,syntax-and-kiro}.md` enumerate 41 known findings and how they were resolved.
3. **Check the open‑questions register.** `docs/architecture/01-architecture/open-questions.md` lists 22 deferred items with phase + owner; the answer to your question may already be tracked there.
4. **Run tools to verify before claiming.** Per Principle 1.
5. **Surface ambiguity rather than guess.** Per Karpathy rule 1.

---

## Sources for the principles

- Karpathy's four rules — [andrej-karpathy-skills (GitHub)](https://github.com/forrestchang/andrej-karpathy-skills) — the canonical CLAUDE.md text quoted above.
- Background — [Karpathy's CLAUDE.md: 4 Rules That Fix LLM Coding (Luca Berton)](https://lucaberton.com/blog/karpathy-claude-md-llm-coding-principles-2026/), [Karpathy's CLAUDE.md Skills File: The Complete Guide (Antigravity)](https://antigravity.codes/blog/karpathy-claude-code-skills-guide), [Andrej Karpathy's Fix for AI Coding Agents Gone Wrong (Kristopher Dunham)](https://medium.com/@creativeaininja/andrej-karpathys-fix-for-ai-coding-agents-gone-wrong-a-single-markdown-file-6fb377097717).

---

*Last updated: 2026-05-15. Update this file when an architectural decision changes a guardrail.*
