# SQL Injection Findings — Session Plan

**Session:** `2026-05-16-sql-injection-findings`
**Branch:** `fix/sql-injection-findings-2026-05-16` (from main @ `5c72062`)
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus)

## Mission

Resolve all 7 SQL-injection-test false positives surfaced in PR-#35's CI run. Hybrid approach (owner-locked):
- **SI-A**: harden `test_no_sql_injection.py` — word-boundary keyword matching kills wire_ids.py false positives; literal-var tracking accepts code where `text(arg)` is called with a variable proven to be built from literals only.
- **SI-B**: refactor the 5 `text()` callers in admin-api to eliminate the dynamic-string pattern entirely (defense-in-depth — passes even the original strict test).

The production code IS actually safe (literal base SQL + bound params) — no real injection. This session adds defense-in-depth + a smarter test.

## Hard rules (every chunk)

- No `Co-Authored-By` trailer.
- No `--no-verify`.
- No `docker compose down -v`.
- No edits to accepted ADRs.
- No changes to API response shapes / endpoint semantics.
- No changes to wire_ids.py (test fix alone resolves their flags).
- Atomic commits.
- Validate via tools: every "done" claim carries reproducible command output (pytest results).

## Chunks

| # | Wave | Chunk | Owner files |
|---|---|---|---|
| SI-A | 1 | Harden test: word-boundary keyword matching + literal-var tracking | `tests/acceptance/test_no_sql_injection.py` |
| SI-B | 1 | Refactor 5 `text()` callers (preferred: SQLAlchemy Core Table API; fallback: full-literal branching) | `admin-api/src/admin_api/api/{api_keys_shortcut,agents,permissions,api_keys}.py` + optional new `admin-api/src/admin_api/db/tables.py` |

Wave 1: SI-A + SI-B in parallel (disjoint files).
Wave 2: REVIEWER (Opus, fresh).

## Closing acceptance criteria

- `test_no_sql_injection_in_admin_api_and_mcp_server` passes locally.
- Existing test suites for affected endpoints (unit + integration + acceptance) still pass.
- No accepted-ADR change.
- No wire_ids.py change.
- `99-report.md` written.
- PR opened, admin-merged (matching prior session pattern).
