# Playwright Extension — Plan

**Status:** Proposed, 2026-05-13.
**Owner:** orchestrator (you / future-you / next session).
**Companion docs:** [`PLAYWRIGHT_MEGA_PROMPT.md`](PLAYWRIGHT_MEGA_PROMPT.md) (solo Sonnet), [`PLAYWRIGHT_ORCHESTRATOR_PROMPT.md`](PLAYWRIGHT_ORCHESTRATOR_PROMPT.md) (multi-agent with XML-tagged briefs).

## 1 — Why this plan exists

Five months of admin-UI work shipped class-of-bug regressions twice — `record.errors is undefined` (commit `465e445` fixed it), then React invariant #31 on Show pages (commit `71ed42d5` fixed it) — because Playwright coverage was incomplete and some tests were tautological (asserted URL params but never row counts). The recovery chunks each added one focused spec; this plan extends them into a coherent, prevention-oriented browser-test suite that catches the *class* of failure before it ships.

## 2 — Current state

### Two parallel Playwright suites (the fork to fix)

| | `admin-ui/tests/e2e/` (live-container) | `admin-ui/e2e/` (testcontainer-style) |
|---|---|---|
| Specs | 5 files, 16 tests | 12 files (`00-diagnose`..`11-service-onboarding`) |
| Structure | Flat, no Page Objects | Page Objects in `pages/`, fixtures in `fixtures/test-data.ts` |
| Config | `admin-ui/playwright.config.ts` | `admin-ui/e2e/playwright.config.ts` |
| Parallelism | `fullyParallel: false, workers: 1` | `fullyParallel: true`, CI retries |
| Browsers | chromium only | chromium + firefox + webkit (declared as projects) |
| Reporter | `list` | `html` + `junit` + `list` |
| Global setup | none (per-test login) | login once → `state.json` storageState |
| pnpm script | none — invoked manually with `npx playwright test tests/e2e/...` | `pnpm test:e2e` runs this |

**Cost of the split:**
1. No single command runs everything. `pnpm test:e2e` runs only the testcontainer suite; the live-container suite needs hand-typed `npx`. CI cannot trivially run both.
2. Discipline drift. The recent live-container specs lacked the Page Object discipline the older suite has; that's how the tautological assertions ("URL contains `q=foo`" without row-count assertion) slipped past the FilterElement bug — there were no shared POM helpers and reviewers were checking spec-by-spec.

### What's confirmed-covered (live-container suite — read by Read tool)
- `smoke.spec.ts` — login → custom dashboard → all 7 resource lists render without JS errors → Tenants new-form fills/submits without TypeError.
- `intros-and-dashboard.spec.ts` — SVG diagram + 6 onboarding steps + Quick-start render; each resource list shows its verbatim intro paragraph.
- `search-and-filters.spec.ts` — 5 positive narrow scenarios (services `q=crm` → 1 row containing `demo-crm`; services `q=%` → 0; tenants `q=t_default`; agents `q=smoke` < baseline; audit `event_type`).
- `tenants-platform-admin.spec.ts` — PlatformAdmin sees Tenants list with ≥1 row (`t_default`).
- `show-pages.spec.ts` — 7 tests, one per resource: Show page has no JS-error needles; JSON columns render readable text.

### What may already be covered (testcontainer suite — must be surveyed in Phase 0)
By filename: `01-login`, `02-service-crud`, `03-credential`, `04-agent`, `05-permissions`, `06-api-keys`, `07-audit`, `08-tenants`, `09-settings`, `10-security`, `11-service-onboarding`, `00-diagnose`. Page Objects exist for all 7 resources + dashboard + login + settings + a `base.ts`. **Phase 0 of W0 MUST read each spec and mark in the coverage matrix what is real coverage vs. stub vs. broken** — we do not duplicate what works; we do not assume what doesn't.

## 3 — Strategic decision

**Consolidate on `admin-ui/e2e/` as the single canonical Playwright tree** with Page Object discipline, fixtures, and multi-browser projects. Migrate the 5 recent live-container specs into `admin-ui/e2e/tests/` with POMs. Retire `admin-ui/tests/e2e/` after the migration. One `pnpm test:e2e` script runs the full suite.

**Keep the live-container execution model** (real `docker compose` stack, real seed data — 126 services, 480 agents) rather than the testcontainer pattern (start/teardown an isolated stack per run). Reasons: matches production deployment shape; reuses the existing seed-job; faster on a single project than spinning up fresh stacks; the testcontainer config's global-setup is compatible (it just logs in against whatever `BASE_URL` points to).

Trade-off accepted: the suite must keep tolerating real seed data with hundreds of records. Tests use *narrowing* assertions (count < baseline, specific row exists), not exact counts, to be resilient to seed changes.

