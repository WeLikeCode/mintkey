# Admin UI Remediation + MCP Bootstrap — Mega Prompt with Orchestrator Pattern

**Status:** Proposed, 2026-05-13. Owner: orchestrator (you or future-you).
**Companion docs:**
- [`ADMIN_UI_ACTION_GRID_PROMPT.md`](ADMIN_UI_ACTION_GRID_PROMPT.md) — the prior matrix-driven action-grid prompt; superseded for the remaining work by this file.
- [`ADMIN_UI_ACTION_MATRIX.md`](ADMIN_UI_ACTION_MATRIX.md) — the Phase-0 audit output (commit `ac240b89`). The contract for what's broken.
- `mcp-server/skills/agent-bootstrap.md` — the agent-facing skill content used by chunk R6.
- [`PLAYWRIGHT_EXTENSION_PLAN.md`](PLAYWRIGHT_EXTENSION_PLAN.md) — the consolidated Playwright suite where new tests land.

---

## §1 — Findings recap

From the Phase-0 audit + Phase-1a side-finding (5 pre-existing W0–W8 test failures):

1. **`service_api_keys.createApiKey`** — AdminJS errors with "You have to implement action component for your ActionSee: the documentation". Root cause: the resource config has no `component:` line for this custom action. Per ADR-0018 the flow needs a show-once modal so the operator sees the `mk_svckey_…` plaintext exactly once.
2. **`permission_grants.new`** — submits to `/v1/tenants/{tid}/permissions` (404). The actual endpoint is `/v1/tenants/{tid}/agents/{agent_id}/permissions`.
3. **`permission_grants.delete`** — same shape: 404 because `agent_id` is missing from the URL path.
4. **`credentials.revokeCredential`** — not implemented in the UI at all. ADR-0013 §3.1 lists it as required.
5. **`bulkDelete`** — not wired on any of the 6 deletable resources. Possibly unsafe; needs explicit decision.
6. **W0–W8 pre-existing test failures (5)**: `04-agent` tests 1–2, `06-api-keys` tests 2–3 (likely overlap with R1), `07-audit` test 4. The solo-Sonnet variant of the Playwright extension landed these as "green" — they aren't. Need diagnosis.
7. **MCP unauthenticated bootstrap skill** — a new feature: any agent can call an unauthenticated MCP tool to receive `mcp-server/skills/agent-bootstrap.md` and learn how to authenticate, discover services, and use the proxy. The skill content already exists; this chunk wires it.

---

## §2 — Chunk catalog

| # | Title | Priority | Type | UX decisions surfaced | Depends on |
|---|---|---|---|---|---|
| R1 | `service_api_keys.createApiKey` show-once flow | P0 | New custom action component + handler | Decided below (see brief) | — |
| R2 | `permission_grants` endpoint routing (new + delete) | P0 | Bug fix | Decided below | — |
| R3 | `credentials.revokeCredential` action | P1 | New custom action | Decided below | — |
| R4 | `bulkDelete` wiring | P2 | New feature (or explicit non-decision) | **Recommendation: do NOT wire** for safety; document why | — |
| R5 | W0–W8 5 failing tests — diagnose + fix | P0 | Triage + targeted fixes | Diagnosis-driven | R1 likely resolves the api-keys failures |
| R6 | MCP unauthenticated bootstrap method | P0 | New MCP surface | Content pre-decided (see file) | — |
| R7 | MCP auth-chain validation + admin-api fingerprint UUID bug | **P0 (user-reported live blocker)** | Backend bug fix + e2e regression test | Diagnosis-driven (admin-api scope authorized — exception to §3) | — |
| R8 | admin-api `get_agent` wire-ID/UUID mismatch (500s) | **P1 (surfaced during R7 review — 27 admin-api 500s in 5 min)** | Backend bug fix + regression test | Helper-driven (admin-api scope authorized — exception to §3) | — |

