# Plan — Playwright E2E Fix

**Session:** `2026-05-24-playwright-e2e-fix`
**Branch:** `fix/playwright-e2e-auth-fixture`

## Execution waves

```
Wave 0:
  C-0  Orchestrator session scaffold (this commit)

Wave 1 — diagnosis:
  C-1  INVESTIGATOR (Opus, read-only) — root-cause analysis + fix proposal

Wave 2 — orchestrator decision:
  C-2  Orchestrator reads C-1 report; defines C-3..C-N implementation chunks

Wave 3..N — implementation (TBD by C-2):
  Likely candidates (depends on C-1 finding):
    - test fixture update (apps/admin-ui/e2e/global-setup.ts, fixtures/test.ts, pages/login.ts)
    - workflow update (.github/workflows/playwright.yml — timeouts, wait-for-stack)
    - admin-ui code (only if login flow itself is broken — unlikely scope creep)

Wave Final:
  C-Final  Fresh full-session REVIEWER (Opus)
  PR open via Mintkey proxy
```

## Strike budget

3 strikes per chunk. After strike 3 failure: HARD STOP, escalate.

## Hard rules

- ORCHESTRATOR does not edit code (only session bookkeeping)
- IMPLEMENTERs touch ONE file per commit where possible; bookkeeping in matching commits
- REVIEWERs are read-only; no code edits, no stack restarts
- No `Co-Authored-By: Claude` trailer on any commit
- No ADR edits (`docs/architecture/01-architecture/adr/**` read-only)
- No `--no-verify`
- All GitHub state changes via Mintkey proxy
- Real secrets never written to repo

## Verification

End-state must show:
- Playwright workflow GREEN on this PR's CI
- All 211 tests accounted for (passed + skipped + intentionally `test.fail()` markers)
- The 36 previously-passing tests still pass (no regression)
- Root cause + fix documented in 99-report.md
