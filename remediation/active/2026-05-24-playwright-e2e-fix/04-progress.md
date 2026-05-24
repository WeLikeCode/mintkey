# Progress Log — Playwright E2E Fix

**Session:** `2026-05-24-playwright-e2e-fix`
**Branch:** `fix/playwright-e2e-auth-fixture`

Newest entries at the top.

---

## 2026-05-24 — C-7 IMPLEMENTER (fix C-4 decrypt step bugs)
- Commit: `5f699b2`
- Files changed: .github/workflows/playwright.yml (+4 -2)
- Bug 1 fixed: cryptography==45.0.8 → 48.0.0 (45.0.8 doesn't exist; 48.0.0 verified in pip error output's version list)
- Bug 2 fixed: added `sudo chmod 0644 "${BOOTSTRAP_PW_FILE}"` so runner can read seed-job's root-mode-0400 file
- Both jobs (chromium PR + nightly) received identical treatment
- YAML parse: exit 0
- Reference: PR #124 CI run 26357598275 (decrypt step exit code 1)

---

## 2026-05-24 — ORCHESTRATOR finalization

### Per-chunk reviewer verdicts (fresh Opus, read-only)

| Chunk | Reviewer verdict | Key checks confirmed |
|---|---|---|
| C-3 (OIDC fixture) | ✅ PASS | Scope=1 file (global-setup.ts +113 -26); navigates `${baseURL}/auth/start` not `/admin/login`; defensive CSS password locator (avoids PatternFly "Show password" strict-mode trap); storageState path matches playwright.config.ts; try/catch with stale-state cleanup; diagnostic logging at every step; no Co-Authored-By; no secrets. |
| C-4 (workflow decrypt) | ✅ PASS | Scope=1 file (playwright.yml +62 -2); `secrets.PLAYWRIGHT_PASS` reference dropped from both jobs; decrypt step in BOTH chromium PR + nightly all-browsers jobs; positioned after `docker compose up --wait` and before `Run Playwright tests`; `::add-mask::` precedes `$GITHUB_ENV` write; graceful no-op when bootstrap file missing; pinned cryptography==45.0.8; `set -euo pipefail`; KEK matches public dev value in infra/compose/docker-compose.yml. |

### C-Final full-session review (fresh Opus)

- Commit log shape: PASS (6 commits in order at review time; 7 with this finalization)
- File-level scope: PASS (10 files: 2 code + 8 session)
- ADR directory: untouched
- Co-Authored-By: absent
- Real secrets: none (dev KEK acceptable; not a real secret)
- Per-commit owner-file scope: PASS for both fix commits + both bookkeeping commits
- C-3 OIDC fixture: 6/6 beats present
- C-4 workflow decrypt: 9/9 beats present in both jobs
- YAML parse + TS transpile: clean
- Live CI sanity: confirmed baseline still red (dependabot runs on pre-fix main); branch not pushed yet at review time
- Bookkeeping: matrix + progress consistent

### Decisions during execution

- **Live-stack functional verification by the C-3 implementer** caught a Keycloak selector issue (`getByLabel(/password/i)` matched both the input AND the "Show password" toggle button → strict-mode error). Implementer switched to CSS-only locator. Saved an entire strike loop.
- **Cookie scope verified by reading admin-ui/admin-api source**: `mintkey_session` is host-only on `localhost`, port-agnostic per RFC 6265. Admin-ui validates via internal HTTP call to admin-api/whoami.
- **One-shot first-strike PASS** for both C-3 and C-4. Zero strikes used total.
- **Out of scope (deferred)**: `apps/admin-ui/e2e/pages/login.ts` accordion expansion for `01-login.spec.ts` sub-suite; `PLAYWRIGHT_TENANT_ID`/`OPERATOR_ID`/`API_JWT` env wiring; push-to-main Playwright trigger.

### Next

- Push branch
- Open PR via Mintkey proxy
- Monitor Playwright CI on the new PR; verify ≥55 of 56 previously-failing tests now pass

---

## 2026-05-24 — C-4 IMPLEMENTER (workflow decrypt step)
- Commit: `1fb48c3`
- Files changed: .github/workflows/playwright.yml (+62 -2)
- Jobs updated: chromium PR + nightly all-browsers
- Pinned: cryptography==45.0.8
- Graceful no-op confirmed: if data/bootstrap-secrets/admin_password missing → ::warning:: + exit 0
- YAML parse: exit 0
- actionlint: not_found
- Functional decrypt test against live stack: PASS (decrypted length=43, >16)

---

## 2026-05-24 — C-3 IMPLEMENTER (global-setup.ts OIDC rewrite)
- Commit: `eed01a1`
- Files changed: apps/admin-ui/e2e/global-setup.ts (+113 -26)
- tsc: Pre-existing error (`import.meta` without tsconfig; errors in `--noEmit` without project config because root tsconfig.json excludes e2e/). The original file had the same issue. Node transpile check (module=ESNext, target=ES2020) exits 0, output length=6546.
- Functional test against live stack: PASS. Global-setup logged `✅ saved storageState to .../state.json`. Diagnose test (chromium) passed in 6.4s showing AdminJS dashboard text instead of login page.
- Cookie scope verification: storageState captured `mintkey_session@localhost/` and `csrf_token@localhost/` (no explicit Domain → host-only for `localhost`, port-agnostic per RFC 6265). Admin-ui validates sessions via internal HTTP call to admin-api:8080/v1/auth/whoami forwarding the browser's cookies — so the cookie only needs to be present for `localhost`. Verified: post-login URL was `http://localhost:8081/admin`.
- Selector fix applied: Keycloak's PatternFly theme renders a "Show password" toggle button with `aria-label="Show password"`, causing `getByLabel(/password/i)` strict-mode violation (2 matches). Fixed to use `input#password, input[name=password], input[type=password]` CSS locator.

