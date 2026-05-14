# PROMPT — Admin UI rework (paste into Claude Code / Sonnet)

> Run from `$PROJECT_ROOT/`. This refines `team/remediation/MEGA_PROMPT.md` **Phase 3** (Admin UI) — the full per-screen UX spec is `team/remediation/ADMIN_UI_SPEC.md`, which is the authority for this work. It can be run standalone or fed to the orchestrator (`team/remediation/ORCHESTRATOR_PROMPT.md`) as a sequence of chunks.

## Copy-paste command (paste this into a Claude Code session in the repo)

> Read `team/remediation/PROMPT_ADMIN_UI.md`, `team/remediation/ADMIN_UI_SPEC.md`, and `team/remediation/MEGA_PROMPT.md`, then execute the admin-UI rework per `PROMPT_ADMIN_UI.md`. **Test-first; validate via tools (run the tests, paste the output, render the UI in a browser with a screenshot or DOM assertion — no "looks fine" claims); and end-to-end test the service-onboarding flow through the UI.** Navigate code with Serena MCP, never dump whole files. Do not stop, hand back, or summarize-and-quit until the Definition of Done is green and you've pasted the proof — especially the end-to-end-through-the-UI test output.

## 0. Mission

Rework `admin-ui/` per `team/remediation/ADMIN_UI_SPEC.md`: make AdminJS actually boot and show data; replace the default "Welcome to AdminJS" landing with a real onboarding dashboard; turn the auth-scheme field into a dropdown with the right conditional fields per scheme; add a working "Test Connection" button; make the credential↔service relationship unambiguous on every screen; and clean up every other screen (Agents + the MCP "Connect" panel, Permissions with dropdowns + structured constraints, API Keys, Audit, Tenants). **The work is judged by tests, not by appearance** — see §4.

## 1. Definition of Done — all green, with command/screenshot proof for each

(This is `ADMIN_UI_SPEC.md` §6, restated as the gate.)

