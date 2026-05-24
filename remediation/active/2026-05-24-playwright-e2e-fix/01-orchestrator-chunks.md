# Chunk Catalog — Playwright E2E Fix

**Session:** `2026-05-24-playwright-e2e-fix`
**Branch:** `fix/playwright-e2e-auth-fixture`

## C-0 — Orchestrator session scaffold

| Field | Value |
|---|---|
| Owner files | `remediation/active/2026-05-24-playwright-e2e-fix/*` |
| Action | Create branch + 6 session files; commit baseline |
| Status | in-flight |

## C-1 — INVESTIGATOR (Opus, read-only)

| Field | Value |
|---|---|
| Owner files | NONE (read-only) |
| Action | Diagnose root cause; produce report |
| Deliverable | A written report covering: (a) root-cause hypothesis with evidence; (b) proposed fix with risks; (c) confidence level; (d) what's still uncertain |
| Inputs | The 5 initial hypotheses in ISSUE_INTAKE.md; the failing-job log already at `/tmp/mon_failed_job2.log`; the codebase under `apps/admin-ui/e2e/`; `.github/workflows/playwright.yml`; `apps/admin-api/`; the docker compose stack config under `infra/compose/`; the GitHub Actions log artifacts via Mintkey proxy if needed |
| Forbidden | NO code edits; NO commits; NO stack restarts; NO subagent dispatch |
| DoD | Deliverable saved to `remediation/active/2026-05-24-playwright-e2e-fix/03-investigation-report.md`; orchestrator confirms PASS by reading the report and feeling confident enough to write the C-3..C-N implementation plan |

## C-2 — Orchestrator chunk plan (this turn, after C-1)

| Field | Value |
|---|---|
| Owner files | `01-orchestrator-chunks.md`, `02-matrix.md`, `04-progress.md` |
| Action | Read C-1 report; define implementation chunks C-3, C-4, ... with owner-files and DoD per chunk |

## C-3..C-4 — MVP implementation (post-C-1 investigation)

Per `03-investigation-report.md` (HIGH confidence): the e2e suite fails 56/211 because (a) `PLAYWRIGHT_PASS` GitHub secret is unset → `global-setup.ts` short-circuits; (b) even with the secret set, the old AdminJS internal-auth form has been replaced by an SSO-C login page where Keycloak OIDC is the primary CTA and the break-glass form is hidden in a collapsed `<details>` that's also gated server-side by `internal_password_hash IS NULL → 404`.

The investigator's MVP fix is two chunks (Option A):

### C-3 — IMPLEMENTER: rewrite global-setup.ts for Keycloak OIDC

| Field | Value |
|---|---|
| Owner files | `apps/admin-ui/e2e/global-setup.ts` ONLY |
| Action | Replace the AdminJS internal-form login with a full Keycloak OIDC flow: (a) navigate `${BASE_URL}/auth/start`; (b) Playwright follows the 302 to Keycloak `realms/mintkey/protocol/openid-connect/auth`; (c) fill Keycloak username + password (use defensive selectors: `getByLabel(/username\|email/i)` + `getByLabel(/password/i)` + `getByRole("button", { name: /sign in\|login/i })`); (d) submit and wait for redirect back to admin-ui; (e) save `storageState` (must include the `mintkey_session` cookie). Add helpful debug logs (e.g. `[global-setup] decrypted password length=N`, `[global-setup] cookie domains: ...`). Keep the existing graceful-fallback (`PLAYWRIGHT_PASS not set → warn + return`) but no longer rely on it for CI. |
| Risks | LOW: only touches the fixture. If Keycloak HTML differs from expectations, globalSetup logs the failure and tests run unauthenticated — exactly the current state, no regression. |
| DoD | (i) Code commit isolated to `global-setup.ts`. (ii) Bookkeeping commit updates 02-matrix + 04-progress. (iii) AST parse / `tsc --noEmit` clean against the file (pre-existing project-wide TS errors OK). (iv) Single atomic commit `fix(admin-ui-e2e): rewrite global-setup.ts to drive Keycloak OIDC flow`. |

### C-4 — IMPLEMENTER: workflow decrypts bootstrap password

| Field | Value |
|---|---|
| Owner files | `.github/workflows/playwright.yml` ONLY |
| Action | (1) Drop `PLAYWRIGHT_PASS: ${{ secrets.PLAYWRIGHT_PASS }}` env from both the chromium PR job and the nightly all-browsers job. (2) Add a step BEFORE `Run Playwright tests` that decrypts the bootstrap admin password: read `data/bootstrap-secrets/admin_password`, decrypt with the hardcoded dev KEK (`TUQpz9CUkfOvVJiM0yBUL8J9xAgrzE__JkNnwcocVas=`) using `cryptography.fernet`, write result to `$GITHUB_ENV` as `PLAYWRIGHT_PASS`. Include a non-failing `ls -la data/bootstrap-secrets/` diagnostic line. The bootstrap-secrets directory may not exist if seed-job didn't run; the step should still gracefully no-op (test runs without auth, matches current behavior). |
| Risks | LOW: only adds workflow steps. If decrypt fails, falls back to current behavior. Hardcoded dev KEK is already in `infra/compose/docker-compose.yml` (and `docker-compose.yml` at repo root) — it is a known-dev value, not a real secret. |
| DoD | (i) Code commit isolated to `.github/workflows/playwright.yml`. (ii) `python3 -c "import yaml; yaml.safe_load(open(...))"` exit 0. (iii) Mirror change applied to BOTH the chromium-only PR job and the nightly cross-browser job (if both reference PLAYWRIGHT_PASS). (iv) Bookkeeping commit. (v) Atomic commit `fix(ci/playwright): decrypt bootstrap admin password instead of relying on PLAYWRIGHT_PASS secret`. |

### Out of scope (deferred — investigator gap items)

- Polishing `apps/admin-ui/e2e/pages/login.ts` to expand the `<details>` accordion (only affects `01-login.spec.ts`; deferred per investigator's "MVP=steps 1+2 only" guidance).
- Adding `PLAYWRIGHT_TENANT_ID` / `OPERATOR_ID` / `API_JWT` / `IS_PLATFORM_ADMIN` env exports to unblock the ~10-15 conditionally-skipped tests (orthogonal feature work).
- Adding Playwright to push-to-main triggers (operational hygiene; user can decide separately).

## C-Final — Full-session REVIEWER (Opus, fresh, read-only)

Per PR-#123 C-5 template: scope/lint/secrets/ADR/CO-AUTHORED-BY audit + verification of (i) global-setup OIDC code reads correctly; (ii) workflow YAML parses + decrypt step is wired correctly.

## C-PR — Open PR via Mintkey proxy

Use `99-report.md` as the PR body. Open AFTER C-Final PASS so the CI run on the PR is the verification of the fix.

## Post-PR — Monitor

Orchestrator monitors the Playwright run on the new PR; the success criterion is **≥56 previously-failing tests now pass** (target: 92+ pass, where 36 were already passing and 56 should join them after the fix; the remaining ~80 may skip due to missing PLAYWRIGHT_TENANT_ID etc.).

## C-Final — Full-session REVIEWER (Opus, fresh, read-only)

Same shape as the C-5 reviewer used on PR #123: scope/lint/secrets/ADR/CO-AUTHORED-BY/owner-files audit + alert-state delta check.

## C-PR — Open PR via Mintkey proxy

Use the standard PR-body template from `99-report.md`.
