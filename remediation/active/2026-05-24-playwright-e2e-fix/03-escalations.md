# Escalations — Playwright E2E Fix

**Session:** `2026-05-24-playwright-e2e-fix`

Open questions for owner. None at C-0 time.

## Standing escalation triggers

- **E-1:** Root cause is not in test-fixture code but in admin-ui auth flow itself → fixing requires touching production code in `apps/admin-ui/src/`. Defer for owner decision (scope).
- **E-2:** Root cause is the stack lifecycle in CI (timing, healthcheck order, network) → fix requires `infra/compose/` or `.github/workflows/playwright.yml` edits. Likely OK, but confirm scope is acceptable.
- **E-3:** Test failures are non-deterministic (some pass on retry) → flakiness is a deeper issue; document and propose a quarantine pattern.
- **E-4:** Fixing the failing 56 tests requires changing >5 owner files OR changing more than 200 lines net → STOP, present plan to owner first.
- **E-5:** The fix surfaces a NEW set of failures (e.g. fixes auth but exposes login form deprecation, OR a regression in the 36 currently-passing tests) → STOP, present tradeoff to owner.

## Resolution log

(none yet)