1. **AdminJS boots and is usable, with NO DB connection — it uses the admin-api REST API for all data access** (`ADMIN_UI_SPEC.md` §0). P0-1..P0-3 fixed: the `admin-ui` container starts with the custom `RestResource` adapter registered (no `NoResourceAdapterError`; no `@adminjs/sql`, no `pg`, no `connect-pg-simple`); `GET /admin/login` returns 200; logging in with the bootstrap operator (username from `./data/bootstrap-secrets/admin_password`) lands on the dashboard (the session is admin-api's; AdminJS validates it via `GET /v1/auth/whoami`); **every resource list renders with data when data exists** — sourced from admin-api `GET` calls, which enforce RLS. Prove with an automated browser test.
2. **The dashboard is the custom onboarding component** — the stateful quick-start checklist + counts + empty state from `ADMIN_UI_SPEC.md` §2.1 — not the default AdminJS landing. A test asserts the checklist reflects DB state.
3. **`auth_scheme` is a dropdown everywhere it appears** with the 8 labels from `ADMIN_UI_SPEC.md` §1.1; the Credential form renders exactly the scheme-specific fields (the custom `Edit` component); secrets are write-only (never returned by admin-api, never shown). A test picks each scheme and asserts the rendered fields + the `RegisterCredentialRequest` body it POSTs.
4. **"Test Connection" works** — reachable from the Services list and the Service detail page, POSTs to `POST /v1/tenants/{tid}/services/{sid}/test`, shows the result inline, and persists `last test` on the service. A test clicks it and asserts the result is shown and persisted.
5. **The credential↔service relationship is unambiguous** — the Service detail "Credential" panel (status badge: ✓ configured vN · ⚠ no credential · n/a (no auth) · ✗ revoked; scheme label; non-secret config fields; last-test result; Test/Rotate buttons) and the Credentials list with `Service` as the first column. A test asserts the Service detail shows the credential status.
6. **Every other screen matches `ADMIN_UI_SPEC.md` §2** — Agents (incl. the one-time-key copy-box modal and the MCP "Connect" panel with the config snippet), Permissions (agent/service/action dropdowns + the structured `Constraints` sub-form + the agent-nested route), API Keys (the create form with dropdowns + the one-time-key modal + the list with agent/service columns), Audit (right columns + filters + the `prev_hash`→`hash` linkage in the detail), Tenants (list + create + the functional "all tenants" toggle).
7. **Tests pass, in CI:** the unit (vitest/supertest) suite, the browser/integration (Playwright) suite, and the **end-to-end-through-the-UI** service-onboarding test (`ADMIN_UI_SPEC.md` §4 — the headline). The parity gates pass (OpenAPI parity, SQLAlchemy mirror, `mmdc` on every mermaid block) — relevant if you add `auth_scheme: none` (G1).
8. **Clean diff.** `git status` shows only the changes this work required; no `--no-verify`; no edits to `docs/architecture/**` to make a gate pass (the deliberate G1 enum addition is fine — but then the parity gate must pass); no committed secrets.

## 2. Hard rules (non-negotiable — same discipline as `MEGA_PROMPT.md` §2)

- **Test-first, always.** For every screen change: write the failing test (vitest/supertest for handlers, Playwright for the browser flow), run it, watch it fail for the right reason, then write the minimum code that turns it green, then re-run.
- **Validate via tools, not claims.** Run every test; paste the runner output and the Playwright run summary; render the UI in a browser and include at least one screenshot or DOM assertion per screen you changed. "It looks good" / "the dashboard is nicer now" without test output + a screenshot is **not acceptable**. No `assert true`, no `test.skip`/`it.skip`/`pytest.skip` to dodge a gap, no mocking the thing under test (don't mock AdminJS itself away in a test of an AdminJS resource handler).
- **End-to-end test the service-onboarding flow through the UI** — `ADMIN_UI_SPEC.md` §4's headline Playwright test (log in → register a service via the dropdown form → register the credential via the conditional form → click Test Connection → see ✓ → see the service detail's credential panel → create an agent → see the one-time key in the modal → grant a permission via the dropdowns → see the MCP config in the agent's Connect panel). It must run in CI. This is the single most important deliverable's proof.
- **Navigate code with Serena MCP — symbol-first.** `get_symbols_overview` / `find_symbol` / `find_referencing_symbols` / `find_implementations` for navigation; `replace_symbol_body` / `insert_after_symbol` for surgical edits; `get_diagnostics_for_file` after editing. Don't dump whole `.ts`/`.py` files into context to search them. Full-file `Read` is fine for config / markdown / small files. If Serena is down, say so, fix it, fall back, and note you were navigating blind.
- **Surgical changes.** Every changed line traces to a DoD item or a failing test. No drive-by refactors. Match existing style.
- **Don't bypass safety.** No `--no-verify`, no skipping hooks, no disabling lint/type checks.
- **Don't edit the canonical layer to pass a gate.** `docs/architecture/**` (ADRs, contracts) is the source of truth — the UI form must match the OpenAPI `RegisterCredentialRequest` variants, not the other way around. If a scheme is genuinely missing a field it needs, extend the OpenAPI (it's `M`-modifiable per ADR-0014.3), then the parity gate must pass. If the contract is *wrong* (not just incomplete), STOP and open an `OQ-NNN`.
- **Track progress / be resumable.** `TodoWrite` the chunks; maintain `PROGRESS.md` (or `ORCHESTRATION_STATE.md` if running orchestrated). If you run low on context, leave it exact and continue — don't summarize-and-stop with work remaining.
- **If a fix needs an architectural decision** not settled by an ADR (e.g. the exact cookie domain/path mechanics for the BFF relay across compose hosts; the `whoami` cache TTL — ADR-0019 leans 15 s), STOP, open an `OQ-NNN`, ask. **Already decided, not open questions:** (a) RLS scoping — admin-api enforces it from the session; AdminJS has no DB connection. (b) The write-auth model — per **ADR-0019**: a state-changing call requires the `mintkey_session` cookie AND the `AdminUiSignedRequest` JWT, the JWT's `sub`/`tnt` must match the session, and the effective identity (tenant-context + audit `actor_id`) is the **session's** — the JWT is a channel proof + `jti` replay protection, not a grant of identity; reads need only the cookie.

## 3. Context to load first (in this order)

1. `team/remediation/ADMIN_UI_SPEC.md` — **the authority for this work** (the per-screen spec, the auth-scheme model, the testing requirements, the DoD).
2. `team/remediation/MEGA_PROMPT.md` — the discipline (§2 hard rules), the verification-suite shape (§9), the XML-tagged subagent-brief format (§10).
3. `AGENTS.md` and `CLAUDE.md` — operating principles, Mintkey guardrails.
4. `docs/architecture/contracts/rest/openapi.yaml` — the `AuthScheme` enum and the `RegisterCredentialRequest` discriminated union: the **field-level source of truth** for what each auth scheme's form must collect and POST.
5. `docs/architecture/01-architecture/adr/0019-admin-ui-bff-and-write-auth.md` — **the decision record** for the BFF-over-REST model and the write-auth (cookie + JWT, must agree, identity from the session); plus `0013-adminjs-pin.md` and `.kiro/specs/mintkey-mvp/design.md §4`/`§5`, `requirements.md REQ-SEC-5`, `tasks.md T-1.0.13` + the AdminJS-resource tasks — the existing specs this refines. **As part of this work, update those Kiro-spec sections to match ADR-0019 + `ADMIN_UI_SPEC.md`** (point `design.md §5` at `ADMIN_UI_SPEC.md`; restate the signed-request middleware in `design.md §4` / `tasks.md T-1.0.13` as the ADR-0019 cookie+JWT model; drop `@adminjs/sql`/`connect-pg-simple` from the AdminJS tasks).
6. `docs/architecture/03-flows/E2E-01-builder-happy-path.md` — the operator journey the dashboard checklist and the headline test mirror.
7. The current `admin-ui/src/` — navigate with Serena (`get_symbols_overview` on `src/index.ts`, `src/auth.ts`, `src/lib/signed-request.ts`, `src/middleware/`, `src/resources/*.ts`), `admin-ui/package.json`, `admin-ui/Dockerfile`, `admin-ui/tests/`. Don't file-dump.

## 4. Prerequisites — fix or coordinate

`ADMIN_UI_SPEC.md` §0 (P0-1..P0-3): AdminJS won't boot (no resource adapter registered) / first request 500s (a Postgres session store that shouldn't exist at all — AdminJS holds no DB connection) / the admin-api REST surface AdminJS now depends on isn't complete (`whoami` is a stub, `POST .../services/{sid}/test` is missing, list/show endpoints are missing or incomplete and don't carry human-readable labels, the credential field name is wrong, the permissions route is wrong, signed-JWT verification isn't wired). **The UI rework cannot be verified until these hold.** Either fix them here (P0-1, P0-2 are admin-ui-side; P0-3 is admin-api-side) or, if you're running this as a phase under the orchestrator, ensure `MEGA_PROMPT.md` Phases 1–2 are done first. Don't proceed to the cosmetic work while the app doesn't start — fix P0-1 and P0-2 in chunk 0, and confirm/fix the P0-3 endpoints as you reach the screens that need them.

