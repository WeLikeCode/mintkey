# Issue Intake — Playwright E2E Fix

**Session:** `2026-05-24-playwright-e2e-fix`
**Owner:** architect (CiprianSpot)
**Triggered:** 2026-05-24 (immediately after PR #123 merged into main @ `83c6970`)
**Driver:** remediation-orchestrator pattern (ORCHESTRATOR Opus → INVESTIGATOR Opus → IMPLEMENTERs Sonnet → fresh REVIEWERs Opus → final REVIEWER)
**Branch:** `fix/playwright-e2e-auth-fixture` (off `main @ 83c6970`)

## Original brief (verbatim — user, 2026-05-24)

> Please investigate and fix the playwright test that you've identified it failed! Use the orchestrator pattern.

## What we already know (from PR #123's CI monitoring)

Recorded in `~/.claude/projects/.../memory/project_playwright_pre_existing_red_2026-05-24.md`:

- Workflow: `Mintkey Playwright E2E` at `.github/workflows/playwright.yml`. Triggered on `pull_request` against `main`/`develop` when paths include `apps/admin-ui/**`, `apps/admin-api/**`, `docker-compose.yml`, or `.github/workflows/playwright.yml`. NOT triggered on push to `main`, so the failure has been invisible until each new PR.
- **Last 20 runs across all branches: 20/20 FAILED**, going back to dependabot PRs from 2026-05-23 10:54 (i.e. predates everything we've shipped recently).
- Latest run on PR #123 HEAD `c158c9a` (post-C-6 fix): **36 passed, 56 failed, 25 skipped** out of 211 tests (1 worker, chromium only). Wall-clock ~17.6 minutes.
- All 56 failures trace to `apps/admin-ui/e2e/pages/login.ts:30`:
  ```typescript
  await this.page.waitForSelector("input[type=email], input[name=email]", { timeout: 15_000 });
  ```
  Each fails with "Test timeout of 30000ms exceeded" after the 15s waitForSelector exhausts. Diagnostic test (`00-diagnose.spec.ts:43`) confirms when tests navigate to a resource page expecting `input[name="slug"]`, the locator instead resolves to `<input required type="email" name="email" id="bg-email" autocomplete="username">` — meaning the test landed on the AdminJS internal-auth login page rather than the resource page (tests are NOT authenticated).
- C-6 fix in PR #123 (Playwright runbook test import) confirmed working: all 15 runbook tests now pass cleanly. So the C-6 fix is unrelated to the 56 remaining failures.

## Initial hypotheses (UNVERIFIED — must be tested by investigator)

1. **Auth fixture not running**: `apps/admin-ui/e2e/global-setup.ts` may not actually execute the login OR may execute but fail silently. The `storageState` it produces (if any) may not be propagated to tests.
2. **React render race**: AdminJS renders the login form via React bundles. In CI's resource-constrained container, React may take >15s to mount, exhausting the `waitForSelector` window even though the page eventually loads.
3. **Wrong login page**: the test expects internal-auth (email/password), but the deployed admin-ui may redirect to Keycloak SSO first. If `global-setup.ts` doesn't navigate Keycloak's form, no session is established.
4. **Wrong base URL**: tests assume `http://localhost:8081` but the admin-ui may be reachable at a different port in CI.
5. **Stack not actually healthy**: the workflow may launch the stack but proceed before admin-ui is serving. The diagnostic test showing the email input exists on screen weakens this hypothesis but doesn't eliminate it.

## Constraints

- Investigation MUST happen in a fresh subagent (no shared mental state with previous chunks)
- INVESTIGATOR is read-only — no code edits, no commits, no stack restarts
- Investigator's deliverable: root-cause hypothesis + evidence + proposed fix + risk assessment
- Orchestrator decides implementation plan AFTER reading the investigation report

## Out of scope

- Cross-browser Playwright (only chromium fails on PRs; nightly cross-browser is separate)
- Adding new tests
- Refactoring existing test code beyond what's required to unblock CI
- Improving Playwright workflow performance (separate concern)

## Success criteria

1. Playwright workflow turns green on a PR that touches `apps/admin-ui/**` or `apps/admin-api/**`
2. ≥56 of the previously-failing tests now PASS (re-running on the fixed branch)
3. Root cause documented in `99-report.md` so future debugging is faster
4. No regression in the 36 currently-passing tests (re-verify they still pass after the fix)