R1 + R2 + R5 + R6 + R7 are P0; R8 is P1 (a follow-on from R7's review that's actively producing 500s in admin-api logs and likely impacting R1-redux's dropdown traffic). **R7 was the live blocker** — fixed at commit `b0147493`. R8 is the next admin-api bug class: `agents.py:338` binds a wire-prefixed ID (`agent_<32hex>` per ADR-0017) as a bare UUID, raising `invalid input syntax for type uuid` on every `GET /v1/tenants/{tid}/agents/{aid}` and the per-permissions sibling. Different code path from R7 (R7 fixed RLS context for M2M; R8 fixes wire-ID decoding for tenant-scoped GETs). R3 is P1. R4 is P2 with a recommendation to consciously skip.

**Sequencing:**
- **Critical-path first**: R7 (the live auth-chain blocker).
- **Parallel-safe with R7**: R1 (admin-ui only) and R6 (mcp-server tool registration only — does not touch admin-api). Launch alongside R7.
- **Serial after**: R5 (depends on R1 for the 06-api-keys failures) → R2 → R3.
- **R4 last** (or skipped pending user decision).

---

## §3 — Hard rules (every chunk inherits these)

**Discipline (non-negotiable):**
- **Never claim a cell is ✅ without a live-browser screenshot you READ with the Read tool.** The prior pattern of "spec passes → ship" produced 3 separate class-of-bug incidents.
- **TDD**: failing Playwright test FIRST; run it; paste the failure output in the commit body; THEN implement.
- **Update `team/remediation/ADMIN_UI_ACTION_MATRIX.md`** as part of every commit that touches an action cell. The matrix is your receipt.
- **Page Objects mandatory** (`admin-ui/e2e/pages/*.ts`) — extend, don't rewrite. Console-error fixture mandatory — import `test` from `admin-ui/e2e/fixtures/test.ts` (or wherever W0 landed it).
- **Never `--no-verify`** / `--no-gpg-sign`. **No `test.skip` / `test.fixme`** except for genuinely-not-yet-shipped features called out in this prompt; in those cases attach a `// TODO(R_n)` comment naming the chunk.
- **No `expect(true).toBe(true)`**. No hardcoded passwords. No hardcoded UUIDs except the bootstrap tenant `9593e3ba-…`.
- **One conventional commit per chunk** (`feat(admin-ui):` / `fix(admin-ui):` / `feat(mcp-server):`). Body documents: failing-then-passing transition, screenshots you read with what you saw, matrix delta.

**Scope boundaries:**
- **Permitted**: `admin-ui/**`, `mcp-server/**` (R6 only), `team/remediation/ADMIN_UI_ACTION_MATRIX.md` (always).
- **Forbidden** (escalate if a chunk needs it): `admin-api/**`, `services/**` (except `mcp-server/**` for R6), `docs/architecture/**` (except `proposal/P-*.md` if R6 needs one), `.kiro/**`, `docker-compose.yml`, Liquibase changelogs.
- Untracked-files caveat (do NOT touch except the matrix): `team/remediation/*.md` other than the matrix, `ORCHESTRATION_STATE.md`, `data/`, the `0019-*.md` ADR copies, root `package.json`/`pnpm-lock.yaml`, `admin-api/db/changelog/011-schema-fixes.yaml`, `tests/acceptance/test_classical_key.py`, `.serena/project.yml` mod.

**ESCALATE conditions (orchestrator surfaces to user):**
- A chunk requires admin-api source changes.
- An AdminJS 7.x limitation prevents a clean implementation.
- 3 consecutive failing-test-doesn't-fail rounds for the same chunk → wrong root-cause assumption.
- A UX decision the brief deferred isn't obviously resolved by reading ADR-0013 / 0014 / 0018.

---

## §4 — Common context (every chunk's IMPLEMENTER reads this)

Read first, every time:
1. `team/remediation/ADMIN_UI_ACTION_MATRIX.md` — the audit + status.
2. `team/remediation/PLAYWRIGHT_EXTENSION_PLAN.md` — where new specs live.
3. `AGENTS.md`, `CLAUDE.md` — operating guardrails.
4. The ADRs the chunk's brief calls out (R1 → ADR-0013/0018; R2 → ADR-0008; R3 → ADR-0013; R6 → ADR-0006/0007/0009).
5. The relevant `admin-ui/src/resources/<resource>.ts` file (or `mcp-server/src/...` for R6).
6. `admin-ui/src/components/index.ts` (ComponentLoader inventory).
7. `admin-ui/src/lib/{api-client,rest-resource,signed-request}.ts`.
8. `docs/architecture/contracts/rest/openapi.yaml` — confirm the backing endpoint shape.

Stack details (every chunk):
- `docker compose` project `mintkey`; admin-ui at `http://localhost:8081/admin`, admin-api at `:8080`, mcp-server at `:8001` (verify port).
- Bootstrap operator: `admin@mintkey.internal`; password at `data/bootstrap-secrets/admin_password`. Pass as `MINTKEY_ADMIN_PASSWORD` env to Playwright; as `PLAYWRIGHT_PASS` to the W0–W8 storage-state setup.
- Tenant UUID: `9593e3ba-4102-4235-9748-28d35b473214` (`t_default`).

---

## §5 — Orchestrator workflow

**You are the orchestrator. You make no code changes yourself.** Per chunk:

1. **Dispatch a Sonnet IMPLEMENTER** with the chunk's brief from §6.
2. Wait for the implementer's `STATUS: DONE` / `BLOCKED` / `ESCALATE` report.
3. **Dispatch a fresh REVIEWER** (default model / Opus) with the REVIEWER template (§7) filled with the chunk's ACs.
4. On `PASS`: move to next chunk.
5. On `FAIL <list>`: dispatch a NEW Sonnet IMPLEMENTER (not the previous one) with the FAIL findings carried into a `<prior_review_findings>` element. Loop.
6. **Hard-stop** after 3 failed reviews of the same chunk OR an `ESCALATE` from either side → surface to user.

**Parallelism** is allowed when chunks touch disjoint paths:
- R1 (admin-ui src + components/actions/) and R6 (mcp-server/) → can run in parallel.
- R2 (resources/permissions.ts + rest-resource.ts) and R6 → parallel.
- R3, R4 conflict with R1/R2 on resource files → serial after them.
- R5 spans multiple specs; best run AFTER R1 lands (it'll resolve 06-api-keys tests).

---

## §6 — Chunk briefs

Each brief is **ready to dispatch verbatim** as the `prompt` argument to a Sonnet Agent call (with `subagent_type: general-purpose`, `model: sonnet`, optionally `run_in_background: true`).

---

### R1 — `service_api_keys.createApiKey` show-once flow

```xml
<role>You are a Sonnet IMPLEMENTER in `$PROJECT_ROOT` (Mintkey repo root). The Mintkey stack runs via docker compose (admin-ui :8081, admin-api :8080). A fresh REVIEWER will verify in a real browser; do NOT report DONE without your own browser screenshot READ with the Read tool.</role>

<objective>Implement the `service_api_keys.createApiKey` custom action end-to-end so the user-reported "You have to implement action component for your ActionSee: the documentation" error is replaced with a working show-once flow per ADR-0018.

The action must:
1. Render a form with fields: `agent_id` (dropdown of the operator's agents — fetch via /v1/tenants/{tid}/agents; show agent slug + name), `service_id` (dropdown of services the chosen agent has permission grants on — fetch via /v1/tenants/{tid}/agents/{aid}/permissions; default empty until agent selected), `name` (free-text, optional, defaults to a generated slug), `expires_at` (date picker, optional — default empty = no expiry), `constraints` (read-only summary of the inherited Constraints from the selected permission grant — operators cannot widen but can narrow; v1: read-only inheritance is sufficient).
2. On submit: POST to `/v1/tenants/{tid}/agents/{aid}/api-keys` (per `docs/architecture/contracts/rest/openapi.yaml` — verify the exact request body shape). Admin-api returns `{ "key": "mk_svckey_<26-char>", "key_id": "svckey_<...>", ... }` ONCE.
3. Show the returned `key` in a **show-once modal** with: warning banner ("This is the only time you'll see this key — copy it now"), the key in a monospace box, a "Copy to clipboard" button, a "I've copied it" confirm button. The modal must not close on outside-click; only via the confirm button.
4. After confirm: redirect to the api-keys list. The new row must be visible.
5. The `key` plaintext MUST NOT be persisted in the admin-ui's local state beyond the modal's lifetime; cleared on confirm/unmount.

UX decisions (DECIDED — do not re-litigate):
- The form lives at `/admin/resources/service_api_keys/actions/new` (AdminJS default URL).
- It's an AdminJS `resource`-type custom action (not `record`).
- The custom React component lives at `admin-ui/src/components/actions/ApiKeyCreate.tsx` and is registered in `admin-ui/src/components/index.ts` as `Components.ApiKeyCreate`.
- Wired in `admin-ui/src/resources/api_keys.ts` via `actions.createApiKey.component: Components.ApiKeyCreate` (plus the existing handler).
- Form styling uses `@adminjs/design-system` primitives (Box, Input, Select, Button, Section, Label) — match the prevailing look.
</objective>

<chunk>action-grid-R1-create-api-key</chunk>

<context>
- Phase-0 audit (commit ac240b89, see ADMIN_UI_ACTION_MATRIX.md): this is the user-screenshot bug.
- ADR-0018: classical service API keys; the `mk_svckey_<…>` flow is Argon2id-hashed at rest, plaintext shown once.
- The backing endpoint per the audit's OpenAPI inventory: `POST /v1/tenants/{tid}/agents/{aid}/api-keys`. Curl-probe it first with the bootstrap session to confirm request/response shape — record it in your report.
- Existing related files to read: admin-ui/src/resources/api_keys.ts, admin-ui/src/lib/api-client.ts (signed-request flow per ADR-0019), admin-ui/src/components/index.ts (ComponentLoader, 9 components currently registered).
- The W0–W8 06-api-keys tests 2–3 are currently failing per the Phase-1a side-finding — they likely WERE asserting this flow ahead of its implementation. Your fix should make those tests pass (and you confirm so as part of your AC).
</context>

<scope>
MAY create/modify:
- `admin-ui/src/components/actions/ApiKeyCreate.tsx` (new — the React component).
- `admin-ui/src/components/index.ts` (register the new component).
- `admin-ui/src/resources/api_keys.ts` (wire `actions.createApiKey.component`).
- `admin-ui/src/lib/api-client.ts` (if a new helper is needed — keep additions surgical).
- `admin-ui/e2e/tests/32-create-api-key.spec.ts` (new Playwright spec).
- `admin-ui/e2e/pages/api-keys.ts` (extend POM).
- `team/remediation/ADMIN_UI_ACTION_MATRIX.md` (cell update).

Do NOT touch: any other resources/*.ts, the dashboard/intro components, admin-api/**, services/**, docs/architecture/**.
</scope>

<acceptance_criteria>
1. CURL EVIDENCE: bootstrap-login → POST /v1/tenants/<tid>/agents/<aid>/api-keys with valid body → 200 + `{ "key": "mk_svckey_…", "key_id": ..., ... }`. Paste trimmed JSON. Also probe with bad request (no agent_id) → expect 422 with field-level error.
2. Failing-test-first: spec at `tests/32-create-api-key.spec.ts` fails BEFORE the fix with a specific error mentioning the ActionSee component or "no records / modal not visible". Paste the failure output.
3. Component implemented: `ls admin-ui/src/components/actions/ApiKeyCreate.tsx` exists; registered in `components/index.ts`; wired in `resources/api_keys.ts`.
4. Spec passes after fix.
5. Live browser drive: `/admin/resources/service_api_keys/actions/new` renders the form with all 5 fields. Fill, submit, modal appears with a `mk_svckey_…` value, copy button works, confirm dismisses, list shows the new row. Screenshot the modal AND the list-after-create; READ both; describe what you saw (specific key prefix, specific row text).
6. Show-once safety: the `key` plaintext is NOT in any persistent state (Redux/localStorage/etc.) — verify by reading the component source; the modal's local state clears on unmount.
7. The previously-failing W0–W8 `06-api-keys` tests 2 + 3 now pass. (`pnpm test:e2e --project chromium tests/06-api-keys.spec.ts 2>&1 | tail -20` → green.)
8. Full suite still green: `pnpm test:e2e --project chromium 2>&1 | tail -25`.
9. Container healthy: `docker compose ps | grep admin-ui` → `(healthy)`; logs clean of `TypeError|ReferenceError|SyntaxError|Error rendering`.
10. Matrix updated: `ADMIN_UI_ACTION_MATRIX.md` Standard `service_api_keys/new` from ❌ → ✅; Custom `service_api_keys/create-and-show-once` from ⬜/❌ → ✅; Phase log entry added.
11. Single commit, conventional (`feat(admin-ui): service_api_keys createApiKey show-once flow (R1 of action-grid remediation)`), no `--no-verify`.
</acceptance_criteria>

<discipline>
- TDD evidence in the commit body.
- Plaintext key never leaves the modal component's local state. No `console.log(key)`.
- Use the AdminJS `Notice` API to surface "Key created" outside the modal post-confirm.
- The copy-to-clipboard button uses `navigator.clipboard.writeText` — falls back gracefully if unavailable; show a "Copy not supported" hint.
- Console-error fixture catches any JS error during the test.
- Never `--no-verify`. No `test.skip`. No hardcoded password.
</discipline>

<workflow>
1. Read AGENTS.md, CLAUDE.md, ADR-0018, ADR-0019, MATRIX, resources/api_keys.ts, lib/api-client.ts, components/index.ts.
2. Curl-probe the backing endpoint; record the request/response shape.
3. Write the failing Playwright spec (verify it fails).
4. Build the ApiKeyCreate.tsx component; register; wire.
5. Rebuild admin-ui (`docker compose up -d --no-deps --build admin-ui`).
6. Re-run the new spec; confirm pass.
7. Live-browser drive: screenshot the form + modal + post-create list; READ.
8. Run 06-api-keys.spec.ts; confirm tests 2 + 3 pass.
9. Full suite.
10. Update matrix; commit.
</workflow>

<output_format>
CHANGED: <file — purpose>
CURL EVIDENCE: <trimmed JSON>
RAN: <failing spec output, fix, rebuild, passing spec, 06-api-keys spec, full suite, git log/show>
SCREENSHOTS: <PNG paths + what you saw — modal contents, key prefix, row text>
MATRIX DELTA: <which cells changed>
STATUS: DONE | BLOCKED <specific> | ESCALATE <specific>
</output_format>

<constraints>
≤ 2800 words. Single commit. Sonnet. No --no-verify. Stop after this chunk.
</constraints>
```

---

### R2 — `permission_grants` endpoint routing (new + delete)

```xml
<role>You are a Sonnet IMPLEMENTER in `$PROJECT_ROOT` (Mintkey repo root). Stack live; bootstrap operator at admin@mintkey.internal. REVIEWER will verify; require browser-screenshot evidence.</role>

<objective>Fix `permission_grants.new` and `permission_grants.delete` to route through the correct nested admin-api endpoints. Currently both call tenant-wide URLs (`/v1/tenants/{tid}/permissions[/{pid}]`) which are 404 — the real endpoints are nested under the agent: `/v1/tenants/{tid}/agents/{aid}/permissions[/{pid}]`.

UX decisions (DECIDED):
- The `new` form keeps a top-level `agent_id` dropdown (populated from `/v1/tenants/{tid}/agents`). On submit, the BFF reads `agent_id` from the payload and constructs the URL.
- The `delete` action: each permission_grant record carries its `agent_id` in the record payload (verify in admin-api response). The BFF reads it from the record and constructs the URL for DELETE.
- No new admin-api endpoints. No schema changes. The fix is entirely in admin-ui's `rest-resource.ts` URL builder + `resources/permissions.ts`.
</objective>

<chunk>action-grid-R2-permissions-routing</chunk>

<context>
- Phase-0 audit: 404s confirmed via curl.
- Likely root cause: `RestResource`'s URL builder in `admin-ui/src/lib/rest-resource.ts` uses a flat template; permissions need a per-resource URL builder that consults the record (or the form payload) for `agent_id`.
- Survey first: read rest-resource.ts to find the URL-build path; read resources/permissions.ts to see what's currently wired; check if RestResource already supports a per-resource URL-builder hook.
- ADR-0008: multi-tenancy and the agent-scoped routing.
- The W0–W8 `05-permissions.spec.ts` may currently pass while exercising the wrong URL (if the test asserts only HTTP status, the 404 might be expected — verify and fix). Read it; if it tests the broken state, fix it.
</context>

<scope>
MAY: admin-ui/src/lib/rest-resource.ts (extend for per-resource URL builder), admin-ui/src/resources/permissions.ts (wire the builder), admin-ui/e2e/tests/33-permissions-routing.spec.ts (new), admin-ui/e2e/tests/05-permissions.spec.ts (may need updates if it was asserting broken state), admin-ui/e2e/pages/permissions.ts (extend POM), ADMIN_UI_ACTION_MATRIX.md.

Do NOT touch: admin-api/**, other resources/*.ts (unless rest-resource.ts changes require ripple), docs/architecture/**.
</scope>

<acceptance_criteria>
1. Curl confirms: `POST /v1/tenants/<tid>/agents/<aid>/permissions` exists and accepts a grant payload; `DELETE /v1/tenants/<tid>/agents/<aid>/permissions/<pid>` exists.
2. Failing test first: a spec that creates a permission_grant via the UI fails BEFORE the fix with a 404 in network logs or "not visible after create" assertion.
3. After fix: create-grant round-trip works — fill form, submit, list shows new grant, delete it, list updates.
4. The URL builder is `service_id`-aware via the record payload, not a hardcoded constant.
5. Network-traffic verification: in the spec, listen to `page.on('request')` for `POST` and `DELETE` to permission endpoints; assert the URL contains `/agents/<a-uuid-or-prefixed-id>/permissions`.
6. Existing W0–W8 `05-permissions.spec.ts` either still passes (if it was correct) or has been updated alongside the fix (commit body explains).
7. Full suite green.
8. Live-browser drive: screenshot the create form + post-create list + post-delete list; READ; describe.
9. Container healthy.
10. Matrix updated: `permission_grants/new` and `permission_grants/delete` from ❌ → ✅; Custom rows for `grant` and `revoke` updated.
11. Single commit (`fix(admin-ui): permission_grants nested under agent_id (R2 of action-grid remediation)`), no `--no-verify`.
</acceptance_criteria>

<discipline>
- TDD-evidence captured.
- Don't refactor RestResource broadly. Add a per-resource URL-builder hook surgically.
- Other resources must continue to work (services CRUD, agents CRUD, etc.) — run the full W1/W2 CRUD suite to verify.
</discipline>

<workflow>
1. Survey rest-resource.ts; identify the URL-construction point.
2. Curl-probe both endpoints; record.
3. Write failing spec; observe 404.
4. Implement per-resource URL-builder hook in rest-resource.ts; wire in permissions.ts.
5. Rebuild; re-run; verify pass.
6. Run full W1+W2 CRUD specs to confirm no regression.
7. Live-browser; screenshot; READ.
8. Update matrix; commit.
</workflow>

<output_format>
CHANGED: ...
CURL EVIDENCE: ...
RAN: ...
SCREENSHOTS: ...
MATRIX DELTA: ...
STATUS: DONE | BLOCKED | ESCALATE
</output_format>

<constraints>≤ 2400 words. Single commit. Sonnet. No --no-verify.</constraints>
```

---

### R3 — `credentials.revokeCredential` custom action

```xml
<role>Sonnet IMPLEMENTER in the Mintkey repo root. Live stack; REVIEWER verifies browser-side.</role>

<objective>Implement the `credentials.revokeCredential` custom action per ADR-0013 §3.1. The action wires `DELETE /v1/tenants/{tid}/services/{sid}/credentials/{key_version}` to a "Revoke" button on the credential show page, with a confirmation dialog.

UX decisions (DECIDED):
- Button location: credential show page (not list — operators should see context before revoking).
- Confirmation: modal dialog with the credential's slug + service slug + "Revoke" (red, destructive) and "Cancel" buttons. No "Are you sure?" double-confirm — one click after the modal is enough.
- After revoke: redirect to the credentials list; show a Notice "Credential revoked"; the revoked row remains in the list with status `revoked` (revocation does NOT delete the row per ADR-0008).
- Audit: admin-api emits the `credential.revoked` event automatically; the UI doesn't need to do anything extra.
</objective>

<chunk>action-grid-R3-revoke-credential</chunk>

<context>
- ADR-0013 §3.1: credential-revoke flow.
- ADR-0008: revocation keeps the row, sets a status.
- Backing endpoint per OpenAPI: `DELETE /v1/tenants/{tid}/services/{sid}/credentials/{key_version}` (verify shape with curl).
- Existing related: admin-ui/src/resources/credentials.ts (currently `delete: { isVisible: false }`; check if any action stub exists).
</context>

<scope>
MAY: admin-ui/src/resources/credentials.ts (add custom action + handler), admin-ui/src/components/actions/CredentialRevokeConfirm.tsx (new component), admin-ui/src/components/index.ts (register), admin-ui/e2e/tests/34-credentials-revoke.spec.ts (new), admin-ui/e2e/pages/credentials.ts (extend POM), ADMIN_UI_ACTION_MATRIX.md.

Do NOT: admin-api/**, other resources.
</scope>

<acceptance_criteria>
1. Curl evidence for the backing endpoint.
2. Failing test first.
3. After fix: revoke round-trip works — show page → Revoke button → modal → confirm → list shows status=revoked on that row.
4. Cancel button in modal closes without calling admin-api (verify via `page.on('request')`).
5. Live-browser drive: screenshot the show page with Revoke button, the modal, the post-revoke list; READ each.
6. The revoked-but-still-listed semantics: the row IS visible in the list (status `revoked`); it does NOT disappear. Verify in the screenshot.
7. Full suite green.
8. Container healthy.
9. Matrix updated.
10. Single commit (`feat(admin-ui): credentials revokeCredential action (R3 of action-grid remediation)`).
</acceptance_criteria>

<discipline>same as R1/R2; TDD; browser-verified; matrix updated.</discipline>

<workflow>survey → failing test → implement → rebuild → verify → matrix → commit.</workflow>

<output_format>CHANGED / CURL / RAN / SCREENSHOTS / MATRIX DELTA / STATUS.</output_format>

<constraints>≤ 2200 words. Single commit.</constraints>
```

---

### R4 — `bulkDelete` decision

**RECOMMENDATION**: do not implement. AdminJS's default bulkDelete UX is checkbox-multi-select on the list view → "Delete selected" button. For Mintkey:
- `services` with active permission grants → bulk-delete cascades to invalidating agent access. Hazardous.
- `agents` with active sessions → in-flight calls 401. Hazardous.
- `credentials`, `permission_grants` — moderately safer but still risky in bulk.
- `tenants` — almost certainly catastrophic; tenant-deletion is operator-confirmed-one-by-one per ADR-0016.7's cascade semantics.

**Implementer brief**: instead of wiring, write a short note in `team/remediation/ACTION_GRID_ESCALATIONS.md` explaining the safety analysis; update the matrix to mark each `<resource>/bulkDelete` cell as 🚫 (justified — not implemented for safety) with a `// see ESCALATIONS.md` link; commit a single `docs(admin-ui): document why bulkDelete is intentionally not wired (R4 of action-grid remediation)` change.

If the user overrides this recommendation → re-spec as R4-implement with explicit safety guardrails (e.g. bulkDelete requires typing the resource name to confirm, max 5 items per batch, audit-event-amplified).

---

### R5 — Diagnose + fix W0–W8 5 failing tests

```xml
<role>Sonnet IMPLEMENTER in the Mintkey repo root. Diagnostic work — 5 pre-existing failing tests in the W0–W8 Playwright suite that the solo-Sonnet variant left as "green" mid-flight.</role>

<objective>Diagnose and fix the 5 failing tests Phase-1a uncovered:
- `04-agent.spec.ts` tests 1 + 2.
- `06-api-keys.spec.ts` tests 2 + 3 (likely resolved by R1 — verify first; don't redo if R1 already lands).
- `07-audit.spec.ts` test 4.

For each: read the failing test, understand the assertion, run it, classify the failure cause:
- **(a) Test is asserting a not-yet-shipped feature** → mark `test.fixme` with a `// TODO(R_n)` comment pointing at the implementation chunk.
- **(b) Test is correct, implementation is broken** → fix the implementation (within admin-ui/** scope; ESCALATE if it requires admin-api changes).
- **(c) Test is wrong (tautological / wrong baseline / drift)** → fix the test.

Report the breakdown in the matrix's cross-cutting section and update the Phase log.
</objective>

<chunk>action-grid-R5-w0-w8-failing-tests</chunk>

<context>
- Phase-1a side-finding: `pnpm test:e2e --project chromium` returns 113 passed, 25 skipped, 5 failed. The 5 are listed above.
- R1 may resolve the 06-api-keys failures — run R1 FIRST if not done; if those tests pass after R1, mark this chunk's scope as "agent + audit only".
- Don't write fresh tests; this chunk fixes existing ones.
</context>

<scope>
MAY: admin-ui/e2e/tests/04-agent.spec.ts, 06-api-keys.spec.ts (if R1 didn't already), 07-audit.spec.ts, admin-ui/e2e/pages/* (POM extensions), admin-ui/src/resources/* (if a failure points to a real source bug), ADMIN_UI_ACTION_MATRIX.md.

Do NOT: admin-api/**, broaden the suite, add new tests.
</scope>

<acceptance_criteria>
1. Per-failure classification (a/b/c) written in the commit body.
2. Each failure resolved per its classification.
3. `pnpm test:e2e --project chromium` shows 0 failed.
4. If any (a) → the test.fixme has a TODO comment referencing the chunk that will fix it (R1, future R, or ESCALATE).
5. If any (b) → live-browser proof the implementation now works.
6. Full suite green; matrix updated.
7. Single commit (`fix(admin-ui): resolve 5 pre-existing W0-W8 test failures (R5 of action-grid remediation)`).
</acceptance_criteria>

<discipline>Don't blanket-skip. Each `test.fixme` MUST have a chunk-id justification. No tautologies introduced.</discipline>

<workflow>read each failing spec → run → diagnose → classify → fix or fixme → re-run → matrix → commit.</workflow>

<output_format>CHANGED / per-failure classification / RAN / SCREENSHOTS (if any) / MATRIX DELTA / STATUS.</output_format>

<constraints>≤ 2400 words. Single commit. May span multiple files but coherent purpose.</constraints>
```

---

### R6 — MCP unauthenticated bootstrap method

```xml
<role>Sonnet IMPLEMENTER in `$PROJECT_ROOT` (Mintkey repo root). Scope: mcp-server only. The Mintkey stack runs via docker compose (mcp-server at :8001 — verify). REVIEWER will validate via direct MCP protocol call.</role>

<objective>Expose an **unauthenticated MCP tool** that returns the contents of `mcp-server/skills/agent-bootstrap.md` (already authored — read it first). The tool teaches any agent (Claude/GPT/Gemini/custom — vendor-agnostic) how to: (a) authenticate to Mintkey, (b) discover services, (c) call the proxy. Without it agents need a pre-installed Mintkey skill; with it they self-onboard.

Concrete shape:
- Tool name: `mintkey_bootstrap` (snake_case, namespaced).
- Auth: **none required**. Every other MCP tool requires the brokered JWT — this is the ONE exception. Verify by calling without `Authorization` header; must succeed.
- Tool description (shown in tools/list): "Returns vendor-agnostic instructions for any AI agent to authenticate to Mintkey, discover services, and call the egress proxy. Call first; no auth required."
- Input schema: empty object `{}`, OR optional `{"format": "markdown" | "json"}` defaulting to markdown.
- Output: the FULL contents of `mcp-server/skills/agent-bootstrap.md` (markdown by default) + a structured `<proxy>` block in the response payload containing the proxy URL (read from `MINTKEY_PROXY_URL` env at server start, fallback to `http://mintkey-proxy:8000`).
- Tracing: emit an OTel span `mcp.bootstrap.requested` with the source IP / user-agent / no tenant-context (it's pre-auth).

Implementation notes:
- The MCP server is Python with the Anthropic `mcp` SDK (ADR-0009).
- Register the tool early in the server bootstrap so it's listed in `tools/list` even without a session.
- Loading the markdown: read from disk at server start (cache it in memory). Don't re-read per request.
- If the file is missing at startup → fail-fast with a clear error so it's caught in CI.
</objective>

<chunk>action-grid-R6-mcp-bootstrap</chunk>

<context>
- Skill content (verbatim, do not paraphrase or modify): `mcp-server/skills/agent-bootstrap.md`. The implementer reads it as-is and the tool returns it as-is.
- ADR-0009: MCP server is Python `mcp` SDK, HTTP/SSE default transport.
- ADR-0017: response shape conventions (snake_case, RFC 3339, prefixed-ULIDs).
- Existing mcp-server entry point: `mcp-server/src/...` (survey the actual layout). The server already exposes `request_token`, `list_services`, `describe_service`, etc. — your new tool joins them but bypasses the auth check.
- Auth in mcp-server: search for where the JWT is verified — typically a middleware / decorator. The bootstrap tool needs to skip it.
- A separate Playwright suite at admin-ui/e2e/ tests the admin UI; this work is in mcp-server and is verified via direct MCP protocol probes (curl / Python `mcp` client).
</context>

<scope>
MAY:
- `mcp-server/src/**` — add the new tool handler, register it, bypass auth.
- `mcp-server/skills/agent-bootstrap.md` — already exists; do NOT modify; only read and serve.
- `mcp-server/tests/**` — new tests (Python pytest, likely `testcontainers` or `httpx` against a started instance).
- `team/remediation/ADMIN_UI_ACTION_MATRIX.md` — Cross-cutting row "MCP bootstrap" added.

Do NOT:
- Modify the skill markdown content (the skill is canonical).
- Change auth for other tools.
- Touch admin-ui/, admin-api/, services/ (other than mcp-server), docs/architecture/ (other than mcp-server's own README if it exists).
</scope>

<acceptance_criteria>
1. Survey: paste the current MCP tool inventory (e.g. `grep -rn "@tool\|register_tool\|FastMCP" mcp-server/src/`) so the reviewer sees the integration point.
2. The skill markdown file exists at `mcp-server/skills/agent-bootstrap.md` and is ≥150 lines (sanity-check it's not been truncated).
3. Failing test first: a Python test (pytest) that connects to mcp-server WITHOUT auth, calls `tools/list`, asserts `mintkey_bootstrap` is present. Run it BEFORE the implementation; it fails (tool not registered). Paste failure.
4. Implementation: tool registered, auth bypassed for this one tool, response payload structure:
   ```json
   {
     "skill_markdown": "<full content of agent-bootstrap.md>",
     "proxy_url": "http://mintkey-proxy:8000",
     "mcp_url": "http://mintkey-mcp:8001",
     "version": "1.0"
   }
   ```
   (Adjust shape per the `mcp` SDK conventions — content-type / structured-content / etc. — but the markdown must be retrievable.)
5. After-fix test: same test passes. Add a second test: call the tool unauthenticated, assert the markdown contains the verbatim `<authentication>` opening sentence and the `<proxy_usage>` block. Add a third: call WITHOUT any token; the `mintkey_bootstrap` tool returns 200, but `list_services` (any other tool) returns 401 — proving auth bypass is scoped to bootstrap only.
6. mcp-server container rebuilds + healthy: `docker compose up -d --no-deps --build mcp-server && sleep 15 && docker compose ps | grep mcp-server`.
7. The proxy_url comes from `MINTKEY_PROXY_URL` env if set; otherwise defaults to `http://mintkey-proxy:8000`. Verify with `docker compose exec mcp-server env | grep MINTKEY_PROXY_URL`.
8. Single commit (`feat(mcp-server): unauthenticated mintkey_bootstrap tool serving agent-bootstrap skill (R6 of action-grid remediation)`), no `--no-verify`.
9. Matrix updated: Cross-cutting row "MCP unauthenticated bootstrap" → ✅ with commit hash.
10. Don't introduce new admin-ui Playwright tests for this chunk (it's mcp-server scope); the Python pytest suite is sufficient.
</acceptance_criteria>

<discipline>
- Read the skill markdown verbatim; serve it verbatim. No interpretation, no template-rendering at request time. Cached in memory.
- Auth bypass is SCOPED to this one tool. All other tools continue to require the JWT. Add a comment in the code explaining why the bypass exists.
- The `<proxy>` block / `proxy_url` field uses the env var; provide a sensible default.
- Tests run via pytest; use existing test conventions (testcontainers if mcp-server already uses them; otherwise `httpx` + a started instance).
- Never `--no-verify`. No tautological tests (don't just assert "tool returned 200"; assert the response contains specific known text from the markdown).
</discipline>

<workflow>
1. Read mcp-server's layout (`find mcp-server/ -name '*.py' -not -path '*/test*' | head -30`); find the tool-registration / FastMCP entry point.
2. Read `mcp-server/skills/agent-bootstrap.md` (your output payload).
3. Find the auth middleware; understand how to bypass it for one tool.
4. Write the failing pytest; run it.
5. Implement the tool + auth bypass.
6. Rebuild mcp-server; re-run tests; verify pass.
7. Direct MCP protocol probe: `curl -X POST $MCP_URL/tools/call -d '{"tool":"mintkey_bootstrap","arguments":{}}'` (no Authorization header) → returns the skill markdown.
8. Also probe `tools/list` without auth → `mintkey_bootstrap` is listed.
9. Probe `request_token` without auth → 401 (auth bypass is scoped).
10. Update matrix; commit.
</workflow>

<output_format>
CHANGED: <file — purpose>
SURVEY: <mcp-server tool-registration entry point, auth middleware location>
RAN: <failing pytest, rebuild, passing pytest, curl probes (unauth bootstrap → 200, unauth list_services → 401), git log/show>
RESPONSE SHAPE: <paste the actual JSON the bootstrap tool returns; trim the markdown to first 5 lines + ... + last 2 lines>
MATRIX DELTA: <cross-cutting row added/updated>
STATUS: DONE | BLOCKED | ESCALATE
</output_format>

<constraints>≤ 2600 words. Single commit. Sonnet. No --no-verify.</constraints>
```

---

### R7 — MCP auth-chain validation + admin-api fingerprint UUID bug

**Scope exception**: this chunk MAY modify `admin-api/src/admin_api/**` and `admin-api/tests/**` (or repo-root `tests/integration/admin_api/**`). Other §3 hard rules still apply (TDD, conventional commit, no `--no-verify`).

```xml
<role>You are a Sonnet IMPLEMENTER in `$PROJECT_ROOT` (Mintkey repo root). Scope spans admin-api source + optional mcp-server tests (this chunk is authorized to modify admin-api/ source — exception to §3 of this prompt). Stack live; mcp-server at the port docker-compose.yml says (8082 was reported; verify), admin-api at :8080. REVIEWER will validate the chain end-to-end with direct curl + MCP probes.</role>

<objective>Fix the MCP agent-authentication chain. A user-reported smoke-test found: every X-API-Key presented to MCP gets a 401. The trace:

  MCP receives X-API-Key
  → MCP calls admin-api POST /v1/internal/validate-agent-key (or wherever — verify the actual route)
  → admin-api returns 500 with Postgres error: invalid input syntax for type uuid: ""
  → MCP interprets the 500 as "invalid" and returns 401 mintkey:auth_required.

Root cause: admin-api's fingerprint extraction producing an empty string, which gets bound as a UUID parameter to a Postgres query.

Two-part fix:

1. **Reproduce + diagnose + fix the admin-api side.**
   - Find the validate-agent-key handler in admin-api/src/admin_api/api/internal.py (or via grep).
   - Trace the fingerprint extraction. Find why it returns empty string. Candidates:
     * The extraction regex doesn't match the actual `mk_agent_…` key format.
     * The fingerprint computation returns the right value but the SQL binding is wrong (binding to a uuid column when it should be bytes/text, or vice versa).
     * A prior commit changed the prefix from `mk_agent_` to `mk_agentkey_` (or similar) without updating the regex.
   - Fix the smallest thing that resolves the symptom. Don't refactor the handler.

2. **Add an end-to-end auth-chain regression test** under tests/integration/admin_api/ or tests/acceptance/ that:
   - Provisions a synthetic agent (POST /v1/tenants/{tid}/agents) and captures the returned API key.
   - Calls validate-agent-key with that key → 200 + agent_id + tenant_id.
   - Calls mcp-server `tools/call request_token` with X-API-Key → 200 + brokered JWT.
   - Decodes the JWT (split, base64 the payload) → asserts sub=agent_id, tnt=tenant_id.
   - Calls mcp-server `tools/call list_services` with the JWT → 200.
   - Confirms admin-api logs since test-start have ZERO 500s.

The agent's reported keys (`mk_agent_17N...`, `mk_agent_0AF...`) follow `mk_agent_<base32>` shape. Verify what the actual minting code uses.</objective>

<chunk>action-grid-R7-mcp-auth-chain</chunk>

<context>
- Symptom from the agent's bisect: every X-API-Key → 401. Admin-api logs the 500 + UUID error.
- Scope exception: MAY modify admin-api/src/admin_api/** and tests; all other §3 hard rules still apply.
- ADR-0006 (token binding) + ADR-0017 (wire conventions).
- Likely fingerprint is SHA-256 of the key body (not the full prefixed string), stored as bytes or hex.
- mcp-server's call to admin-api uses internal-service auth; this chunk does not change that contract.
- A separate W0-W8 reviewer and a separate R1 implementer may be running in parallel; disjoint scopes.
</context>

<scope>
MAY modify:
- admin-api/src/admin_api/** (the fix — likely in api/internal.py or api/agents.py).
- admin-api/tests/** OR tests/integration/admin_api/** (whichever the project uses — survey).
- A new pytest at tests/acceptance/test_mcp_auth_chain.py (or similar).
- team/remediation/ADMIN_UI_ACTION_MATRIX.md (cross-cutting row: "MCP agent-key validation chain").

Do NOT modify:
- admin-api/requirements.txt, Dockerfile.
- admin-ui/** (not a UI bug).
- services/** other than reading mcp-server source/config.
- Liquibase changelogs.
- docs/architecture/** (unless a tiny Status corrigendum is unavoidable; minimal).
</scope>

<acceptance_criteria>
1. Reproduction: paste the curl + the admin-api log line containing `invalid input syntax for type uuid: ""`.
2. Diagnosis: cite the exact file:line of the buggy fingerprint extraction; quote the buggy code; explain why it produces empty string.
3. Failing test first: pytest that exercises validate-agent-key with a synthetic key → fails with the same Postgres error or a 500. Paste failure output.
4. Fix applied surgically: minimal diff resolves the symptom.
5. Test passes after fix.
6. End-to-end chain validation (all must succeed):
   a. POST /v1/internal/validate-agent-key with a real key → 200 + agent_id + tenant_id.
   b. mcp-server `tools/call request_token` with X-API-Key → 200 + JWT.
   c. Decode JWT payload; assert sub=agent_id, tnt=tenant_id.
   d. mcp-server `tools/call list_services` with the JWT → 200.
   e. `docker logs --since 2m mintkey-admin-api-1 | grep -c "500\|invalid input"` → 0.
7. Container rebuilds + healthy: docker compose up admin-api healthy.
8. No regressions: admin-api integration tests + admin-ui Playwright suite both still green.
9. Matrix updated: cross-cutting row "MCP agent-key validation chain" → ✅ with commit hash.
10. Single commit (`fix(admin-api): agent-key fingerprint extraction (was passing empty string as UUID — R7 of action-grid remediation)`), conventional, no --no-verify.
</acceptance_criteria>

<discipline>
- ONE bug fix + ONE regression pytest. Don't refactor. Don't change the key format / fingerprint algorithm beyond what fixes the bug.
- TDD failing-then-passing transition in commit body.
- Regression pytest is the durable artefact: minimal, no flaky timing, no hardcoded UUIDs (synthesize the test agent).
- Never --no-verify. Never edit Liquibase changelogs.
</discipline>

<workflow>
1. Read AGENTS.md, CLAUDE.md, ADR-0006.
2. Find the handler: grep validate.agent.key in admin-api/src/.
3. Read the fingerprint extraction code.
4. Curl-reproduce; capture 500 + log line.
5. Write the failing pytest.
6. Diagnose; apply minimum fix.
7. Re-run pytest; passing.
8. Rebuild admin-api; chain-validate end-to-end through MCP.
9. Run existing admin-api integration tests + admin-ui Playwright suite to confirm no regression.
10. Update matrix; commit.
</workflow>

<output_format>
CHANGED: <file — purpose>
REPRO: <curl + admin-api log line>
DIAGNOSIS: <file:line + buggy code excerpt + why it produced empty string>
RAN: <failing pytest, fix, passing pytest, end-to-end curls, container rebuild, admin-ui regression check, git log/show>
MATRIX DELTA: <which cross-cutting cell changed>
STATUS: DONE | BLOCKED | ESCALATE
</output_format>

<constraints>≤ 2800 words. Single commit. Sonnet. No --no-verify. Don't broaden scope beyond the fingerprint fix + the end-to-end pytest.</constraints>
```

---

### R8 — admin-api `get_agent` wire-ID/UUID mismatch (500s)

**Scope exception** (same as R7): MAY modify `admin-api/src/admin_api/**` and a regression test under `tests/`. All other §3 hard rules still apply.

```xml
<role>You are a Sonnet IMPLEMENTER in `$PROJECT_ROOT` (Mintkey repo root). Scope: admin-api source + one regression test (scope exception like R7). Stack live; admin-api at :8080. REVIEWER will verify via direct curl probes.</role>

<objective>Fix the `get_agent` (and likely `get_permissions`) 500s in admin-api. Surfaced by R7's reviewer: 27 admin-api 500s in 5 minutes from `GET /v1/tenants/<tid>/agents/agent_<32hex>` and the per-agent permissions endpoint. Root cause cited in the R7 review: a wire-ID / UUID mismatch at `admin-api/src/admin_api/api/agents.py:338` — the handler tries to bind the wire-prefixed ID (`agent_<32hex>` per ADR-0017) as a bare UUID parameter.

Per ADR-0017, wire IDs are prefixed-ULIDs (e.g. `agent_<26-char-Crockford-base32>` or possibly the 32-hex-after-prefix variant the R7 reviewer observed). The database column is `UUID`. The handler must accept either the wire form (prefixed) OR the canonical UUID form, decode the wire form to a UUID, then query.

Two-part fix:

1. **Diagnose + fix** the get_agent handler (and the per-permissions handler if it shares the same code path / helper). Use the existing wire-ID-to-UUID helper if one exists in admin-api (likely something like `wire_id_to_uuid()`, `parse_agent_id()`, or `decode_prefixed_id()`); otherwise add a small one. Apply the same fix to any sibling handlers exercising the same bug (cross-check with `grep -rn "agent_<.*>::uuid\|::uuid.*agent_id" admin-api/src/`).

2. **Add a regression test** at `tests/acceptance/test_agent_wire_id_handling.py` (or extend an existing acceptance test — survey first). The test:
   - Provisions a synthetic agent via `POST /v1/tenants/{tid}/agents`; captures the returned `agent_id` (likely in wire form `agent_<...>`).
   - `GET /v1/tenants/{tid}/agents/{agent_id-wire-form}` → 200.
   - `GET /v1/tenants/{tid}/agents/{agent_id-UUID-form}` → 200 (if the contract supports both forms — verify; if it's strictly wire-form, just the first GET is enough).
   - `GET /v1/tenants/{tid}/agents/{agent_id-wire-form}/permissions` → 200 (or 200 with empty list if no grants).
   - Asserts admin-api logs since test-start have ZERO 500s.

Don't refactor admin-api beyond what fixes the bug. The same scope-exception as R7 applies.</objective>

<chunk>action-grid-R8-get-agent-wire-id</chunk>

<context>
- Symptom (R7 reviewer-reported): 27 admin-api 500s in 5 min on `GET /v1/tenants/<tid>/agents/agent_<32hex>` and the per-agent permissions endpoint. R1-redux's admin-ui CRUD traffic likely triggers them (it's fetching agents/permissions for the createApiKey dropdowns).
- Likely fix site: `admin-api/src/admin_api/api/agents.py:338`. Survey the actual line to confirm.
- ADR-0017: wire IDs are prefixed-ULIDs. Canonical wire form: `agent_<26-char-Crockford-base32>`. The R7 reviewer cited `agent_<32hex>` too — verify which forms are valid.
- Existing helpers: grep `admin-api/src/admin_api/` for `wire_id_to_uuid`, `parse_id`, `decode_id`, or similar. Reuse if exists.
- Scope-exception: this chunk MAY modify `admin-api/src/admin_api/**` and `tests/`. All other §3 hard rules still apply.
- Concurrent work: R1-redux still running in admin-ui/ — fully disjoint scope. A separate R6 reviewer just landed PASS on `d8b55973`; no other admin-api work in flight.
- The pre-existing untracked Liquibase changelog `admin-api/db/changelog/011-schema-fixes.yaml` is unrelated and should NOT be touched.
</context>

<scope>
MAY modify:
- `admin-api/src/admin_api/api/agents.py` (the handler — and any sibling handler with the same bug).
- `admin-api/src/admin_api/db/deps.py` or `admin-api/src/admin_api/util/ids.py` (or wherever the helper lives — if you need to add/extend a wire-ID-to-UUID helper).
- `tests/acceptance/test_agent_wire_id_handling.py` (new) OR an extension to `tests/acceptance/test_mcp_auth_chain.py` (only if you can do it cleanly without bloating the existing test).
- `team/remediation/ADMIN_UI_ACTION_MATRIX.md` — cross-cutting row "admin-api wire-ID handling" added.

Do NOT modify:
- `admin-api/requirements.txt`, `admin-api/Dockerfile`.
- Liquibase changelogs.
- `admin-ui/**` (R1-redux's working set).
- `services/**`, `docs/architecture/**`.
- Any pre-existing untracked file (other than the matrix).
</scope>

<acceptance_criteria>
All must hold; reviewer will re-run each.

1. **Reproduction**: paste the curl that reproduces the 500. Quote the admin-api log line(s) (Postgres error message + the agents.py file:line).
2. **Diagnosis**: cite the exact file:line of the buggy code; quote 4-8 lines of context; explain in 1-2 sentences why it produces the UUID error.
3. **Failing test first**: pytest that exercises the GET path with a wire-form `agent_id` → fails BEFORE the fix with a 500 / the same Postgres error. Paste failure.
4. **Fix applied surgically**: `git diff HEAD -- admin-api/src/` is small (≤ ~30 lines changed). No refactor. Helper added or extended cleanly.
5. **Test passes after fix.**
6. **End-to-end verification** (paste output for each):
   a. `POST /v1/tenants/<tid>/agents` with a sane body → 200 + agent_id (capture).
   b. `GET /v1/tenants/<tid>/agents/<agent_id-wire-form>` → 200 + full agent JSON.
   c. `GET /v1/tenants/<tid>/agents/<agent_id-wire-form>/permissions` → 200 (or 200 with empty list).
   d. `docker logs --since 2m mintkey-admin-api-1 | grep -cE "500|invalid input syntax for type uuid"` → 0.
7. **Container rebuilds + healthy**: `docker compose up -d --no-deps --build admin-api && sleep 12 && docker compose ps | grep admin-api` → `(healthy)`.
8. **No regressions**:
   - Existing admin-api integration tests pass: `python -m pytest tests/integration/admin_api -q` → green.
   - R7's regression tests still pass: `MINTKEY_INTEGRATION_TEST=true python -m pytest tests/acceptance/test_mcp_auth_chain.py -v` → 3 passed.
   - The W0-W8 admin-ui Playwright suite NOT regressed (same pass/fail count as before — modulo the 5 known pre-existing failures the orchestrator knows about; R1-redux's redux work is in flight, so don't worry about admin-ui state beyond a `docker compose ps | grep admin-ui` health check).
9. **Matrix updated**: cross-cutting row "admin-api wire-ID handling" → ✅ with commit hash + comment "Fixed get_agent (and siblings) to decode wire-prefixed IDs before UUID binding (R8)". Phase log entry.
10. **Single commit**: `fix(admin-api): get_agent decodes wire-prefixed IDs before UUID binding (R8 of action-grid remediation)`, conventional, no `--no-verify`.
</acceptance_criteria>

<discipline>
- ONE bug fix (across however many handlers share the same code path) + ONE regression pytest. Don't refactor agents.py broadly.
- TDD failing-then-passing transition in the commit body verbatim.
- The regression pytest is the durable artefact: minimal, no flaky timing, no hardcoded UUIDs (synthesize the test agent via the POST).
- Never `--no-verify`. Never edit Liquibase changelogs.
- If diagnosis reveals the bug is in admin-ui (not admin-api), STOP and ESCALATE — that would mean the wire-format issue is on the request-shaping side, which is R1-redux's territory.
</discipline>

<workflow>
1. Read AGENTS.md, CLAUDE.md, ADR-0017 (wire conventions).
2. Find the buggy handler: `grep -rn "def get_agent\|agents/{agent_id}" admin-api/src/`. Read agents.py:338 area. Identify the wire-ID-to-UUID step (or lack thereof).
3. Find / inspect existing helpers: `grep -rn "wire_id\|prefixed_id\|decode_id\|::uuid" admin-api/src/admin_api/ | head -20`.
4. Curl-reproduce: bootstrap session, create an agent (capture wire-form ID), `GET /v1/tenants/<tid>/agents/<agent_wire>` → observe 500.
5. Write the failing pytest.
6. Apply the surgical fix (decode wire form before binding).
7. Re-run pytest; passing.
8. Rebuild admin-api; chain-validate (steps 6a-d).
9. Run existing admin-api integration tests + R7 regression tests.
10. Update matrix; commit.
</workflow>

<output_format>
CHANGED: <file — purpose, one line each>
REPRO: <curl command + admin-api log line(s)>
DIAGNOSIS: <file:line + buggy code excerpt + why>
RAN: <failing pytest, fix, passing pytest, end-to-end curls (6a-d), container rebuild, admin-api integration tests, R7 regression tests, git log/show>
MATRIX DELTA: <which cross-cutting cell changed>
STATUS: DONE | BLOCKED <specific> | ESCALATE <specific>
</output_format>

<constraints>≤ 2400 words. Single commit. Sonnet. No `--no-verify`. Don't broaden scope.</constraints>
```

---

## §7 — REVIEWER template (every chunk uses this; fill the AC slot from the chunk's brief)

```xml
<role>You are a fresh, independent REVIEWER subagent in `$PROJECT_ROOT` (Mintkey repo root). You did NOT do this work. Re-run; drive the browser (or MCP protocol for R6) yourself. Deliver PASS / FAIL / ESCALATE with evidence.</role>

<objective>Verify the most-recent commit (HEAD) for chunk {{R<n> title}} meets its acceptance criteria. The implementer claimed: {{2-4 lines summary of their report}}. Don't trust it — re-run.</objective>

<chunk>review-{{R<n>-id}}</chunk>

<context>
Stack runs via docker compose. Bootstrap operator admin@mintkey.internal; password at data/bootstrap-secrets/admin_password. Read AGENTS.md, CLAUDE.md, the chunk's AC block from team/remediation/ADMIN_UI_REMEDIATION_PROMPT.md §6, and the relevant ADRs.

Pre-existing items (DO NOT fail on): untracked team/remediation/*.md files, the .serena/project.yml mod, the 04be7008 OpenAPI touch (intentional per ADR-0014/0015), the bootstrap tenant UUID 9593e3ba-….
</context>

<acceptance_criteria>
{{Paste the chunk's <acceptance_criteria> block verbatim from §6. Re-run each as a reviewer command; paste actual output; PASS/FAIL per criterion.}}

Plus universal reviewer ACs:
A. Single commit, conventional message, no --no-verify / --no-gpg-sign.
B. No anti-patterns: `grep -rn "test.skip\|test.fixme\|xit\|xdescribe\|expect(true).toBe(true)" admin-ui/e2e/tests/ admin-ui/e2e/fixtures/` — empty or only justified fixme with chunk-id TODO comment.
C. Browser-drive your own positive-narrow case (different inputs than the implementer's test) — temp spec, screenshot, READ, describe, delete the temp spec.
D. Matrix correctly updated; cell hash matches HEAD.
E. No regressions to prior chunks: `pnpm test:e2e --project chromium 2>&1 | tail -25` green (modulo any pre-existing failures the chunk explicitly inherited or fixed).
</acceptance_criteria>

<discipline>
Re-run. Drive the browser. READ screenshots; describe in your own words. Distinguish regression from pre-existing. Cite file:line for code claims. Tautology-check filter/data tests — URL-only assertions = FAIL.
</discipline>

<workflow>
1. git log --oneline -5; git status. Read the brief's AC.
2. Run each AC; paste output; classify PASS/FAIL.
3. Drive your own positive-narrow case; READ screenshot; describe.
4. Anti-pattern + regression sweep.
5. Verdict.
</workflow>

<output_format>
CHECKS: <each AC + command + output + PASS/FAIL>
NAVIGATION: <files inspected; key findings>
SCREENSHOTS: <PNGs; what you saw>
ANTI-PATTERNS: <none | list>
PRE-EXISTING / OUT-OF-SCOPE NOTES: <only if needed>
VERDICT: PASS — <one-line> | FAIL — <numbered specifics> | ESCALATE
</output_format>

<constraints>≤ 2000 words. No permanent edits. Delete temp spec.</constraints>
```

---

## §8 — Done

Orchestration is complete when:

- All chunks R1–R6 have a REVIEWER `PASS` verdict (R4 is "documented why not implemented" — counts as PASS).
- `ADMIN_UI_ACTION_MATRIX.md` has zero ⬜, zero ❌; only ✅, 🚫 (justified, escalated), and n/a.
- `pnpm test:e2e --project chromium` is green; pre-existing 5 failures from Phase-1a are resolved.
- `mintkey_bootstrap` MCP tool is callable unauthenticated and returns the skill markdown; `request_token` etc. still require auth.
- The matrix's Phase log records each chunk's commit hash + date.

Report closing summary to the user with the chunk hashes + the matrix state.
