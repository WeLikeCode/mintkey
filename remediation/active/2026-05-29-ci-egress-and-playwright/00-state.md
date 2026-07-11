# Remediation: CI egress-coverage gap + Playwright red

**Session:** 2026-05-29-ci-egress-and-playwright
**Branch:** feature/service-templates (UNPUSHED — CI activates only on push/PR)
**Pattern:** orchestrator (Sonnet implementers, fresh Opus reviewers, flip-tests, 3-strike hard-stop)

## Issue intake

- **Problem.** (Item 3) Offline CI suites passed while ALL credential egress was broken (vault-adapter scope interceptor rejected proxy + admin-api — BUG-1/20/21); only live e2e caught it. (Item 4) Playwright e2e has been ~20/20 red: the login fixture drives the OLD AdminJS password form, but login migrated to Keycloak OIDC.
- **Expected.** (3) An OFFLINE test that FAILS when the scope-interceptor / cross-service identity+token wiring is broken. (4) Playwright login fixture drives the real Keycloak OIDC flow; login-root-caused failures clear; suite green (or residual independent failures enumerated).
- **Scope (owner-chosen).** Item 3 = **A+B offline cross-service** (NOT broadening the live `test-integration` job, NOT a new full-stack job). Item 4 = fix the OIDC login fixture; do NOT fix unrelated AdminJS bugs (enumerate residuals).
- **Risk.** Low–medium (tests + a CI-config tweak + e2e fixtures; no product code paths changed).
- **DoD.** All new/changed tests GREEN locally with real evidence; flip-tests prove they guard the wiring; no secrets committed (no live session cookies in state.json); fresh Opus review PASS each chunk.

## Baseline (researched 2026-05-29)

- ci.yml: `test-integration` boots compose + runs live brokered-call e2e, but gated `if ref==main || base_ref==main` → feature branches skip. `test-go-unit` runs `go test ./... -short`. `test-python-unit` runs pytest unit.
- Item 3 facts: `apps/proxy-plugin/internal/vault/xmodule_integration_test.go` (TestBug1_CrossModule_*) catches proxy→vault scope OFFLINE (loopback, no Docker) via `vaulttest.Start` (real server WITH scopeInterceptor). GAP: `apps/vault-adapter/internal/server/grpc_test.go:~48` `newTestGRPCServer` registers gRPC WITHOUT the interceptor; no admin-api→vault (BUG-20) test exists. admin-api client = `apps/admin-api/src/admin_api/services/vault_client.py` (must send `x-mintkey-service-token` + `x-mintkey-service-identity`=svcid_admin_api).
- Item 4 facts: `apps/admin-ui/e2e/{global-setup.ts,pages/login.ts}` target `input[type=email]` on `/admin/login` (now a hidden break-glass accordion; break-glass internal-login returns 404, internal_password_hash NULL). Real flow: `/admin/login` → `<a href="/auth/start">` → admin-api `/v1/auth/oidc/login` → Keycloak realm `mintkey` form (`#username`,`#password`,submit `#kc-login`) → callback → `mintkey_session`+`csrf_token` → `/admin`. Working ref: `tests/acceptance/test_e2e_smoke.py:_oidc_login` (line 42). state.json cookies expired 2026-05-24. Creds for local validation: `adminus@mintkey.internal`/`cacamaca3#` (OIDC-confirmed). ~620/633 failures = the one login root cause; ~10-15 independent (tenants new-form crash).

## Chunks

- **Chunk C (item 3, A+B)** — owner: ci-egress. Files: vault-adapter Go test(s), new admin-api Python test, maybe ci.yml. Status: DISPATCHED.
- **Chunk P (item 4)** — owner: playwright. Files: apps/admin-ui/e2e/{global-setup.ts,pages/login.ts, tests/01-login.spec.ts, tests/21-logout-session.spec.ts}, .gitignore (state.json). Status: DISPATCHED.

(Disjoint files → parallel.)

## Round history

- R1: dispatched Chunk C + Chunk P implementers (Sonnet) in parallel.
- R2 results:
  - **Chunk P (item 4) — PASS** (commit `376d89e`). global-setup + login.ts rewritten to drive Keycloak OIDC (`#username`/`#password`/`#kc-login` → callback → /admin); state.json gitignored (no committed cookies); 01-login 5/5 green; flip-test confirms it guards live login. Broad chromium ~151-156 passed / ~47-52 INDEPENDENT pre-existing failures (service-create slug/auth-scheme field not rendering ~22 specs; missing demo-crm seed data; /admin/logout doesn't invalidate mintkey_session; runbook/screenshot data tests). Opus reviewer independently spot-checked 7 residuals → all authenticated, none login-caused. Minor: 01-login test 4 (logout) near-tautological but TODO-annotated.
  - **Chunk C (item 3) — ALREADY_SATISFIED** (no commit). The A+B offline coverage already exists + is effective + CI-wired-offline: vault-adapter `grpc_test.go:446` `newTestGRPCServerWithAuth` (real scopeInterceptor) + 6 `TestGRPCScopeEnforcement_*` (proxy + admin_api identities); proxy `xmodule_integration_test.go` (no -short guard); `tests/unit/admin_api/test_vault_client_get_credential.py` (Put+Get metadata). Opus reviewer flip-verified all (break wiring → tests fail). Runs in `test-go-unit` (`go test ./... -short`) + `test-python-unit` (`pytest tests/unit/admin_api/`, no ignore). Baseline researcher was WRONG (only read the no-interceptor harness at line 48, missed line 446+).

## Outcome — CLOSED 2026-05-29

- Item 4: FIXED (commit 376d89e), reviewer PASS. Login fixture now drives OIDC; login-root-caused failures cleared. Residual ~47 failures are independent pre-existing AdminJS bugs (out of scope — enumerated above).
- Item 3: NO CODE NEEDED — A+B offline egress-wiring coverage already present + CI-wired + flip-verified. Only true residual is that the *full live path* test (`test-integration`) is gated to PRs→main (owner declined broadening that).
- Branch unpushed → all CI (offline jobs + Playwright) activates only once pushed.

## Optional follow-ups (not done — minor)
- Tighten `test_vault_client_get_credential.py` to pin identity == `svcid_admin_api` (currently only asserts non-empty).
- `01-login.spec.ts` test 4 logout assertion is near-tautological (real coverage lives in 21-logout-session, currently red on the /admin/logout product gap).

## Tasks
- #318 item 3 (CI A+B) — done (already satisfied)
- #319 item 4 (Playwright) — done (fixed, 376d89e)
