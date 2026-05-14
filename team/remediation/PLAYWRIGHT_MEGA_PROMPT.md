# Playwright Extension — Mega Prompt (solo Sonnet)

You are a single Sonnet implementer working in `$PROJECT_ROOT/`. Your job: extend the Mintkey admin-UI Playwright test suite per [`PLAYWRIGHT_EXTENSION_PLAN.md`](PLAYWRIGHT_EXTENSION_PLAN.md). Work through chunks W0 → W8 in order. Each chunk is one git commit with a TDD failing→passing transition captured in the commit body. The orchestrator pattern is *not* in use here — you are running solo, so you also self-review each chunk before moving on.

---

## 1 — Read before you start

In this exact order; do not skim:

1. [`PLAYWRIGHT_EXTENSION_PLAN.md`](PLAYWRIGHT_EXTENSION_PLAN.md) — the canonical plan; every chunk in §5 is your contract.
2. `AGENTS.md` and `CLAUDE.md` at the repo root — operating guardrails for any agent in this codebase.
3. `docs/architecture/01-architecture/adr/0019-admin-ui-bff-and-write-auth.md` — the BFF / write-auth contract you must respect (especially for W6).
4. `admin-ui/playwright.config.ts` (the soon-retiring config) and `admin-ui/e2e/playwright.config.ts` (the canonical config to keep).
5. All 5 specs in `admin-ui/tests/e2e/*.spec.ts` (the migration source).
6. All 12 specs in `admin-ui/e2e/tests/*.spec.ts` (the migration target; some may be stubs — your W0 survey decides).
7. All 11 Page Object Models in `admin-ui/e2e/pages/*.ts` (the conventions you extend; do not write a new POM from scratch when extending an existing one).
8. `admin-ui/e2e/fixtures/test-data.ts` and the existing `global-setup.ts` / `global-teardown.ts`.

---

## 2 — Hard rules (non-negotiable)

- **Never `--no-verify`** on commits; never `--no-gpg-sign` flags. If a pre-commit hook fails, fix the cause.
- **No `test.skip` / `test.fixme` / `xit` / `xdescribe` / `expect(true).toBe(true)`.** If you can't make a test pass cleanly, fix the underlying issue or STOP and write an ESCALATE note (see §7). One exception: a deliberate `test.fixme` with an inline `// TODO(W4): pending feature X — feature gate flag …` comment IS allowed, but only for genuinely-not-yet-shipped UI features called out in the PLAN (e.g. PlatformAdmin toggle UX before it lands).
- **No hardcoded passwords.** Always `process.env.MINTKEY_ADMIN_PASSWORD` or the testcontainer suite's `PLAYWRIGHT_PASS`.
- **No hardcoded record UUIDs** beyond the known-bootstrap-tenant `9593e3ba-...`. CRUD specs create their own records and use the returned ID.
- **No edits to** `admin-api/`, `services/`, `docs/architecture/`, `.kiro/`, `docker-compose.yml`, Liquibase changelogs, the seed-job's seed data. If your chunk needs them, ESCALATE.
- **Single commit per chunk**, conventional message starting with `test(admin-ui):` or — only if your chunk includes a small bug fix discovered while writing tests — `fix(admin-ui):`. No squashing across chunks; no commits that mix two chunks.
- **TDD discipline**: write the failing test first, run it, capture the failure output in the commit body. Only then implement the supporting code (POM additions, fixture updates, etc.). Commits without that transition in their body get rejected by self-review.
- **Validate via tools**: every claim ("the dashboard shows the diagram", "the filter narrows the list") must be backed by a real browser run + a screenshot you've read with the Read tool. Don't claim what you haven't verified.
- **No tautological assertions**: on any filter / data test, asserting only "URL contains `?q=foo`" is rejected. Add a positive narrow assertion (`expect(rowCount).toBeLessThan(baseline)`, `expect(body).toContain(knownMatch)`).
- **Page Objects** for any new selectors. If you find yourself writing `page.locator('input[name="slug"]')` twice in two specs, that goes in `admin-ui/e2e/pages/<resource>.ts`.
- **The console-error fixture is mandatory** after W0. Every test inherits it via the `test` fixture override. No spec defines its own `test` from `@playwright/test` directly after W0 — they import from `admin-ui/e2e/fixtures/test.ts` (or similar) instead.

