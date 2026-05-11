# MEGA PROMPT — Drive Mintkey to a working, fully-tested implementation

> Run this in Claude Code (Sonnet) from `$PROJECT_ROOT/`.
> Read it once, top to bottom, before doing anything.
> **Companion:** `team/remediation/ORCHESTRATOR_PROMPT.md` runs this same job as an orchestrator + worker + reviewer loop. This file is the solo-agent version *and* the source of truth for the Definition of Done (§1), the hard rules (§2), the phases (§5), the endpoint-coverage requirement (§6), the verification suite (§9), and the subagent-brief format (§10) — the orchestrator prompt references all of those.

## 0. Mission

This repo contains the **specs** (ADRs under `docs/architecture/01-architecture/adr/`, Kiro specs under `.kiro/specs/`, wire contracts under `docs/architecture/contracts/`) and a **partial implementation** of Mintkey — a credential broker for AI agents. Right now the implementation is at the *"skeletons + unit-tested helper libraries that the entrypoints don't wire together"* stage: the Go services compile and their unit tests pass but their `cmd/*/main.go` are stubs; the FastAPI `admin-api` has endpoints that 500 against the real Liquibase schema; the AdminJS `admin-ui` doesn't boot (`@adminjs/sql` adapter never registered, `session` table never created); the `seed-job` stops at step 5 of 12; `docker compose up` "comes up" but the headline demo can't run past phase 1; no Go service emits traces/metrics; `audit.Emit` is a stub that always errors.

**Your job: take it from there to actually working — and do not stop until it is.** "Working" is defined precisely in §1. You will run a tight loop (assess → fix test-first → verify → repeat). You will not hand back, summarize-and-stop, or claim success until **every item in §1 is green and you have pasted the command output that proves it.** Partial completion is failure.

## 1. Definition of Done — the ONLY success criteria

Every item below must be **green**, and for each you must **show the actual command and its output** in your final report. No item may be marked done on the basis of "it should work" or a mocked test.

1. **Stack boots.** `docker compose up -d --build` → all 15 long-running containers report `healthy` within 120 s; the 2 one-shot jobs (`liquibase`, `seed-job`) exit `0`. (`docker compose ps` shows it.)
2. **Architecture tests pass.** `pytest tests/architecture/ -q` → all pass (RLS coverage, no-f-string-SQL, audit-chokepoint coverage, and any others present). No `xfail`/`skip` that masks a real gap.
3. **Every admin-API endpoint is exercised and passes.** You produce `tests/acceptance/ENDPOINT_COVERAGE.md` (see §6) listing every path×method from the **union** of `docs/architecture/contracts/rest/openapi.yaml` and the FastAPI routers in `admin-api/src/admin_api/api/*.py`, each mapped to ≥1 integration test that hits a **real testcontainer Postgres + a real Vault Adapter** and asserts the documented status code(s) and response schema — including the documented negative cases (401/403/404/409/422/429, SSRF rejection, cross-tenant isolation, replay, rate-limit, 410 on `/v1/changes?since=<unknown>`). The matrix is **100%** and the suite (`pytest tests/integration/admin_api/ -q`) passes.
4. **All unit/integration suites pass.** `cd admin-api && pytest -q`; `cd mintkey-models && pytest -q`; `cd mcp-server && pytest -q`; `cd admin-ui && npm test`; for each Go module `go test ./...`. All green. No skipped tests that hide gaps.
5. **Contract parity gates pass.** FastAPI's runtime `/openapi.json`, after canonical YAML sort, equals `docs/architecture/contracts/rest/openapi.yaml`. The SQLAlchemy mirror (`mintkey-models/mintkey_models/db.py`) equals `sqlacodegen --generator declarative` against the freshly-migrated DB. Every `mintkey` JSON schema validates (`Draft202012Validator.check_schema`). `protoc … --descriptor_set_out=/dev/null` on `vault.proto` succeeds. Every fenced ```mermaid``` block under `docs/` renders with `mmdc`.
6. **The admin UI boots and login works.** The `admin-ui` container starts with no `NoResourceAdapterError`; `GET http://localhost:<admin-ui-port>/admin/login` returns 200; logging in with the bootstrap operator (username from `./data/bootstrap-secrets/admin_password`) lands on the dashboard; every resource list (Services, Credentials, Agents, Permissions, Audit, API Keys, Tenants) renders **with data** when data exists (RLS is correctly scoped on the read connection). Prove it with an automated browser/HTTP test (Playwright or supertest against the running container), not a manual claim.
7. **The headline demo (E2E-01) passes end to end in ≤ 90 s.** `tests/acceptance/test_e2e_smoke.{sh,py}` runs the full builder happy path against the live `docker compose` stack: login → register a service (pointing at the mock backend) → register a credential **with an actual value** → `POST …/test` returns `{ok: true, status_code: 200}` → create an agent (capture the one-time API key) → grant a `(service, action)` permission → a small test agent connects to the MCP server → `list_services` → `request_token` → calls Kong `https://localhost/v1/call/<service_id>/<path>` with the JWT → **200** → the mock backend's request log shows the **real backend credential, not the agent's JWT** → a Jaeger trace exists with the expected spans (`mcp.tool_call`, `broker.issue_token`, `proxy.handle_request`, `vault.get_credential`, `proxy.upstream_call`) → the audit log contains all 9 expected event types, all with the same `tenant_id`, on a valid per-tenant hash chain → a red-team grep over all container logs + OTel exports finds **zero** occurrences of the registered plaintext credential or the agent API key.
8. **Multi-tenant + revocation scenarios pass.** Cross-tenant isolation (`tests/acceptance/test_tenant_isolation.py`): a `t_default` operator/agent/JWT cannot see or act on `t_acme` data; agent revocation propagates and denies the next proxied request within ≤ 5 s; credential rotation propagates within ≤ 30 s with zero failures; a classical `mk_svckey_…` key (long-lived-api-keys feature) can be created from the UI, used at the proxy, and revoked, with the proxy denying within `min(5 s, cache TTL)`.
9. **Clean diff.** `git status` shows only the changes your work required — no `--no-verify`, no edits to `docs/architecture/**` or the ADRs to make a parity gate pass (if the *contract* is genuinely wrong, you STOP and surface it per §7; the default bias is "make the code conform to the canonical contract"). No secrets committed.