## 4 — Coverage matrix (priority-ranked gaps)

P0 = required before any other coverage work. P1 = core extension. P2 = quality gaps. P3 = polish / nice-to-have.

| Priority | Gap | Why it matters | Lives in |
|---|---|---|---|
| 🔴 **P0** | **Console-error + network-error global fixture** | Both bugs we shipped were silent in `pnpm test`; only visible by reading the rendered page. A fixture that listens to `page.on('pageerror')`, `console.error`, `requestfailed` and `response.status>=500` and fails the test that triggered it would have caught both at write-time. Cross-cutting. | new `admin-ui/e2e/fixtures/console-errors.ts` |
| 🔴 **P0** | **Suite reconciliation + Page Object enrichment** | The two-suite fork is the structural defect. Must fix first. | `admin-ui/e2e/` (migration target) |
| 🟠 **P1** | **CRUD happy paths per resource** | Create / edit / delete a Service, Credential, Agent, Permission Grant, Service API Key, Tenant. Round-trip → list shows new row → show page renders → edit page populates → delete removes → list updates. | new specs `tests/12..17-{resource}-crud.spec.ts` |
| 🟠 **P1** | **Form validation rendering** | We've twice shipped UI that broke when the API returned 422 / field errors. A spec deliberately submits invalid forms, asserts the field-level error renders, no JS-error box. | new spec `tests/18-form-validation.spec.ts` |
| 🟠 **P1** | **PlatformAdmin UX (toggle / All-Tenants pin)** | Currently the BFF forwards `X-Platform-Admin: true` unconditionally for PlatformAdmin sessions. ADR-0016.3 envisions a "pin to tenant" / "All Tenants" toggle. When implemented, e2e coverage. (Gated on feature.) | future spec |
| 🟡 **P2** | **Multi-tenant scoping (RLS via UI)** | Operator pinned to tenant A cannot see tenant B's data through list, show, or URL-probe. Requires a seeded second-tenant operator (fixture). | new spec `tests/19-tenant-isolation.spec.ts` |
| 🟡 **P2** | **AdminUiSignedRequest write-auth contract** | ADR-0019 says state-changing AdminJS calls must carry cookie AND Ed25519 JWT (must agree; replay rejected). No e2e currently asserts the JWT is in the request and admin-api rejects on mismatch. | new spec `tests/20-bff-write-auth.spec.ts` |
| 🟡 **P2** | **Pagination + sorting** | 126 services, 480 agents — operator must page-navigate. No coverage. | new spec `tests/21-pagination-sorting.spec.ts` |
| 🟡 **P2** | **Logout + session expiry** | Logout button must invalidate the session and redirect to login. Expired-session calls must redirect to login, not crash. | new spec `tests/22-logout-session.spec.ts` |
| 🟢 **P3** | **Custom actions** (credential rotate / agent revoke / permission grant-revoke) | Per ADR-0013. Gated on the actions existing in the UI. | future spec |
| 🟢 **P3** | **Accessibility scan** (`@axe-core/playwright`) | Run on dashboard + each list + each show + new-form pages; assert 0 serious violations. Low cost; baseline a11y discipline. | new spec `tests/23-accessibility.spec.ts` |
| 🟢 **P3** | **Visual regression** (screenshot diffing) | Catch unintended visual changes on the dashboard + canonical list/show pages. Opt-in due to fragility around date stamps and seed data. | future spec / workflow |
| 🟢 **P3** | **Performance baselines** | Dashboard load < threshold; list paint < threshold. Catch perf regressions. | new spec `tests/24-performance.spec.ts` |
| 🟢 **P3** | **Cross-browser actually exercised** | Testcontainer config already declares chromium + firefox + webkit projects. CI must run all three on every PR (or at minimum nightly). | CI config + W8 verification |

## 5 — Chunk breakdown

Each chunk fits one Sonnet IMPLEMENTER subagent run (≤ ~2500-word brief, ~30-45 min agent time) followed by one fresh REVIEWER pass. Per-chunk DoD is in the chunk's row below; full DoD is §6.