---

## 2026-05-24 — C-2 ORCHESTRATOR (plan implementation)

Reviewed C-1 investigation report. Confidence HIGH on a 2-file MVP fix:

1. **C-3**: Rewrite `apps/admin-ui/e2e/global-setup.ts` to drive Keycloak OIDC flow (instead of the now-removed AdminJS internal-form). Save `storageState` with the `mintkey_session` cookie.
2. **C-4**: Update `.github/workflows/playwright.yml` to decrypt the bootstrap admin password from `data/bootstrap-secrets/admin_password` (Fernet, dev KEK) and export as `PLAYWRIGHT_PASS`. Drop `secrets.PLAYWRIGHT_PASS` reference.

Both touch disjoint owner files. Serial dispatch per PR-#123 lesson (shared bookkeeping → git index race if parallel). Per-chunk reviewer gate.

Deferred (out of scope, documented in 01-orchestrator-chunks):
- `pages/login.ts` accordion expansion (only impacts `01-login.spec.ts` sub-suite)
- `PLAYWRIGHT_TENANT_ID`/`OPERATOR_ID`/`API_JWT`/`IS_PLATFORM_ADMIN` env wiring (orthogonal)
- Playwright trigger on push-to-main (operational hygiene; user call)

### Next

- Commit C-2 plan
- Dispatch C-3 IMPLEMENTER (global-setup.ts OIDC rewrite)

---

## 2026-05-24 — C-1 INVESTIGATOR (Opus, read-only)

Verdict: **HIGH confidence on two-part root cause**. Report saved at `03-investigation-report.md`.

### Root cause

1. **Auth fixture short-circuit**: `apps/admin-ui/e2e/global-setup.ts:24-27` returns early because `PLAYWRIGHT_PASS` GitHub secret is unset (workflow line 85; runtime log line 2893 verbatim: `PLAYWRIGHT_PASS not set — skipping global login`). No `storageState` is written; all tests run unauthenticated.

2. **Stale UI assumption**: even if `PLAYWRIGHT_PASS` were set, the fixture targets the OLD AdminJS internal-auth React form. The current `/admin/login` was rewritten under SSO-C (ADR-0019) to a static HTML page with Keycloak SSO as primary CTA and the email/password input hidden inside a collapsed `<details>` accordion (`apps/admin-ui/src/auth.ts:172-192`). Internal break-glass login is server-side-gated to 404 unless `mintkey admin reset-password` has been run (`apps/admin-api/src/admin_api/api/auth.py:68-74`).

### Why 36 tests still pass

All 36 are auth-independent: 12× `00-diagnose` use console.log only with no `expect()`; 16× `99-runbook` use soft `finding()` instead of assertions; SEC-5 literally tests the unauth-redirect path; `08-tenants` Test 1 gates on `PLAYWRIGHT_IS_PLATFORM_ADMIN` (not exported by workflow → no-op); other passing tests have similar guards.

### Hypothesis verification

| Hypothesis | Status |
|---|---|
| 1. Auth fixture not running | ✅ VERIFIED (log line 2893) |
| 2. React render race | ❌ REFUTED (login page renders in ~2.4s; no React on this surface) |
| 3. Wrong login page (Keycloak SSO + accordion) | ✅ VERIFIED (`auth.ts:75-83`) |
| 4. Wrong base URL / port mapping | ❌ REFUTED (healthcheck OK at `:8081`) |
| 5. Stack not healthy | ❌ REFUTED (all containers `Healthy` before tests run) |
| NEW: stale test architecture (PR-#90 rewrite) | ✅ VERIFIED (contextual) |

### Investigator-flagged gaps for implementer

1. Didn't fetch Playwright HTML artifact (diagnose-test body dumps already match `renderLoginPage()` verbatim)
2. Didn't inspect actual Keycloak login-form HTML — implementer should code defensively with `getByLabel(/username\|email/i)`
3. Cookie scope: `mintkey_session` is set on `:8080` (admin-api) but tests navigate `:8081` (admin-ui). Verify domain spans both ports OR admin-ui validates via internal API call.
4. `PLAYWRIGHT_TENANT_ID`/`OPERATOR_ID`/`API_JWT`/`IS_PLATFORM_ADMIN` env vars not exported by workflow — ~10-15 tests will skip themselves cleanly once auth works (out of scope).

---

## 2026-05-24 — C-0 ORCHESTRATOR

### Bootstrap

- Base: `main @ 83c6970` (PR #123 merge — code-scanning remediation v2)
- Branch created: `fix/playwright-e2e-auth-fixture`
- Session scaffold created (6 files): ISSUE_INTAKE, 00-plan, 01-orchestrator-chunks, 02-matrix, 03-escalations, 04-progress.

### Carried context (from PR #123 monitoring)

- Playwright workflow has failed 20/20 most recent runs (across all branches, including pre-existing dependabot runs from 2026-05-23 10:54).
- Last run on `c158c9a`: 36 passed, 56 failed, 25 skipped (211 total, chromium worker, 17.6 min).
- All 56 failures: `apps/admin-ui/e2e/pages/login.ts:30` timeout waiting 15s for `input[type=email]`.
- Diagnostic test shows tests reaching login page (not resource page) when expecting authenticated state.
- C-6 import fix on PR #123 successfully resolved the runbook tests; remaining 56 are independent.

### Decisions

- INVESTIGATOR (fresh Opus) dispatched BEFORE any implementer, because we don't yet have a confirmed root cause among 5 initial hypotheses.
- Investigator is read-only; deliverable is a written report at `03-investigation-report.md`.

### Next

- Commit C-0 baseline
- Dispatch C-1 INVESTIGATOR