If `git` is not initialized or you can't run something, say so explicitly and route around it — but the bar above does not move.

## 2. Hard rules (non-negotiable — Claude Code working discipline)

- **Test-first, always.** For every fix: write the failing test, run it, watch it fail *for the right reason*, then write the minimum code that turns it green, then re-run. Reference the requirement/ADR/scenario the test satisfies in the test or the commit.
- **Validate with tools, not assertions.** Never write "tests pass" / "it works" without showing the runner output and exit code. Never `assert True`, never `pytest.skip`/`xfail` to dodge a gap, never mock the thing under test. If a check needs infrastructure (Postgres, the Vault Adapter, Kong), stand it up (testcontainers / `docker compose`).
- **Navigate code with Serena MCP — symbol-first, like a senior dev with an IDE.** The Serena MCP server is configured for this repo. Use `mcp__serena__get_symbols_overview` before reading a code file; `mcp__serena__find_symbol` / `mcp__serena__find_declaration` for go-to-definition; `mcp__serena__find_referencing_symbols` / `mcp__serena__find_implementations` to trace callers and implementations ("who calls this", "every place that INSERTs into `permission_grants`", "every implementation of `VaultAdapter`"); `mcp__serena__replace_symbol_body` / `mcp__serena__insert_after_symbol` for surgical edits; `mcp__serena__get_diagnostics_for_file` after editing. **Do not dump whole code files into context to search them or "understand" a module.** Full-file `Read` is fine for config (`docker-compose.yml`, `*.yaml`, `*.json`, `Dockerfile`, `*.toml`), markdown specs/ADRs/contracts, small modules (~≤60 lines), and a test file you're rewriting. If Serena is down, say so, fix it (`uvx --from git+https://github.com/oraios/serena serena start-mcp-server …`), and only then fall back to `grep`/`Read` — noting you were navigating blind.
- **Surgical changes.** Every changed line traces to a Definition-of-Done item or a failing test. No drive-by refactors, no "while I'm here" cleanups, match existing style. (Symbol-scoped edits help you keep this true.)
- **Don't bypass safety.** No `--no-verify`, no skipping pre-commit hooks, no disabling lint/type checks. If a hook fails, fix the underlying issue.
- **Don't edit the canonical layer to make things pass.** `docs/architecture/**` (ADRs, contracts) is the source of truth. If the code disagrees with the contract, change the code. If you become convinced the *contract* is wrong, STOP, write an `OQ-NNN` in `docs/architecture/01-architecture/open-questions.md`, and ask the user — do not silently change the contract.
- **Root cause, not symptom.** When something breaks, trace it. Don't `try/except: pass` it, don't loosen an assertion, don't delete the failing test.
- **Track progress.** Use `TodoWrite` for the phases and the items within them; mark each `completed` the moment it's actually green (not batched). Maintain `PROGRESS.md` (see §8) so the work is resumable.
- **If a fix requires an architectural decision** not already settled by an ADR (e.g. "should the AdminJS read connection use `BYPASSRLS` or per-request `SET app.current_tenant`?"), STOP, write the OQ, and ask. Don't guess on architecture.
- **Delegate properly.** When you spawn subagents, brief them per §10 — XML-tagged, self-contained, bounded, with a parseable report shape. A subagent has none of your context.
- **Don't stop early.** You loop until §1 is fully green. If you run low on context, update `PROGRESS.md` with the exact next step and continue.