---

## 3 — The loop, per chunk

Repeat for each W0 … W8:

1. **Read** the chunk's row in `PLAYWRIGHT_EXTENSION_PLAN.md` §5; that's your DoD.
2. **Survey** what already exists in `admin-ui/e2e/tests/` for the resources / scenarios this chunk touches. Extend rather than rewrite. If a spec is a stub (a `test('...', () => { /* TODO */ })` shape) say so in your commit body and replace it cleanly.
3. **Write failing tests first.** Run `pnpm test:e2e` (after W0) or the current path (before W0); capture the failure output (paste it into your commit body or chunk notes).
4. **Implement** the supporting code (POM updates, fixtures, helpers). Re-run until your new tests are green.
5. **Run the FULL suite**: `pnpm test:e2e` — every previously-green test must still be green. No regressions.
6. **Read screenshots**. For each new spec, open at least one screenshot with the Read tool and write a 1-2 sentence description in your commit body of what you saw. "Looks fine" is not a description.
7. **Commit.** Conventional message; body documents (a) the chunk reference (`Closes W{N} per PLAYWRIGHT_EXTENSION_PLAN.md §5`), (b) the failing→passing transition, (c) the screenshots you read.
8. **Self-review** (since you're solo): re-read your diff with `git show HEAD`; verify no anti-pattern slipped through (no `test.skip`, no hardcoded password, no tautological assertion, no `--no-verify`). If you find one, amend in a NEW commit (do not `--amend`).
9. **Move to next chunk.**

---

## 4 — Phase reference

The chunk descriptions are in `PLAYWRIGHT_EXTENSION_PLAN.md` §5; this section adds *implementation notes* per chunk. Treat the plan's DoD as the contract; treat the notes below as hints.

### W0 — Survey + consolidate + console-error fixture

Sub-steps in order:

1. **Survey.** Open every `admin-ui/e2e/tests/*.spec.ts`. For each, write one row in a new file `admin-ui/e2e/COVERAGE.md`: spec filename, what it asserts, status (`real` / `stub` / `broken`). Same for the live-container suite.
2. **Migrate the 5 live-container specs into the canonical tree.** Target paths:
   - `admin-ui/tests/e2e/smoke.spec.ts` → `admin-ui/e2e/tests/12-smoke.spec.ts` (or merge into the existing login / dashboard specs if the testcontainer suite has stubs).
   - `intros-and-dashboard.spec.ts` → `admin-ui/e2e/tests/13-intros-and-dashboard.spec.ts`.
   - `search-and-filters.spec.ts` → `admin-ui/e2e/tests/14-search-and-filters.spec.ts`.
   - `tenants-platform-admin.spec.ts` → fold into `08-tenants.spec.ts` if appropriate, else `15-tenants-platform-admin.spec.ts`.
   - `show-pages.spec.ts` → `admin-ui/e2e/tests/16-show-pages.spec.ts`.
   Replace raw selectors in the migrated specs with Page Object calls. Use the existing POMs (`pages/services.ts` etc.) wherever they already expose what you need.
3. **Console-error fixture.** Create `admin-ui/e2e/fixtures/test.ts` exporting a `test` (extends `@playwright/test`) with a beforeEach that hooks `page.on('pageerror')`, `page.on('console')` (filter type === 'error'), and `page.on('requestfailed')`; collect to an array; assert empty in an `afterEach`. Add one **synthetic** test (`tests/00-fixture-self-test.spec.ts`) that intentionally throws — verify the fixture fails the test; then **delete or `.fixme`** the synthetic test (an inline `test.fixme` with a comment is OK here — this is one of the explicit exceptions). After this, every spec imports `test` from `../fixtures/test` not `@playwright/test`.
4. **Retire the old config + dir.** Remove `admin-ui/playwright.config.ts`. Remove `admin-ui/tests/e2e/`. Verify `pnpm test:e2e` still runs the testcontainer-suite config and is green.
5. **Verify cross-browser readiness (not full run yet)**: `pnpm test:e2e --project chromium` green. (Firefox/Webkit get the full enable in W8.)

### W1, W2 — CRUD happy paths

- One spec per resource. Each spec covers: **create → list → show → edit → list → delete → list**.
- Use `nanoid` (or a tiny in-spec UUID) for slugs/names so concurrent runs don't collide. e.g. `e2e-svc-${nanoid(8)}`.
- Extend `admin-ui/e2e/pages/<resource>.ts` with `create()`, `editField()`, `deleteAndConfirm()` methods. Spec files become 30-60 line orchestrations.
- After delete, the global-teardown's cleanup file should record any leftover record IDs in case the spec fails mid-way.
- W1 = Services + Credentials + Agents. W2 = Permission Grants + Service API Keys + Tenants. Tenants CRUD requires the bootstrap PlatformAdmin session (already established).

### W3 — Form validation rendering

- Submit each of: empty form, single missing-required-field form, format-violating form (e.g. invalid email), and a duplicate-slug form. Assert: each field-level error renders (find by accessible name); no JS-error box (the console-error fixture catches that); the form is still editable after the error.
- Cover at least 3 resources (Services + Agents + one with stricter validation).

### W4 — Multi-tenant scoping + PlatformAdmin

- Seed a second tenant + an operator scoped to it via admin-api HTTP calls in a new fixture file `admin-ui/e2e/fixtures/multi-tenant.ts` (NOT in `seed-job`; not in admin-api source). The new operator credentials live in `PLAYWRIGHT_TENANT_B_PASS` env (default a random string the fixture sets at setup time).
- Log in as tenant-B operator → assert list endpoints for resources scoped to tenant A return 0 / not-visible for cross-tenant items.
- Direct URL probe: `/admin/resources/services/records/<tenantA-svc-id>/show` → expect either a 4xx redirect or an empty / forbidden state. Not a JS error.
- PlatformAdmin toggle: if the UI exposes it (check `admin-ui/src/resources/tenants.ts` and search for "All Tenants" / "platform_admin_view"), cover the toggle behavior. If not, write a `test.fixme` with the comment `// TODO: pending platform-admin-toggle UX — see PLAN §4 P1`.

### W5 — Pagination + sorting + logout + session expiry

- Pagination: services list page 1 vs page 2 — assert different row sets, total count consistent, no row appears on both pages.
- Sorting: click column header → URL `?sortBy=name&direction=asc`; first row's value < second row's value lexicographically. Reverse for `direction=desc`.
- Logout: find the logout button (AdminJS exposes one in the header / user menu), click it; assert next request lands on `/admin/login`; subsequent navigations to `/admin/...` redirect to login.
- Session expiry: clear the `mintkey_session` cookie via `context.clearCookies()`; navigate to `/admin/resources/services`; assert redirect to login (no crash).

### W6 — AdminUiSignedRequest write-auth contract

- Listen with `page.on('request')` during a CRUD create. Filter to admin-api requests (`request.url().startsWith(ADMIN_API_URL)`). Find the one matching the action (POST / PUT / DELETE).
- Assert headers: `Cookie: mintkey_session=...` AND `Authorization: Bearer eyJ...` (or whatever header the BFF sets — check `admin-ui/src/lib/signed-request.ts`).
- Decode the JWT (`jose` already available, or just `JSON.parse(atob(token.split('.')[1]))` for the payload). Assert `sub`, `tnt` match the session's operator/tenant.
- Replay: capture the exact request; `await fetch(...)` it again from the test context within `jti`-TTL; assert admin-api returns 401 (`{ "error": "replay_denied" }` or similar — check ADR-0016.1 + the actual response shape).

### W7 — Accessibility

- Add `@axe-core/playwright` to `admin-ui/e2e/package.json` (the sub-package.json). One new dev dep is allowed here.
- One spec `23-accessibility.spec.ts`. For each canonical page (dashboard, 7 lists, 7 shows, 7 new-forms = 22 pages), `injectAxe(page)`; `await checkA11y(page, undefined, { detailedReport: true, axeOptions: { runOnly: ['wcag2a', 'wcag2aa'] } })`.
- Baseline: 0 serious / 0 critical. If existing violations exist (likely some — AdminJS stock components aren't perfect), capture them in `COVERAGE.md` and either: fix the few that are admin-ui-source-fixable, or scope down (e.g. test only the dashboard initially and grow the surface).

### W8 — Cross-browser + CI

- `pnpm test:e2e --project firefox` and `--project webkit` — run them; flaky failures get retries + a follow-up issue; structural failures get fixed.
- CI workflow file: check what exists under `.github/workflows/` or equivalent. Add `playwright.yml` that runs `pnpm install`, brings up `docker compose up -d`, waits for healthy, runs `pnpm test:e2e`. Uploads `playwright-report/` + `test-results/` as artifacts.
- Nightly cron variant: all three browsers. PR variant: chromium only (the fast path).

---

## 5 — Verification before declaring DONE (whole plan)

Run before claiming you've finished the plan:

- `cd admin-ui && pnpm test` → vitest green.
- `cd admin-ui && pnpm test:e2e` → all chromium specs green; ≥50 tests.
- `cd admin-ui && pnpm test:e2e --project firefox` and `--project webkit` → green.
- `docker compose ps` → every long-running mintkey container `(healthy)` (except `otel-collector` which has no healthcheck).
- `git log --oneline -10` shows one commit per chunk; conventional messages; no `--no-verify` flags.
- `admin-ui/e2e/COVERAGE.md` is up to date.
- `admin-ui/tests/e2e/` no longer exists; `admin-ui/playwright.config.ts` no longer exists.

---

## 6 — Resumability

You can pause and resume between chunks. To resume:

1. `git log --oneline -10` — identify last completed chunk by commit message (`test(admin-ui): W{N} …`).
2. Re-read PLAN §5 row for the next chunk.
3. Re-read this file's §2 hard rules.
4. Continue.

Mid-chunk pause: keep your scratch notes in `team/remediation/PLAYWRIGHT_NOTES.md` (gitignored or untracked — do NOT commit). Resume from your notes.

---

## 7 — Anti-patterns to avoid (from prior orchestration lessons)

- **Tautological tests**: asserting `expect(url).toContain('q=crm')` without a row-count check. Caught the `FilterElement → [object Object]` bug in commit `3992a429` only because a reviewer ran a positive narrow case. Don't repeat.
- **Show-page neglect**: covering List but not Show. React #31 (fixed in `71ed42d5`) shipped because Show pages were never browser-tested for any record.
- **Flat specs with raw selectors**: 5 specs encoding the same login flow 5 times → one inconsistency = drift. POMs solve this; use them.
- **`expect(true).toBe(true)` placeholders**: forbidden. Even one of these stops the suite from being trustworthy. A legitimate `expect(regex.test(body)).toBe(true)` is fine — that's an actual assertion on `.test()`'s return value.
- **Hardcoded test data that drifts** (a specific UUID that was true at write-time but isn't after the next seed run). Use fixtures + `firstRecordId(page, 'services')` patterns.
- **`docker compose down -v` between specs**: don't. Specs use the live stack and namespace their data.

---

## 8 — When to STOP and ESCALATE

- A chunk requires `admin-api/` source changes (not just calling admin-api over HTTP from a fixture). Stop; write up what's needed; surface it.
- A chunk's reasonable implementation hits an AdminJS 7.x limitation you can't work around (you've spent > 30 min on it).
- The plan turns out to be wrong about something material (e.g. consolidating onto `admin-ui/e2e/` causes more pain than expected — fork is actually load-bearing). Stop; write an alternative; surface it.
- 3 attempts at a chunk's TDD failing case in a row don't fail (the test is supposed to fail before the fix, but keeps passing) → either the bug doesn't exist, the test is wrong, or the assumed root cause is misidentified. Stop; investigate.

Each ESCALATE: write a one-page note in `team/remediation/PLAYWRIGHT_ESCALATIONS.md` (create if doesn't exist) with timestamp, chunk, what you tried, what's blocking.

---

## 9 — Start

Begin with W0. Concretely, your first 5 minutes:

1. Read PLAN.md in full.
2. Read AGENTS.md + CLAUDE.md.
3. `ls -la admin-ui/e2e/tests/ admin-ui/e2e/pages/` — verify what's there.
4. Open `admin-ui/e2e/tests/01-login.spec.ts` first; that's the simplest reference for the testcontainer-suite shape.
5. Open `admin-ui/tests/e2e/smoke.spec.ts`; that's the most-recently-disciplined live-container spec.
6. Open `admin-ui/e2e/pages/base.ts`; that's the POM base class.

Then start writing `admin-ui/e2e/COVERAGE.md` as your survey.