| Chunk | Title | Prereqs | Sized chunk DoD |
|---|---|---|---|
| **W0** | **Survey + consolidate + console-error fixture** | none | (a) Coverage matrix `admin-ui/e2e/COVERAGE.md` lists every existing spec + what it covers + status (real / stub / broken). (b) The 5 live-container specs are migrated to `admin-ui/e2e/tests/` using existing POMs (extend where helpful); `admin-ui/tests/e2e/` directory removed; `admin-ui/playwright.config.ts` removed. (c) `console-errors.ts` fixture added; every test (via `test.beforeEach` in a `base` fixture file) is wrapped with the listener; intentional synthetic-error test proves it fails when an error fires. (d) `pnpm test:e2e` runs everything from `admin-ui/e2e/` and is green for chromium. (e) `package.json` `test:e2e` script unchanged in name; only the config path stays. |
| **W1** | **CRUD happy paths — Services + Credentials + Agents** | W0 | One spec per resource (`12-services-crud.spec.ts`, `13-credentials-crud.spec.ts`, `14-agents-crud.spec.ts`). Each: create record → list contains it → show renders all fields → edit changes one field → list reflects → delete → list no longer contains it. POM coverage in `pages/`. Uses the existing fixtures or extends them. Each created record has a slug containing `e2e-{nanoid}` so concurrent runs don't collide. |
| **W2** | **CRUD happy paths — Permission Grants + Service API Keys + Tenants** | W0 | Same shape for the remaining 3 resources. Tenants CRUD requires PlatformAdmin (the bootstrap operator is one). Service API Keys per ADR-0018 — verify the create form generates a real `mk_svckey_...` token, shown once. |
| **W3** | **Form validation rendering** | W0 | One spec `18-form-validation.spec.ts` covering: missing required field → field-level error renders → no JS-error box; wrong format → same; constraint violation (e.g. duplicate slug) → server 4xx renders as a normal banner. At least 3 resources covered. |
| **W4** | **Multi-tenant scoping + PlatformAdmin toggle** | W0 + seed-2-tenant fixture (in chunk scope) | A second tenant + operator are seeded via admin-api (HTTP, not direct SQL). The non-PlatformAdmin tenant-A operator session cannot see tenant-B data: list returns 0 for tenant-B content; direct show URL `/admin/resources/services/records/<tenantB-svc-id>/show` 4xx-redirects. PlatformAdmin toggle (if shipped) lets switching tenants; if not shipped, NOTE in COVERAGE.md and skip cleanly with a justified `test.fixme`. |
| **W5** | **Pagination + sorting + logout + session expiry** | W0 | Services list page-navigation (page 2 shows different rows; total count consistent across pages); column sort toggles `?sortBy=…&direction=…`; logout button invalidates the session (next request → /admin/login); expired-session simulation (delete the cookie) → /admin redirects to login, not crash. |
| **W6** | **AdminUiSignedRequest write-auth contract** | W0 | Trigger a write (any CRUD create); intercept the request via Playwright's request listener; assert it carries both `Cookie: mintkey_session=…` AND `Authorization: Bearer <JWT>`; decode the JWT, assert `sub === session.operator_id`, `tnt === session.tenant_id`. Replay test: capture the exact request, replay it within `jti`-TTL → admin-api responds 401 (replay denied via the `admin_request_jti` denylist in ADR-0016.1). |
| **W7** | **Accessibility (axe-core)** | W0 | `@axe-core/playwright` added (single dev dep allowed). One spec `23-accessibility.spec.ts` runs `injectAxe` + `checkA11y` on the dashboard, each of the 7 resource lists, each show page, and each new-form. Baseline: 0 serious / 0 critical violations. Moderate violations logged but not failed. |
| **W8** | **Cross-browser + CI wiring** | all previous | The testcontainer config's `firefox` and `webkit` projects pass for the whole suite. (If a test is fundamentally not portable, mark with `test.skip` per browser project with a comment — but treat as a flag for follow-up.) A GitHub Actions workflow `.github/workflows/playwright.yml` (or equivalent — check what CI the project uses) runs `pnpm test:e2e` on PR for chromium; nightly cron for all three browsers. JUnit + HTML reports uploaded as artifacts. |

**Optional follow-ons** (post-W8, separate orchestrations, NOT in this plan): visual-regression diffing, performance baselines, custom-action coverage (gated on UI features landing), Storybook integration for component-level testing.

## 6 — Definition of Done (whole plan)

1. **One canonical tree** at `admin-ui/e2e/`. `admin-ui/tests/e2e/` removed. `admin-ui/playwright.config.ts` removed (the testcontainer-suite config is the only one).
2. **`pnpm test:e2e`** runs the full suite (≥50 tests once W1-W3 done) against the live `docker compose` stack; chromium green; firefox + webkit green after W8.
3. **Console-error fixture** is active across every spec. A synthetic error test in the suite proves it works.
4. **Page Objects** cover every resource and the dashboard/login/settings pages; no new spec contains raw selectors that a POM could encapsulate.
5. **CRUD round-trips** exist for every resource that has create/edit/delete in the UI.
6. **Form validation, multi-tenant scoping, write-auth contract, pagination/sorting, logout** all have specs.
7. **A11y baseline** is 0 serious / 0 critical violations on the canonical pages.
8. **No anti-patterns** anywhere: no `test.skip` / `test.fixme` (except justified-and-tracked), no `xit` / `xdescribe`, no `expect(true).toBe(true)`, no inlined passwords, no hardcoded UUIDs that drift across runs, no `--no-verify`.
9. **Each chunk = one commit**, conventional message, body documents the TDD failing→passing transition and the screenshots taken.
10. **`COVERAGE.md`** in `admin-ui/e2e/` is up-to-date with every spec, what it covers, and any known gaps.