## 3. Context to load first (in this order — don't skip)

1. `AGENTS.md` and `CLAUDE.md` (operating principles, Mintkey guardrails, the verification-command list).
2. `.claude/skills/task-implement/SKILL.md` (the per-task workflow).
3. `.kiro/specs/mintkey-mvp/{requirements,design,tasks}.md` (the Phase-1 spec — what's supposed to exist).
4. `.kiro/specs/long-lived-api-keys/{requirements,design}.md` and `docs/architecture/01-architecture/adr/0018-classical-service-api-keys.md` (the classical-API-keys feature).
5. `docs/architecture/03-flows/E2E-01-builder-happy-path.md` (the demo you must make work) and `docs/architecture/contracts/rest/openapi.yaml` (the endpoint contract).
6. The three adversarial reviews if present in the conversation/repo (finding IDs `F-UI-*`, `F-API-*`, `F-DP-*`) — treat them as a **head start, not gospel**: re-verify each, some may be stale or already fixed, and there are certainly more.
7. Skim the code **with Serena** (`get_symbols_overview` on the package roots — `admin-api/src/admin_api/`, `admin-api/db/changelog/`, `seed-job/`, `admin-ui/src/`, `services/*/`, `mcp-server/src/`), plus `docker-compose.yml`, `tests/`.

## 4. The loop you run (repeat until §1 is fully green)

1. **Assess.** Run the §1 check suite (see §9 for the exact commands). Record each item green/red in `TodoWrite` and `PROGRESS.md`.
2. **If all green** → run the full §9 final-verification once more, paste every output, write the closing summary, and *only then* stop. Otherwise:
3. **Pick the highest-leverage red item** using the phase order in §5 (you can't test endpoints if the stack won't boot; you can't run the demo if the data plane isn't wired). Don't jump ahead.
4. **Plan the fix** in 3–6 numbered steps with a verify check per step (Karpathy's goal-driven execution). For non-trivial fixes, present the plan first.
5. **Write the failing test.** Run it. Confirm it fails for the right reason.
6. **Implement the minimum** that turns it green. Re-run the test.
7. **Run the broader suite for the area** (the relevant `pytest`/`go test`/`npm test`) — fixes regress things; catch it now.
8. **Re-run the full §1 check suite.** Update `TodoWrite` + `PROGRESS.md`.
9. **Commit** (one logical change per commit, conventional message, no `--no-verify`). Goto 1.

## 5. Phase order (do them in this order; each phase leaves the repo strictly better)

**Phase 0 — Test harness.** Stand up what you need to verify anything: a testcontainers Postgres + a way to run all Liquibase changelogs against it; a way to run a real Vault Adapter (once §Phase 4 makes it real, or a thin in-process fake until then — clearly marked); the `tests/integration/admin_api/` scaffold; the `tests/acceptance/` smoke-test scaffold and `ENDPOINT_COVERAGE.md`. If `tests/architecture/test_rls_coverage.py` etc. can't run today, make them runnable. **Exit:** you can run the full §1 check suite and it reports honest red/green.

**Phase 1 — Foundation: make the stack stop crashing on first request.** Fix the schema↔code drift (every column an `admin-api` INSERT/UPDATE references must exist — known offenders: `tenants.name`, `audit_chain_state.genesis_hash`, `permission_grants.updated_at`, `audit_events` is `at` not `created_at`); create the missing `mintkey_app_ro` read-only role with `SELECT` grants and decide+implement how its connection gets the tenant scope (RLS via `SET app.current_tenant` per request, or the documented escape — open an OQ if undecided); move each RLS policy into the **same** Liquibase changeset as its table (ADR-0015); fix the prefixed-ID round-trip so `svc_…`/`agent_…`/`svckey_…`/`perm_…` IDs returned on create are the same form used to look up / revoke / rotate; un-stub `/v1/ready` (real Vault-Adapter ping + change-channel check); finish `seed-job` steps 6–12 (AdminJS Ed25519 keypair → `./data/bootstrap-secrets/admin_ui_private.pem` + public key into the Vault Adapter; the 4 `service_identities` boot secrets; the Broker Ed25519 signing keypair; Keycloak realm import; `tenant.bootstrap_completed` audit; `--rotate-bootstrap`). **Exit:** `docker compose up` → admin-api serves requests without 500s on its core paths; `tests/architecture/` green; `seed-job` exits 0 and produces all 12 outputs.

**Phase 2 — Admin API: every endpoint, tested and working.** Build `tests/acceptance/ENDPOINT_COVERAGE.md` (the inventory), then an integration test per row, then fix every failure. Known gaps: missing `POST /v1/tenants/{tid}/services/{sid}/test` and `GET /v1/tenants/{tid}/services/{sid}`; the UI calls `/v1/tenants/{tid}/permissions` but the route is `…/agents/{aid}/permissions` (pick one, make OpenAPI authoritative); credentials accept `value` but the UI sends `plaintext` (align — and add `rotate_from`); the `Constraints` closed model lives only in `permissions.py` (move it into `mintkey-models/schemas.py`, enforce it in `api_keys.py` too); `whoami` is a stub; the audit-query endpoint selects a non-existent `created_at`; the OpenAPI `Credential` response schema promises a one-time `value` the endpoint (correctly) doesn't return — reconcile the contract or the response. Wire the `AdminUiSignedRequest` JWT verification as a dependency on all state-changing `/v1/tenants/...` routes, reading the JWT from `Authorization: Bearer`, validating `iss/aud/exp/jti` against `admin_request_jti`, deriving `tenant_id` from the `tnt` claim, and CSRF-exempting those signed-JWT routes. **Exit:** `ENDPOINT_COVERAGE.md` is 100%; `pytest tests/integration/admin_api/ -q` green; OpenAPI-parity gate green; SQLAlchemy mirror-diff gate green; `cd admin-api && pytest -q` green.

**Phase 3 — Admin UI: boots, login works, the journey is walkable.** Register the `@adminjs/sql` adapter (`AdminJS.registerAdapter({ Database, Resource })` from `@adminjs/sql`, build the `Database` from the connection, attach it); create the `connect-pg-simple` `session` table (add `createTableIfMissing: true` or a Liquibase changelog) and consolidate the two competing session middlewares into one; add a custom `Edit` component for the Credentials resource so the operator can actually paste their key (and align the field name with admin-api); make `createApiKey` actually invokable — a form (custom component) that picks an agent + service + grant-subset + expiry + constraints; align the routes the resource handlers call with the routes admin-api serves (and the header the signed-JWT goes in); add a **dashboard / empty-state** component with a numbered quick-start ("1. Register a backend service → 2. Add its credential → 3. Create an agent → 4. Grant a permission → 5. Connect your LLM"); add an agent **"Connect"** page that renders the ready-to-paste MCP client config (`{ "mcpServers": { "<agent>": { "url": "<mcp_endpoint>", "headers": { "Authorization": "Bearer <api_key>" } } } }`) with a copy button and a "shown once" treatment for the key that isn't a transient flash; delete the orphan `admin-ui/nginx.conf` (Express serves directly) or wire it properly; make `admin-ui/Dockerfile` build+run consistently with `package.json`'s scripts. **Exit:** the `admin-ui` container starts; `/admin/login` 200s; an automated test logs in with the bootstrap password and confirms every resource list renders (with data when seeded) and the create-service / create-credential / create-agent / grant-permission / create-API-key flows succeed via the UI; `cd admin-ui && npm test` green and the tests actually drive handlers, not just shapes.

**Phase 4 — Data plane: the agent→proxy→backend path actually works.** Generate the `vault.proto` Go stubs and register a real `VaultAdapter` gRPC service on the Vault Adapter (wire `PutCredential`/`GetCredential`/`ValidateServiceIdentity` to the implemented `internal/server/vault.go`, AES-256-GCM envelope crypto, the SQLite store, the DEK cache); load the KEK from the **keyfile volume**, not an env var (seed-job or an init step writes it); un-stub the proxy plugin's vault gRPC client; add the Broker's token-issuance endpoint (`POST /v1/issue`, auth'd by `svcid_mcp`) returning a real JWS Ed25519 with `iss/sub/aud/tnt/scope/jti/iat/exp` and `kid` in the JWS header, with the signing key fetched from the Vault Adapter using `svcid_broker`, and populate JWKS; make the proxy plugin an actual **go-pdk** plugin Kong loads (add `github.com/Kong/go-pdk`, implement the access phase calling the existing `jwt`/`vault`/`credential`/`scrubber`/`revocation`/`classicalkey` packages, register via `server.StartServer`, share the plugin socket with Kong in compose, set `KONG_PLUGINS`/`KONG_PLUGINSERVER_*`); implement the shared `internal/changes` LISTEN/NOTIFY subscriber (pgx `LISTEN`, heartbeat-driven reconnect, missed-event catch-up via `GET /v1/changes?since=…`) and have kong-syncer build the Kong DB-less declarative config (the `/v1/call/<service_id>/<path>` route + the virtual-host route) from Postgres and `POST` it to Kong's `/config` on every `mintkey:service` event; build real `mcp-server/Dockerfile` + `pyproject.toml` and `mock-backend/Dockerfile` + `pyproject.toml` and swap the `nginx:alpine` placeholders in `docker-compose.yml`; add the MCP server's agent-auth middleware (extract `Authorization: Bearer mk_agent_…`, validate via the admin-api internal endpoint, populate `request.state.agent_context`) and register the tenant-context middleware; make `request_token` call the Broker's `/v1/issue` and return the real JWT bundle; decide MCP-over-SSE vs the current REST tools and reconcile with ADR-0009 (if you change to REST, open an OQ — that diverges from the ADR); mount `bootstrap_secrets` (the right `svcid_*` file) and `DATABASE_URL` into the broker / vault-adapter / kong-syncer / proxy-plugin containers; reconcile the `config.go`↔`docker-compose.yml` env-var name mismatches. **Exit:** a test agent with a real Agent API Key can connect to the MCP server, `list_services`, `request_token`, and call Kong `/v1/call/<svc>/<path>` with the JWT and get 200, with the mock backend seeing the real credential.

**Phase 5 — Observability + audit.** Call `otelinit.Init()` in every Go service's `main.go`; add `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317` to compose; mount `/metrics` (`promhttp.Handler()`) on every service Prometheus scrapes; wire `internal/audit.Emit` to the real pgx store (per-tenant advisory lock, read `audit_chain_state`, insert with `prev_hash`/`hash`, update chain state) so the Go-side audit chokepoint actually works; verify the two-layer redaction (SDK filter + collector `redaction`/`attributes` processors) actually drops `*_token`/`*_secret`/`Authorization`/`Cookie`; provision the Grafana dashboards. **Exit:** Prometheus targets all `UP`; a brokered call produces a Jaeger trace with all expected spans; the audit hash chain verifies; the red-team grep is zero.

**Phase 6 — E2E-01 smoke test.** Make `tests/acceptance/test_e2e_smoke.{sh,py}` pass end to end against the live stack in ≤ 90 s, plus `tests/acceptance/test_tenant_isolation.py` and the revocation/rotation/classical-key acceptance tests. Iterate on whatever breaks — and when something breaks here, it usually means an earlier phase's "exit" was declared too generously: go back, tighten it, re-verify. **Exit:** §1 items 1, 7, 8 green.

## 6. The admin-API endpoint-coverage requirement (explicit)

Create `tests/acceptance/ENDPOINT_COVERAGE.md` with one row per **(path, method)** in the **union** of (a) every `paths:` entry in `docs/architecture/contracts/rest/openapi.yaml` and (b) every route registered by the FastAPI routers in `admin-api/src/admin_api/api/*.py` (including the internal ones). Columns: `path | method | source (openapi/router/both) | test file::test | asserted status codes | last result`. For every row:

- There is ≥ 1 integration test in `tests/integration/admin_api/` that **boots admin-api against a real testcontainer Postgres with all Liquibase changelogs applied + a real Vault Adapter** (the in-process fake is allowed only until Phase 4 lands the real one, and must be removed after), exercises the endpoint, and asserts the documented success status + response **schema** (validate the response body against the OpenAPI component schema, not just the status code).
- The documented **negative** cases are covered: 401 (no/invalid auth), 403 (wrong RBAC / wrong tenant), 404 (not found / cross-tenant), 409 (conflict — duplicate, constraint conflict), 422 (validation — bad body, closed-schema violation, SSRF/forbidden-destination), 429 (rate-limited where applicable), 410 (`/v1/changes?since=<unknown>`).
- Cross-cutting scenarios are covered as their own tests: cross-tenant isolation on every list/read endpoint; replay rejection on a signed request; the audit event is emitted (and on the hash chain) for every state-changing endpoint; the one-time secret is returned exactly once and never on subsequent reads.

The matrix must read **100%** before you may mark Phase 2 done. If an OpenAPI path has no implementation, you implement it (or, if you're convinced the path shouldn't exist, open an OQ and ask — don't just delete it). If an implemented route isn't in the OpenAPI, add it to the OpenAPI (it's `M`-modifiable per ADR-0014.3 — it's not in the immutable ADR set), then the parity gate will keep them in sync.

## 7. When you get stuck

- Diagnose the **root cause** by reading and running, not by guessing. Trace the call path end to end — with Serena (`find_referencing_symbols`, `find_implementations`), not by reading every file.
- If a tool/dependency is missing, **install it** (`uv`, `go`, `pnpm`/`npm`, `protoc`, `mmdc` via `npx`, testcontainers, etc.) — don't skip the check because the tool isn't there.
- If the **code and the canonical contract disagree**: the code conforms to the contract. The only exception is if the contract is *obviously* wrong (e.g. it returns a plaintext secret in a list response) — then STOP, open an `OQ-NNN`, and ask the user before touching the contract.
- If a fix needs an **architectural decision** not already in an ADR, STOP, open an `OQ-NNN`, and ask. Examples: `mintkey_app_ro` BYPASSRLS vs per-request `SET`; MCP-over-SSE vs REST tools; whether the seed-job's Keycloak step is still needed if auth went local-session.
- If you hit a **flaky** test, fix the flake (seed RNG, wait-for-condition instead of `sleep`, etc.) — don't `@retry` over a real bug.
- Never `--no-verify`, never weaken an assertion, never delete a failing test to "make CI green".

## 8. Resumability — if you run low on context or time

Maintain `PROGRESS.md` at the repo root with: (a) the §1 checklist with each item's current status and the command/output that last verified it; (b) which phase you're in and the current item; (c) the exact next concrete step; (d) any open `OQ-NNN`s blocking you; (e) anything surprising you learned. If you must stop, leave `PROGRESS.md` accurate and the repo in a committed state, and start the next session by re-running the §1 check suite and continuing from the first red item. **Do not summarize-and-stop with work remaining.**

## 9. The verification suite — run ALL of these; paste ALL output in the final report

```sh
# stack
docker compose up -d --build && sleep 5 && docker compose ps
# architecture + parity gates
pytest tests/architecture/ -q
python -c "import yaml,openapi_spec_validator as v; v.validate(yaml.safe_load(open('docs/architecture/contracts/rest/openapi.yaml')))"
# (run the OpenAPI-parity diff: FastAPI /openapi.json vs the checked-in YAML, canonical-sorted)
# (run the SQLAlchemy mirror diff: sqlacodegen against the migrated DB vs mintkey-models/.../db.py)
python -c "import json; from jsonschema import Draft202012Validator as V; [V.check_schema(json.load(open(p))) for p in __import__('glob').glob('docs/architecture/contracts/events/*.schema.json')]"
protoc --proto_path=docs/architecture/contracts/vault-adapter --descriptor_set_out=/dev/null docs/architecture/contracts/vault-adapter/vault.proto
for f in $(grep -rln '```mermaid' docs/); do npx --yes -p @mermaid-js/mermaid-cli@10 mmdc -i "$f" -o /tmp/_m.svg || echo "MERMAID FAIL: $f"; done
# endpoint coverage
cat tests/acceptance/ENDPOINT_COVERAGE.md   # must read 100%
pytest tests/integration/admin_api/ -q
# unit suites
( cd admin-api && pytest -q )
( cd mintkey-models && pytest -q )
( cd mcp-server && pytest -q )
( cd admin-ui && npm test )
for d in services/*/; do ( cd "$d" && go build ./... && go test ./... ); done
# UI boot + login
# (automated browser/HTTP test: /admin/login 200; login with bootstrap creds; lists render)
# end-to-end
bash tests/acceptance/test_e2e_smoke.sh   # or: pytest tests/acceptance/test_e2e_smoke.py -q   — must finish ≤ 90s
pytest tests/acceptance/test_tenant_isolation.py -q
# red-team
docker compose logs --no-color | grep -E "$(cat tests/acceptance/red-team-fingerprints.txt)" && echo "PLAINTEXT LEAK" || echo "no plaintext in logs"
# diff hygiene
git status --short
```

## 10. Delegating to subagents — the brief format you MUST use

You will spawn subagents — for parallelizable independent work (Phase 0 harness pieces, Phase 4's disjoint services), for research that would pollute your context, and for multi-perspective review. **A subagent has none of your context** — not the conversation, not this prompt, not your `TodoWrite`, not your assumptions. Brief it like a senior colleague who just walked in: state the goal and why, what you've established, what to read, the latitude it has — structured with **XML tags** so it's unambiguous, and demand a structured report back so you can branch on the result mechanically.

### Principles for a good subagent brief

- **Self-contained.** Spell out the repo path, the exact files/sections to read, prior findings (verbatim), the acceptance bar. Don't say "as discussed" or "you know the drill."
- **Bounded.** Name the files it owns ("touch only these"), a length cap, a hard "do not" list. An unbounded subagent sprawls.
- **One clear objective.** One chunk, one question, one review. If you'd give it two unrelated things, spawn two subagents.
- **State whether it writes code or just researches/reviews.** "Implement X" vs "find every caller of Y and report — edit nothing" are different jobs; say which.
- **Make the output parseable.** Demand a fixed report shape with a machine-readable status line (`STATUS: DONE|BLOCKED|ESCALATE` for implementers, `VERDICT: PASS|FAIL|ESCALATE` for reviewers) so you don't have to re-read the whole report to branch.
- **Carry the discipline.** Re-state the non-negotiables in every brief (TDD, surgical, no `--no-verify`, Serena symbol-navigation, don't edit canonical docs) — the subagent didn't read §2.
- **For reviewers: enforce independence.** "You did NOT do this work. Do not trust the summary. Re-run the checks yourself, navigate the code yourself." A reviewer that takes the implementer's word is worse than no reviewer.
- **Trust but verify.** A subagent's report describes what it intended, not necessarily what it did. After a code-writing subagent returns, check the actual `git diff` (or have a reviewer subagent do it).
- **Parallel only when disjoint.** Spawn several in one message only when they own non-overlapping files and have no inter-dependency. Never run an implementer and its reviewer in parallel.

### The XML-tagged brief template (fill the `<…>`; drop tags that don't apply)

```
<role>You are a {implementer | reviewer | researcher} subagent working in $PROJECT_ROOT/. You have none of the orchestrating agent's context — everything you need is in this brief.</role>

<objective>{one sentence — the single thing this subagent must accomplish}</objective>

<context>
- Repo: $PROJECT_ROOT/
- Read first (exact paths): {AGENTS.md; CLAUDE.md; the specific spec/ADR/contract sections}
- What is already established: {the relevant findings/decisions/prior state — concrete, with file:symbol:line}
- {On a re-attempt:} <prior_review_findings>{verbatim from the failed verdict — fix ALL of these}</prior_review_findings>
</context>

<scope>
Files you own (touch ONLY these unless genuinely unavoidable — if you must touch another, justify it in your report):
- {path 1}
- {path 2}
{For a researcher or reviewer:} You edit NOTHING. You read, navigate, run commands, and report.
</scope>

<acceptance_criteria>
All of these must hold; whoever verifies you will check each with the command in parentheses:
- {criterion 1} ({proving command})
- {criterion 2} ({proving command})
</acceptance_criteria>

<discipline>
- Navigate code with Serena MCP, like a senior dev with an IDE: `mcp__serena__get_symbols_overview` before reading a code file; `mcp__serena__find_symbol`/`find_declaration` for go-to-definition; `mcp__serena__find_referencing_symbols`/`find_implementations` to trace callers and implementations; `mcp__serena__replace_symbol_body`/`insert_after_symbol` for surgical edits; `mcp__serena__get_diagnostics_for_file` after editing. Do NOT dump whole code files into context to search them. Full-file `Read` is fine for config/markdown/small files.
- Test-first: write the failing test, run it, confirm it fails for the right reason, then write the MINIMUM code that turns it green, then re-run. Reference the requirement/ADR/scenario in the test.
- Surgical: every changed line traces to <objective>. No drive-by refactors. Match existing style.
- Never `--no-verify`; never skip hooks; never weaken/delete a failing test; never mock the thing under test; never `assert True`.
- Never edit docs/architecture/** or the ADRs to make a gate pass. If the contract is wrong, STOP and report ESCALATE — do not change the contract.
- Show command output for every claim. "It works" without output is not acceptable.
</discipline>

<workflow>
1. {step} — verify: {check}
2. {step} — verify: {check}
3. {step} — verify: {check}
{For a reviewer the workflow is: (1) run these exact commands and paste output; (2) navigate the changed symbols with Serena — does the claimed change exist? are callers intact?; (3) check the diff for anti-patterns (faked tests, skip/xfail dodging a gap, mocking the thing under test, weakened assertions, --no-verify, edits to docs/architecture/**, committed secrets); (4) verify test-first; (5) verify surgical; (6) git status clean.}
</workflow>

<output_format>
Report back in EXACTLY this shape (so it can be parsed mechanically):
{Implementer:}
  CHANGED: <file:symbol — what and why, one line each>
  NAVIGATED: <the Serena calls you used to locate/edit — proves you didn't file-dump>
  RAN: <each command + its full output, including the failing-then-passing test and get_diagnostics_for_file>
  STATUS: DONE | BLOCKED <why> | ESCALATE <architectural question for the user>
{Reviewer:}
  CHECKS: <each command + its full output>
  NAVIGATION: <Serena findings — claimed change exists? callers intact?>
  ANTI-PATTERNS: <none, or a list with file:symbol:line>
  VERDICT: PASS | FAIL <numbered specifics with file:symbol:line + proof> | ESCALATE <architectural question>
{Researcher:}
  FINDINGS: <numbered, each with file:symbol:line and evidence>
  ANSWER: <the direct answer to <objective>>
</output_format>

<constraints>
- ≤ {N} words.
- Do not touch files outside <scope>.
- {anything else specific to this subagent}
</constraints>
```

### Reviewer-specific reminders (put these in every reviewer brief)

- "You did NOT do this work. Your job is to confirm or refute that the work is genuinely done — verified, tested, clean. Do not trust the implementer's summary."
- "A criterion is met ONLY if its command is green and you have pasted the output."
- "Use Serena to confirm the claimed functions/routes/classes exist and do what's claimed (`find_symbol`, `get_symbols_overview`) and that callers aren't broken (`find_referencing_symbols`) — don't just skim the textual diff."
- "End with exactly one of `VERDICT: PASS` / `VERDICT: FAIL <numbered specifics>` / `VERDICT: ESCALATE <question>`. Do not edit any files."

(The `ORCHESTRATOR_PROMPT.md` companion contains the fully-instantiated IMPLEMENTER and REVIEWER templates built on this format — use those when running the orchestrated loop.)

## 11. Start now

1. `TodoWrite` the §1 items and the §5 phases.
2. Make sure Serena MCP is up (`uvx … serena start-mcp-server` reachable); if not, fix it first.
3. Load the §3 context (skim code with Serena, not file dumps).
4. Run the §9 suite once to get the honest baseline; record it in `PROGRESS.md`.
5. Enter the §4 loop. Do not stop until §1 is fully green and you've pasted the proof.
