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

## C-3..C-N — Implementation chunks (TBD after C-1+C-2)

Filled in by C-2.

## C-Final — Full-session REVIEWER (Opus, fresh, read-only)

Same shape as the C-5 reviewer used on PR #123: scope/lint/secrets/ADR/CO-AUTHORED-BY/owner-files audit + alert-state delta check.

## C-PR — Open PR via Mintkey proxy

Use the standard PR-body template from `99-report.md`.
