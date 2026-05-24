# C-1 Investigation Report — Playwright E2E Fix

**Investigator:** fresh Opus 4.7 (1M context, read-only)
**Date:** 2026-05-24
**Branch reviewed:** `fix/playwright-e2e-auth-fixture` @ `a4b323a` (C-0 baseline; off `main @ 83c6970`)
**Failing job log:** `/tmp/mon_failed_job2.log` (831 KB, 8069 lines; run `26347664794` on HEAD `c158c9a`)
**Stack at fail-time:** all containers `Healthy` before tests ran (admin-ui, admin-api, keycloak, seed-job exited cleanly — log lines 2810–2872)

## TL;DR

Root cause is **two stacked auth-architecture mismatches**: (a) the `PLAYWRIGHT_PASS` GitHub secret is empty in CI, so `global-setup.ts` short-circuits and **never logs in** (log line 2893 `PLAYWRIGHT_PASS not set — skipping global login`); (b) even if `PLAYWRIGHT_PASS` were set, the current `global-setup.ts` would still fail because the test code targets the *old* AdminJS internal email/password form, while the `/admin/login` page has been redesigned (SSO-C, ADR-0019) to render a Keycloak SSO button as the primary CTA with the email/password form hidden inside a collapsed `<details>` accordion that only succeeds **after** `mintkey admin reset-password` has been run (the seed default is `internal_password_hash IS NULL` → admin-api returns 404, per SSO-B). Proposed fix: rewrite `global-setup.ts` to drive the Keycloak OIDC flow (admin@mintkey.internal + the bootstrap password that seed-job already wrote to `data/bootstrap-secrets/admin_password`), and feed the password through the workflow without needing a GitHub secret (it's already deterministically generated in the CI stack). **Confidence: HIGH.**

## Evidence trail

### Hypothesis 1 — Auth fixture not running

**Status: VERIFIED**

Direct log evidence at `/tmp/mon_failed_job2.log:2893`:

```
2026-05-24T00:43:32.8402254Z PLAYWRIGHT_PASS not set — skipping global login. Tests must set storageState themselves.
```

This message is the literal early-return branch in `apps/admin-ui/e2e/global-setup.ts:24-27`:

```ts
if (!USER_PASS) {
  console.warn("PLAYWRIGHT_PASS not set — skipping global login. Tests must set storageState themselves.");
  return;
}
```

Reason `USER_PASS` is empty: the workflow at `.github/workflows/playwright.yml:84-87` reads `PLAYWRIGHT_PASS: ${{ secrets.PLAYWRIGHT_PASS }}`, and the env header in the log at line 2885 confirms `PLAYWRIGHT_PASS:` is rendered with **no value**:

```
2026-05-24T00:43:30.1376853Z   PLAYWRIGHT_PASS: 
```

That's GitHub Actions interpolating an unset secret as an empty string. The Settings → Secrets store has no `PLAYWRIGHT_PASS` configured for this repository, and even if it did, point (b) below would still bite.

Additionally, `apps/admin-ui/e2e/playwright.config.ts:38` only sets the `storageState` if `USER_PASS` is truthy:

```ts
storageState: USER_PASS ? path.resolve(__dirname, "state.json") : undefined,
```

So with `PLAYWRIGHT_PASS=""`: globalSetup writes nothing, the config sets no `storageState`, every test runs with a clean (unauthenticated) browser context.

### Hypothesis 2 — React render race

**Status: REFUTED**

The 12 diagnose tests in `00-diagnose.spec.ts` all log within ~2.2-2.4s that the page body reads:

```
Mintkey Admin | Credential broker for AI agents | Sign in with Keycloak | Break-glass (local password)
```

(log lines 2897-2919) — i.e. the page **fully renders** the login HTML within ≤2.4s. That's the static HTML from `apps/admin-ui/src/auth.ts::renderLoginPage` (no React, no bundles). There is no React rendering pipeline involved at this surface anymore (see point 3 below). The 15-second wait in `pages/login.ts:30` for `input[type=email], input[name=email]` is failing not because of slow render but because **after a `<details>` accordion was added, the input is hidden inside it** (see hypothesis 3).

The 99-runbook tests pass within 2-3 seconds each, well under the 15s budget, confirming that resource-bound CPU is not in play.

### Hypothesis 3 — Wrong login page (Keycloak SSO / accordion)

**Status: VERIFIED** (this is the second half of the root cause)

`apps/admin-ui/src/auth.ts:75-83`:

```ts
* Primary CTA: "Sign in with Keycloak" → /auth/start → admin-api OIDC flow.
* Secondary (collapsed): Break-glass accordion with email+password form that
* proxies to admin-api /v1/auth/internal-login via a server-side relay route
* (/auth/internal-login-proxy) to avoid CORS issues.
*
* The accordion is always rendered but collapsed by default (<details> element).
* Operators only see it if they expand it; it only works after
* `mintkey admin reset-password` has been run (otherwise admin-api returns 404).
```

The rendered HTML at `apps/admin-ui/src/auth.ts:172-192`:

```html
<a href="/auth/start" class="btn-primary">Sign in with Keycloak</a>
<hr class="divider">
<details>
  <summary>Break-glass (local password)</summary>
  ...
  <input type="email" id="bg-email" name="email" required autocomplete="username">
  <input type="password" id="bg-password" name="password" required autocomplete="current-password">
  <button type="submit" class="btn-secondary">Sign in (break-glass)</button>
```

Two consequences:

1. **The email/password input lives inside a *closed* `<details>` element.** Playwright's `waitForSelector` *does* find the input in DOM (selectors match hidden elements by default), so `global-setup.ts:38` would resolve — but `locator.fill()` (line 39) would then fail because the element is **not visible** (inside collapsed `<details>`). Plus `getByRole("button", { name: /sign in|login/i })` matches both `Sign in with Keycloak` (an `<a>` with primary CTA text) *and* `Sign in (break-glass)`, ambiguity that itself causes flake.

2. **Break-glass returns 404 by default.** `apps/admin-api/src/admin_api/api/auth.py:68-74`:

   ```python
   if operator is not None and operator.internal_password_hash is None:
       try:
           _ph.verify(DUMMY_HASH, body.password)
       except Exception:
           pass
       return JSONResponse(status_code=404, content={"mintkey:code": "not_found"})
   ```

   The seed-job at `apps/seed-job/main.py:184-225` explicitly inserts the bootstrap admin operator with `internal_password_hash = NULL` (SSO-B D2-b). It writes the plaintext password to `bootstrap-secrets/admin_password` only so that **Keycloak** can be seeded (`_sync_admin_password`, line 657+). The `internal_password_hash` column is *never* set unless an operator runs `mintkey admin reset-password` via CLI. CI does not run that command.

The diagnose tests' direct DOM dump confirms the user is staring at the break-glass form:

```
2026-05-24T00:43:38.1575439Z [services] hasErr=false bodyHead=Mintkey Admin | Credential broker for AI agents | Sign in with Keycloak | Break-glass (local password)
```

(text from `renderLoginPage`, no AdminJS chrome). And the C-0 prompt mentions the diagnose script seeing `<input required="" type="email" name="email" id="bg-email" autocomplete="username">` — that's the `bg-email` input from the accordion, not an AdminJS-rendered React form.

### Hypothesis 4 — Wrong base URL / port mapping

**Status: REFUTED**

The base URL `http://localhost:8081` matches docker-compose (`infra/compose/docker-compose.yml:268: "8081:8081"`) and the workflow healthcheck at `.github/workflows/playwright.yml:73-79` proves admin-ui responds with `{"status":"ok","service":"admin-ui"}` (log line 2890) at that port before tests start. Diagnose tests successfully navigate to `/admin/resources/services` and read body text — wrong URL would have produced connection refused, not a rendered login page.

### Hypothesis 5 — Stack not healthy

**Status: REFUTED**

The compose `up --wait` step in `.github/workflows/playwright.yml:57-58` reports every container `Healthy` before the test step starts (log lines 2810–2872): postgres, keycloak, admin-api, admin-ui, seed-job (exited cleanly with status 0), mcp-server, vault-adapter, etc. The workflow then runs a redundant 5-min loop on `curl http://localhost:8081/health` which returns `200 ok` on the first iteration (log line 2890). Stack readiness is solid.

### New hypothesis — the test/UI assumptions are stale (PR-#90 architecture rewrite)

**Status: VERIFIED, contextual**

`apps/admin-ui/src/auth.ts` and `apps/admin-ui/e2e/global-setup.ts` reference different authentication architectures. The login page was rewritten under SSO-C (ADR-0019) — primary path is Keycloak OIDC via `/auth/start`, break-glass is a 404-by-default accordion. But the Playwright fixture still assumes the *old* AdminJS internal-auth flow with a freely-fillable React email/password form. This is the architectural cause underneath hypotheses 1 and 3. The branch name `fix/playwright-e2e-auth-fixture` confirms this is the agreed scope.

## What the 36 passing tests have in common

**None of the 36 passing tests assert that the operator is authenticated.** Three sub-groups:

1. **12 × `00-diagnose.spec.ts`** — these are pure forensic probes (`console.log` only, no `expect(...)` on protected content). They pass even when the page is just the login form, because the only assertion is implicit (`hasErr=false` if the body has no "Javascript Error" string and there are no console errors).

2. **8 × misc tests that work regardless of session**:
   - `07-audit.spec.ts` 1-4 — these go through `AuditPage` which uses the admin-api JWT (`PLAYWRIGHT_API_JWT`) for the actual audit-event fetches; the `expect(count).toBeGreaterThanOrEqual(0)` is vacuously true since the locator returns 0 rows on a login page; `actor ID` and `hash chain` tests use `if (await firstRow.isVisible())` guards that no-op when nothing is visible.
   - `08-tenants.spec.ts` #1 (`tenants resource visible`) is gated on `PLAYWRIGHT_IS_PLATFORM_ADMIN === "true"`; the env is set, but the `expect(...).toContainText("Tenants")` should still fail on the login page. Looking closer: in CI the `PLAYWRIGHT_IS_PLATFORM_ADMIN` env is **not exported by the workflow** at `.github/workflows/playwright.yml:84-87` (only `PLAYWRIGHT_PASS`, `PLAYWRIGHT_BASE_URL`, `CI` are exported), so the `if (isPlatformAdmin)` block is skipped and the test is a no-op pass.
   - `08-tenants.spec.ts` #4 is a literal `// Placeholder — requires non-PlatformAdmin credentials` empty test body.
   - `09-settings.spec.ts` #2 (`non-PlatformAdmin cannot access settings`) — passes on a login-redirect-only because the assertion validates inaccessibility, which is exactly what an unauthenticated session produces.
   - `10-security.spec.ts` SEC-5 (`unauthenticated access redirects to login`) — literally tests the unauth case. Trivially green.

3. **16 × `99-runbook-ui-verify.spec.ts`** — every step records `finding("MISLEADING", "Step N", ...)` instead of `expect()` failing on unexpected content. The hard assertion in Step 1 (`expect(page.url()).toContain("/admin")`) passes because `/admin/login` also contains `/admin`. Subsequent steps log lines like `[MISLEADING] Step 4: After save URL: http://localhost:8081/admin/login — unexpected landing page` (log line 3438) but the test does not call `expect()` on that — only `log()` + `finding()`. The whole runbook test suite is a soft-assertion forensic walker, not a gate.

**The common signal**: every passing test is auth-independent (or auth-negative). Every failing test in the 56 attempts to interact with an AdminJS-protected resource (services list, agent create, credential set, etc.) and is redirected to `/admin/login`, then `LoginPage.goto()` times out on the email input because the input is inside a closed `<details>` accordion.

## Root cause

Two stacked defects produce the observed 56/211 failure:

1. **`apps/admin-ui/e2e/global-setup.ts:24-27`** early-returns without logging in because the `PLAYWRIGHT_PASS` GitHub Action secret is unset (`.github/workflows/playwright.yml:85`) and no other source of the bootstrap password is wired into the fixture. Tests run with no `storageState`.

2. **Even if `PLAYWRIGHT_PASS` were set, the fixture targets the wrong UI:** `apps/admin-ui/e2e/global-setup.ts:35-44` assumes a vanilla AdminJS internal-auth form (`input[type=email]` reachable; submit button `name=/sign in|login/i`). But under SSO-C (`apps/admin-ui/src/auth.ts:84-196`) the login page is a static HTML page with **Keycloak as the primary CTA** (`<a href="/auth/start">`) and the email/password form **hidden inside a collapsed `<details>` accordion** (`apps/admin-ui/src/auth.ts:176-192`) that's also gated server-side by `internal_password_hash IS NULL → 404` (`apps/admin-api/src/admin_api/api/auth.py:68-74`; SSO-B from `apps/seed-job/main.py:184-225`).

The page-object `LoginPage.goto()` at `apps/admin-ui/e2e/pages/login.ts:27-31` and the failing tests all transitively hit the same root cause — the call chain is: protected resource navigation → AdminJS auth middleware in `apps/admin-ui/src/index.ts:88-129` redirects to `/admin/login` → tests that use `LoginPage.goto()` (or whose `beforeEach` triggers it implicitly) timeout on the email selector inside the accordion.

## Proposed fix

Recommended **Option A (minimal-surface, fixes both defects at once)**: drive the Keycloak OIDC flow from `global-setup.ts` using the bootstrap admin password that the seed-job already wrote to `data/bootstrap-secrets/admin_password` (encrypted with the known dev-fixture KEK). No GitHub secret needed; CI is fully deterministic on this.

| Step | File | Change | Risk |
|---|---|---|---|
| 1 | `apps/admin-ui/e2e/global-setup.ts` | Replace AdminJS-form login with full Keycloak OIDC flow: (a) navigate to `${BASE_URL}/auth/start`, (b) Playwright follows the 302 to `keycloak:8443/realms/mintkey/protocol/openid-connect/auth?...`, (c) fill Keycloak's username + password fields, (d) submit, (e) wait for redirect back to `admin-api/v1/auth/oidc/callback` → `admin-ui/admin`, (f) save `storageState` (now contains the `mintkey_session` cookie set by admin-api). | LOW — only touches the fixture. If Keycloak's login HTML differs from expectation, the global-setup logs `⚠️  Global setup failed — tests will run unauthenticated`, the existing tests behave exactly as today (i.e., the 56 still fail; 36 still pass). No green-test regression possible by definition. |
| 2 | `.github/workflows/playwright.yml` | (a) Drop `PLAYWRIGHT_PASS: ${{ secrets.PLAYWRIGHT_PASS }}` (no longer needed); (b) Add a step **before** `Run Playwright tests` that decrypts the bootstrap admin password and exports it: `pw=$(MINTKEY_BOOTSTRAP_KEK=... python3 -c "from cryptography.fernet import Fernet; import sys; print(Fernet(sys.argv[1].encode()).decrypt(open(sys.argv[2],'rb').read()).decode())" "$KEK" data/bootstrap-secrets/admin_password)` then `echo "PLAYWRIGHT_PASS=$pw" >> $GITHUB_ENV`. KEK is the dev default `TUQpz9CUkfOvVJiM0yBUL8J9xAgrzE__JkNnwcocVas=` already hard-coded in compose; no secret-store rotation required. | LOW — only adds an env export. If the file/path layout differs, falls through to the existing "skipping global login" path. Mirror the same step in the nightly job too. |
| 3 | `apps/admin-ui/e2e/pages/login.ts` | Either: (a) leave as-is (only `01-login.spec.ts` uses it, those tests `test.skip()` themselves when `PLAYWRIGHT_PASS` is empty — but with #2 it's now set, and the page-object will still hit the closed-accordion problem); OR (b) update `LoginPage.goto()` to expand the `<details>` accordion first via `await this.page.locator("details summary").click()` before `waitForSelector("input[name=email]")`. Note that even with the accordion expanded, internal-login will 404 unless `mintkey admin reset-password` has been run — so the `01-login` tests effectively need to be **rewritten to assert the Keycloak SSO flow** (or kept skipped in CI). Cleanest scope: mark `01-login.spec.ts` body with `test.skip(true, "internal break-glass needs `mintkey admin reset-password`; covered by global-setup OIDC path")` for tests 1, 4, 5 (the ones that require a password) and leave the empty-credentials / invalid-credentials tests in place but update them for the new form. | MEDIUM — small but spans page-object + 5 spec tests. Risk is that the rewritten tests get out-of-sync with the actual UI. Mitigation: keep this OUT of the minimum-viable fix and ship as a Wave-3 follow-up. |

**Minimum viable fix = steps 1 + 2 only.** That gets all 56 failing tests authenticated; the 36 passing tests remain green because they're auth-independent. Step 3 is polish for `01-login.spec.ts` (a 5-test sub-suite); if not done, those 3 tests `test.skip()` themselves cleanly when running against the OIDC flow.

**Alternative Option B (rejected as primary, mention as fallback):** run `mintkey admin reset-password --email admin@mintkey.internal` in the workflow before tests start, then update `global-setup.ts` to expand the accordion and use the break-glass form. This works but is fragile: it requires shelling into the `admin-api` container, knowing the CLI signature, exposing the same plaintext password to the test layer, and the resulting login still hits a *different* code path from production (break-glass instead of OIDC), so the e2e suite no longer covers the realistic production login path. Skip unless A proves infeasible.

## Confidence

**HIGH.** Three independent pieces of evidence converge on the same root cause:

1. Log line 2893 directly shows the global-setup early-return (Hypothesis 1).
2. Log lines 2897-2919 + the source of `auth.ts` show the rendered UI is the SSO-C login page with a collapsed accordion, not an AdminJS React form (Hypothesis 3).
3. Every failing test transitively hits `LoginPage.goto()` (or the `beforeEach` that calls it) and times out at exactly `pages/login.ts:30`. Every passing test is observably auth-independent (00-diagnose, 99-runbook with soft findings, SEC-5 testing unauth itself, etc.).

The fix surface is narrow (2 files for MV, 3 for full polish) and the proposed change converts the fixture to use the exact production login path (Keycloak OIDC), so post-fix the suite will validate the *real* login flow operators actually use. Lower-confidence wrinkle: I didn't fetch and inspect the actual Playwright screenshot artifact from the failing run — but the diagnose-test body dumps + the source of `renderLoginPage()` together give me equivalent evidence (verbatim body text matches the static HTML exactly).

## What I didn't verify (gaps for the next chunk)

1. **Screenshot artifact**: I didn't pull the Playwright `playwright-report-chromium-26347664794` HTML report or the `test-failed-1.png` images from GitHub. The diagnose tests already dump exact body text that matches `renderLoginPage()` verbatim, so the screenshots would be redundant — but if the implementer wants extra confidence, the artifact at `repos/WeLikeCode/mintkey/actions/runs/26347664794/artifacts` should be a one-click download.
2. **Keycloak login HTML structure**: I confirmed the realm is bootstrapped and admin@mintkey.internal is created with a synced password (`apps/seed-job/main.py:_ensure_admin_user`, `_sync_admin_password`), but I did **not** inspect the actual Keycloak `kc.html` form HTML that Playwright will need to scrape. Standard Keycloak 24+ login form uses `input#username` and `input#password` with a `<button name="login">Sign In</button>`, so the implementer should code defensively with `getByLabel(/username|email/i)` + `getByLabel(/password/i)`.
3. **Bootstrap admin password file timing**: The bootstrap secrets are written to a docker named volume (`bootstrap_secrets`) plus a host bind at `data/bootstrap-secrets/`. In CI, the workflow runs `docker compose up -d --wait` followed immediately by the playwright test step; the host bind file should be present by the time step 2 runs but I didn't confirm the actual file path resolution on the runner. The implementer should add a `ls -la data/bootstrap-secrets/` debug line on first commit.
4. **`storageState` cookie scope**: After OIDC, the `mintkey_session` cookie is set on `localhost:8080` (admin-api), but tests navigate `localhost:8081` (admin-ui). The admin-ui's `apps/admin-ui/src/index.ts:88-129` middleware reads the session cookie from the request — I need to confirm whether the cookie's `domain` attribute spans both ports, or whether admin-ui validates the session via an internal call to `admin-api:8080/v1/auth/whoami`. If it's the latter, the cookie *only* needs to live on `:8080` and admin-ui will piggyback. Quick check the implementer should do: after a working `global-setup.ts` OIDC run, dump `await context.storageState()` and grep `mintkey_session` to verify scope.
5. **`PLAYWRIGHT_IS_PLATFORM_ADMIN` / `PLAYWRIGHT_TENANT_ID` / `PLAYWRIGHT_OPERATOR_ID` / `PLAYWRIGHT_API_JWT`**: Several tests gate on these envs being set (eg `08-tenants` Test 2, `10-security` SEC-1/SEC-4). They're documented in `e2e/.env.example` but **not exported by the workflow**. Once login works, those tests will probably skip themselves cleanly — but if the orchestrator wants 211-true-pass coverage rather than 211-accounted-for, a small workflow step to fetch them from admin-api (or hard-code seed values) is needed.

## Verification commands the implementer should run

After implementing steps 1 + 2:

```bash
# Local: spin up the stack as CI does
cd ~/gooseProjects/mintkey
docker compose -f infra/compose/docker-compose.yml up -d --wait --timeout 180

# Confirm the bootstrap admin password file is present
ls -la data/bootstrap-secrets/admin_password
cat data/bootstrap-secrets/.admin_password_synced  # sentinel file

# Decrypt the password locally (sanity check the new workflow step works)
python3 -c "
from cryptography.fernet import Fernet
key = b'TUQpz9CUkfOvVJiM0yBUL8J9xAgrzE__JkNnwcocVas='
print(Fernet(key).decrypt(open('data/bootstrap-secrets/admin_password','rb').read()).decode())
"

# Verify OIDC flow works for the admin user by hand:
# 1. browser: http://localhost:8081/auth/start
# 2. should land on Keycloak login (http://localhost:8443/realms/mintkey/...)
# 3. enter admin@mintkey.internal + <decrypted password>
# 4. should redirect to http://localhost:8081/admin with mintkey_session cookie set

# Run only the new global-setup against the live stack
cd apps/admin-ui
PLAYWRIGHT_BASE_URL=http://localhost:8081 \
PLAYWRIGHT_PASS="$(python3 -c '...')" \
pnpm test:e2e --project=chromium --grep "DIAGNOSE list services"
# Expect: global-setup logs '✅ Global setup — login state saved to ...'
# Expect: the diagnose test body now shows AdminJS dashboard text, NOT 'Sign in with Keycloak'

# Once green, run the full chromium suite
pnpm test:e2e --project=chromium
# Target: 211 tests; ≥ ~180 passed; remaining are intentionally skipped on
# missing env (PLAYWRIGHT_TENANT_ID/OPERATOR_ID/API_JWT) or are test.fail() markers
```

For CI, the implementer should:

1. Push the fix to a side-branch first, e.g. `fix/playwright-e2e-auth-fixture-v1`.
2. Open a draft PR (via Mintkey proxy: `POST /v1/call/svc_01KSA6D0CZXQ9SK3HAJS7MD00M/repos/WeLikeCode/mintkey/pulls`).
3. Watch the `Mintkey Playwright E2E` workflow on that PR; verify the new debug line `[admin_password] decrypted ok, length=43` (or whatever the implementer adds) appears and globalSetup no longer logs the warning.
4. Compare run summary: should now be ≥180 passed instead of 36.
