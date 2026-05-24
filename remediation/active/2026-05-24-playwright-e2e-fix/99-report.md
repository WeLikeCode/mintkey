# 99-report — Playwright E2E Fix

**Session:** `2026-05-24-playwright-e2e-fix`
**Branch:** `fix/playwright-e2e-auth-fixture`
**Base:** `main @ 83c6970` (PR #123 merge — code-scanning remediation v2)
**Status:** **READY TO OPEN PR** (all 4 substantive chunks PASS, C-Final PASS).

---

## Summary (1 paragraph)

The Mintkey Playwright E2E workflow had failed 20/20 most-recent runs because (a) the `PLAYWRIGHT_PASS` GitHub secret was unset, so `apps/admin-ui/e2e/global-setup.ts` short-circuited without logging in, and (b) even if the secret had been set, the fixture targeted an AdminJS internal-auth React form that no longer exists — under SSO-C (ADR-0019), `/admin/login` is now a static HTML page with Keycloak as primary CTA and break-glass server-side-404-gated. This PR rewrites the fixture to drive the production OIDC flow at `/auth/start`, adds a CI step that decrypts the seed-job's bootstrap admin password (the same one the seed-job writes to `data/bootstrap-secrets/admin_password` using the public dev Fernet KEK already in `infra/compose/docker-compose.yml`), and drops the unused `secrets.PLAYWRIGHT_PASS` reference. Zero strikes used; C-3 implementer caught and worked around a Keycloak PatternFly "Show password" toggle strict-mode trap during live-stack verification.

## Commit list

| # | SHA | Subject | Files |
|---|---|---|---|
| 1 | `a4b323a` | chore(repo): C-0 — session scaffold for playwright-e2e-fix | 6 session files |
| 2 | `3bfdfd9` | chore(remediation): C-1/C-2 — investigation HIGH conf, plan 2-file fix | session files (incl. `03-investigation-report.md`) |
| 3 | `eed01a1` | fix(admin-ui-e2e): rewrite global-setup.ts to drive Keycloak OIDC flow | `apps/admin-ui/e2e/global-setup.ts` |
| 4 | `fb41513` | chore(remediation): mark C-3 PASS in matrix + progress | 02-matrix.md, 04-progress.md |
| 5 | `1fb48c3` | fix(ci/playwright): decrypt bootstrap admin password instead of GH secret | `.github/workflows/playwright.yml` |
| 6 | `4d64e47` | chore(remediation): mark C-4 PASS in matrix + progress | 02-matrix.md, 04-progress.md |
| 7 | _this commit_ | chore(remediation): finalize session — full-session PASS, ready for PR | session bookkeeping |

## What this PR fixes

| Symptom | Root cause | Fix |
|---|---|---|
| `apps/admin-ui/e2e/pages/login.ts:30` 15s timeout waiting for `input[type=email]` on 56/211 tests | global-setup.ts short-circuited (no `PLAYWRIGHT_PASS`) → tests ran unauthenticated → each protected-resource navigation redirected to `/admin/login` → the email input lives inside a collapsed `<details>` accordion (SSO-C redesign per ADR-0019) and isn't visible | (C-3) rewrite global-setup.ts to drive the Keycloak OIDC flow at `/auth/start` instead of the deprecated AdminJS form, saving `storageState` with the `mintkey_session` cookie |
| `PLAYWRIGHT_PASS` GitHub secret unset → fixture had no password to use | Secret was never configured; even if it had been, it wouldn't match the seed-generated random password | (C-4) workflow step decrypts `data/bootstrap-secrets/admin_password` (Fernet-encrypted by seed-job) using the public dev KEK already in compose; exports as `PLAYWRIGHT_PASS` to `$GITHUB_ENV`. Drops the `secrets.PLAYWRIGHT_PASS` reference entirely. |

## Expected post-merge outcome

| Population | Before | After |
|---|---|---|
| Tests passing | 36 / 211 | ≥91 / 211 (target: 36 + 55 newly-fixed) |
| Tests failing | 56 / 211 | ≤1 (just `01-login.spec.ts` sub-suite still uses the deprecated AdminJS page-object; out of scope) |
| Tests skipped | 25 / 211 | ~25 (unchanged — env-gated tests like `PLAYWRIGHT_IS_PLATFORM_ADMIN` still skip themselves) |

The actual numbers will be confirmed by the Playwright run on this PR.

## What was deferred (out of scope, documented in `01-orchestrator-chunks.md`)

- **`apps/admin-ui/e2e/pages/login.ts` accordion expansion**: only affects `01-login.spec.ts` (5 tests). Would require either expanding the `<details>` accordion + running `mintkey admin reset-password` to lift the 404 gate, OR rewriting those tests to assert the OIDC flow. Either is more invasive than the MVP fix.
- **`PLAYWRIGHT_TENANT_ID` / `OPERATOR_ID` / `API_JWT` / `IS_PLATFORM_ADMIN` env wiring**: ~10-15 tests gate on these and will continue to skip themselves after this PR. Orthogonal feature work.
- **Playwright trigger on push-to-main**: would have caught the drift earlier. Operational hygiene; user call.

## Tests not run + why

- **Local Playwright full run with 211 tests**: would require ~17 min. The C-3 implementer ran a single-test live-stack verification (DIAGNOSE list services chromium) which confirmed `storageState` is correctly populated and the dashboard renders (not the login page). The CI run on this PR will be the full-suite verification.
- **actionlint**: not on the local PATH. YAML parse exit 0 is the substituted check.
- **Cross-browser (firefox / webkit)**: only the chromium PR job is gating; the nightly job is on a separate schedule.

## Residual risks

1. **Keycloak HTML drift**: the fixture uses defensive selectors (`input#username, input#email, input[name=username], input[name=email]` + `input#password, input[name=password], input[type=password]` + `button[name="login"], input[type="submit"], button[type="submit"]`). If Keycloak's PatternFly theme changes in a way that doesn't match any of these, the fixture's try/catch will log `❌` and delete the stale state — tests run unauth, matching today's broken state, no new failure mode.
2. **Seed-job not running**: if `data/bootstrap-secrets/admin_password` is missing in CI for any reason, the decrypt step emits `::warning::` and `exit 0`. Fixture then falls back to no-PASS path. Same gracefully-degraded behavior as today.
3. **`01-login.spec.ts` continues to fail** until separate follow-up. Documented + acknowledged.
4. **Dev KEK in workflow file**: the value `TUQpz9CUkfOvVJiM0yBUL8J9xAgrzE__JkNnwcocVas=` is the documented public dev KEK already in compose. It is NOT a production secret. If the project ever rotates the dev KEK, the workflow + compose + this commit's hardcoded value all need to be updated together.

## Follow-up

- Operator merges this PR
- Confirm Playwright workflow goes green (or at minimum, ≥91 / 211 passing) on the CI run
- Open a separate PR for `01-login.spec.ts` polish if/when the deprecated AdminJS form gating is removed OR rewrite tests for OIDC
- Optional: separate PR to wire `PLAYWRIGHT_TENANT_ID`/`OPERATOR_ID`/`API_JWT`/`IS_PLATFORM_ADMIN` env exports
- Optional: add Playwright trigger on push-to-main so the next drift is caught immediately

## Sign-off

ORCHESTRATOR finalization: PASS. 7 commits since main, working tree clean, ready for `gh pr create` via Mintkey proxy.