## 5. Phase / chunk order (each chunk = test-first, then the code, then verify; each leaves the UI strictly better)

| # | Chunk | Exit (test that proves it) |
|---|---|---|
| 0 | AdminJS boots + lists render via REST — P0-1 (implement the custom `RestResource`/`RestDatabase` adapter backed by admin-api REST calls; `AdminJS.registerAdapter(...)`; **remove `@adminjs/sql` and `pg`** from `package.json`), P0-2 (session owned by admin-api: `authenticate()` → `POST /v1/auth/internal-login` → relay the `mintkey_session` cookie; per-request validate via `GET /v1/auth/whoami` with a short in-process cache; **drop `connect-pg-simple`**; one auth path), and confirm the P0-3 admin-api endpoints exist (`whoami` implemented; `GET` list + `GET` one for every resource; `POST .../services/{sid}/test`). | Browser test: container starts (no `NoResourceAdapterError`); `/admin/login` 200; login with bootstrap password → dashboard; a seeded Services list shows ≥1 row — and that row's data came from a `GET` to admin-api, not a DB query (assert via a network spy or by stubbing admin-api). |
| 1 | Dashboard / onboarding component (`ADMIN_UI_SPEC.md §2.1`) — custom `dashboard` `{component, handler}`: checklist (stateful), counts, empty state. | Test: checklist items tick per DB state; empty state renders when nothing exists; counts match. |
| 2 | Auth-scheme dropdown + the conditional Credential `Edit` component + the 8 schemes (`§1`) — and add `auth_scheme: none` to the enum (G1) across the 5 contract files; proxy injects nothing for `none`. | Test: pick each of the 8 schemes → assert the rendered fields and the exact `RegisterCredentialRequest` variant body POSTed; secrets are `type=password`/textarea and never appear in the show view; OpenAPI-parity gate green. |
| 3 | "Test Connection" action (`§2.3`) — depends on P0-3's `POST .../services/{sid}/test` endpoint. | Test: click it → asserts the body POSTed and the result card shown; `last test` persisted on the service detail. |
| 4 | Credential↔service clarity (`§2.3` Credential panel + `§2.4` list with `Service` first; credential creation only from the Service detail page). | Test: Service detail shows the right credential status badge for {no credential / `none` / configured vN}; Credentials list's first column is the service name; no top-level "New" on Credentials. |
| 5 | Agents (`§2.5`) — the one-time-key copy-box modal (with "I've saved it" confirm, not a flash); the "Connect" panel with the MCP config snippet + copy button; the Permissions & API-Keys sub-panels. | Test: after create, the modal shows the key; the list view does NOT show the key afterward; the Connect snippet contains the `mcp_endpoint` and the key (post-create) or a placeholder (later). |
| 6 | Permissions (`§2.6`) — `Agent`/`Service`/`Action` dropdowns (action loaded after service); the structured `Constraints` sub-form (closed schema, `additionalProperties:false`); the agent-nested route `POST /v1/tenants/{tid}/agents/{aid}/permissions`. | Test: the form sends the agent-nested path with a valid `Constraints` body; an unknown constraint key is rejected client-side. |
| 7 | API Keys (`§2.7`) — the create form with `Agent`/`Service` dropdowns + `Allowed actions` multi-select (limited to the agent's grants) + `Expires at` + `Constraints`; the one-time-`plaintext_key` modal; the list with `Agent`/`Service` columns and Revoke/Rotate. | Test: create returns the one-time key in a modal; the list never shows it; revoke/rotate work. |
| 8 | Audit (`§2.8`) — columns (`Time/Event type/Actor/Target/Outcome`), filters (event_type, agent_id, service_id, time range), cursor pagination; the detail view shows `prev_hash`→`hash`. | Test: the list renders rows (RLS-scoped to the tenant); the detail shows the chain linkage. |
| 9 | Tenants (`§2.9`, PlatformAdmin only) — list + create (with `isolation_mode` dropdown) + the functional "all tenants" toggle (the AdminJS REST calls signal `platform_admin_view:true` to admin-api — query param on reads, claim in the signed request on writes — so admin-api sets `app.platform_admin_view='on'`; cross-tenant reads emit `platform_admin.access` audit). | Test: a non-PlatformAdmin doesn't see the resource; toggling "all tenants" makes admin-api return cross-tenant rows for a PlatformAdmin (assert the request carries the flag and the response widens). |
| 10 | Cross-cutting (`§3`) — branding (no AdminJS logo), nav order (Dashboard → Services → Agents → Permissions → API Keys → Audit → Tenants), the no-free-form-where-enum rule applied everywhere, admin-api problem responses surfaced as notices. | Test: nav order; the `auth_scheme`/`isolation_mode`/status fields are all `<select>`; an error response shows its `title`/`mintkey:code`. |
| 11 | **The end-to-end-through-the-UI test** (`§4` headline) — the full service-onboarding flow in the browser against the live `docker compose` stack. | The Playwright test passes in CI; you've pasted its output and at least one screenshot. |
| 12 | Parity gates if contracts touched (G1) + update `design.md §5` to point at `ADMIN_UI_SPEC.md`. | OpenAPI parity, SQLAlchemy mirror, `mmdc` all green; `design.md §5` references the spec. |

If running orchestrated: hand each chunk to an IMPLEMENTER per `MEGA_PROMPT.md §10` / `ORCHESTRATOR_PROMPT.md §8`; verify with a REVIEWER per `§9` (re-runs the chunk's test, navigates the changed symbols with Serena, checks for fake tests / `--no-verify` / contract edits, demands the screenshot).

## 6. Verification suite — run ALL of these; paste ALL output (and screenshots) in the report

```sh
# stack
docker compose up -d --build && sleep 5 && docker compose ps
# admin-ui boots + login page
curl -fsS http://localhost:${ADMIN_UI_PORT:-3000}/admin/login >/dev/null && echo "login page 200" || echo "ADMIN-UI DOWN"
# unit (vitest / supertest) — must actually drive handlers, not just shapes
( cd admin-ui && npm test )
# browser / integration (Playwright) — boot admin-ui against a testcontainer Postgres, log in, drive each screen
( cd admin-ui && npx playwright test )
# THE HEADLINE: service-onboarding through the UI, against the live stack
( cd admin-ui && npx playwright test tests/e2e/service-onboarding.spec.ts )   # must pass in CI; paste output + screenshot
# parity gates (only if contracts touched — e.g. G1 auth_scheme: none)
pytest tests/architecture/ -q
python -c "import yaml,openapi_spec_validator as v; v.validate(yaml.safe_load(open('docs/architecture/contracts/rest/openapi.yaml')))"
# (run the OpenAPI /openapi.json-vs-checked-in-YAML parity diff; the SQLAlchemy sqlacodegen mirror diff)
for f in $(grep -rln '```mermaid' docs/); do npx --yes -p @mermaid-js/mermaid-cli@10 mmdc -i "$f" -o /tmp/_m.svg || echo "MERMAID FAIL: $f"; done
# diff hygiene
git status --short
git log --oneline -15
```

## 7. When you get stuck

- **Cookie relay (the BFF pattern)** — AdminJS is a backend-for-frontend: the browser holds `mintkey_session` for AdminJS's domain; AdminJS relays it on every outgoing call to admin-api (`Cookie:` header) and relays admin-api's `Set-Cookie` back to the browser at login. If the cookie domain/path don't line up across the compose hosts, that's the first thing to fix. (RLS is *not* an open question — admin-api enforces it from the session; AdminJS has no DB connection.)
- **A screen needs an admin-api endpoint that doesn't exist** (`PATCH /v1/tenants/{id}` for the Tenants edit; `POST .../agents/{aid}/rotate-key` for the Connect panel's "lost your key" path; agent `PATCH` for the Agents edit) → either add it (it's small) or hide the action and note the gap in `PROGRESS.md` and the spec's §5. Don't fake it; don't leave a button that 404s.
- **The AdminJS auto-form won't render a field that isn't a DB column** (the credential `value`, the `Constraints` sub-form, the API-key inputs) → that's expected; you need a **custom React component** (`components` on the property / a custom `Edit`/`new` action component). That's the bulk of chunks 2, 6, 7.
- **A test is flaky** (Playwright timing) → fix the wait (wait-for-selector / wait-for-response), don't `test.retry` over a real bug.
- **Never** `--no-verify`, never weaken an assertion, never delete a failing test, never edit `docs/architecture/**` to pass a gate.

## 8. Start now

1. `TodoWrite` the §1 DoD items and the §5 chunks.
2. Make sure Serena MCP is up (`uvx … serena start-mcp-server` reachable); fix it first if not.
3. Load the §3 context (navigate `admin-ui/src/` with Serena, don't file-dump).
4. Run the §6 verification suite once for the honest baseline; record it in `PROGRESS.md`.
5. Work the chunks in order, starting with chunk 0 (make AdminJS boot). Test-first every chunk; paste the test output and a screenshot per screen you change. Do not stop until §1 is fully green — and the proof you must show last is the **end-to-end-through-the-UI service-onboarding test** passing, with its output and a screenshot.