## 7 — How to run this plan

**Single-agent variant** (one Sonnet works through all chunks): kick off a Sonnet with [`PLAYWRIGHT_MEGA_PROMPT.md`](PLAYWRIGHT_MEGA_PROMPT.md) as its operating brief. It iterates W0 → W8 self-paced.

**Orchestrator variant (recommended)**: the orchestrator (Opus default) reads [`PLAYWRIGHT_ORCHESTRATOR_PROMPT.md`](PLAYWRIGHT_ORCHESTRATOR_PROMPT.md), dispatches one Sonnet IMPLEMENTER per chunk with the XML-tagged brief template, then a fresh REVIEWER, loops on FAIL. Orchestrator never edits code.

**Per-chunk wallclock** (extrapolated from the recent UX-uplift orchestration cadence):
- W0 (the heaviest — migration + fixture + survey): 60-90 min implementer + 20-30 min reviewer.
- W1, W2 (CRUD batches): 45-60 min implementer + 15-20 min reviewer each.
- W3-W7: 30-45 min implementer + 15 min reviewer each.
- W8: 20-30 min implementer + 15 min reviewer.

**Total wallclock estimate**: 7-11 hours of agent runs, spread across whatever cadence works. CI cycles ~2-3 min per chunk's `pnpm test:e2e` run.

## 8 — Risks & mitigations

| Risk | Mitigation |
|---|---|
| Migration breaks currently-green tests | W0's DoD requires all currently-green tests still green AFTER migration; reviewer enforces. |
| Testcontainer suite's pre-existing specs are stubs or broken | W0's coverage matrix marks them; W1+ either fixes the stub-in-place or replaces with a new spec that supersedes. |
| Seeding a second tenant breaks single-tenant assumptions in admin-api | W4 brief is admin-ui-only — the seed-2-tenant happens via admin-api HTTP calls in the fixture (or via the seed-job's idempotent re-run). No admin-api source changes. |
| `pnpm test:e2e` becomes slow as suite grows | Parallel workers (config already enables); a "smoke" project that runs P0 specs only as the PR-blocking subset; full suite nightly. |
| Tautological assertions creep back | Every chunk's DoD has a failing→passing transition captured in the commit body or chunk report; reviewer rejects URL-only assertions on filter / data tests. The console-error fixture is itself a guard. |
| Real seed data shifts across runs (count = 126 today, 130 tomorrow) | Specs use *narrowing* assertions (`expect(count).toBeLessThan(baselineCount)`, `expect(rows).toContain('demo-crm')`) — not exact counts. Already established in `search-and-filters.spec.ts`. |
| Multi-tenant fixture pollutes the seed | Each spec namespaces created records with `e2e-{nanoid}` slugs; teardown deletes by prefix. The existing `global-teardown.ts` is the pattern. |
| Cross-browser flakiness (firefox/webkit) | W8 reviewer runs each browser independently; flaky tests get a follow-up issue, not a `test.skip`. Retries-on-CI is acceptable for known-flaky network-timing cases. |

## 9 — Source links

- Decision provenance: this plan (§3) defers to ADR-0019 for the BFF write-auth shape; ADR-0016.3 for PlatformAdmin RLS escape; ADR-0013 for AdminJS pinning; ADR-0014 for AdminUiSignedRequest.
- Companion prompts: [`PLAYWRIGHT_MEGA_PROMPT.md`](PLAYWRIGHT_MEGA_PROMPT.md), [`PLAYWRIGHT_ORCHESTRATOR_PROMPT.md`](PLAYWRIGHT_ORCHESTRATOR_PROMPT.md).
- Prior remediation orchestration the prompts model on: [`MEGA_PROMPT.md`](MEGA_PROMPT.md), [`ORCHESTRATOR_PROMPT.md`](ORCHESTRATOR_PROMPT.md).
- Repo touchpoints: `admin-ui/e2e/` (target tree), `admin-ui/tests/e2e/` (retiring source), `admin-ui/package.json` (`test:e2e` script), `docker-compose.yml` (live stack).
