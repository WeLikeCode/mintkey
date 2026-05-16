# SQL Injection Findings — Closing Report

**Session:** `2026-05-16-sql-injection-findings`
**Branch:** `fix/sql-injection-findings-2026-05-16`
**Status:** CLOSED-LOCAL-PASS_ALL (PR open pending admin-merge)
**Closed by:** Final REVIEWER subagent (Opus, fresh)

## Summary

7 SQL-injection-test violations on main HEAD were all false positives — production code was already safe (literal-only base SQL + bound params). Resolved via hybrid:
- **SI-A**: hardened scanner detection (word-boundary regex with negative-lookbehind for `.`; `LiteralVarTracker` for literal-only var assignments; 22 self-tests).
- **SI-B**: refactored 5 dynamic `text(base_sql)` callers — 4 use Option B (full-literal branching), 1 uses Option A (SQLAlchemy Core Table API). New `admin-api/src/admin_api/db/tables.py` for the Core API site.

No real injection was found. No product behavior changed. All 138 admin-api unit tests still pass.

## Verification commands and exit codes (REVIEWER re-run, fresh Opus)

```
$ cd admin-api && uv run pytest ../tests/acceptance/test_no_sql_injection.py -v
24 passed in 0.07s        # exit 0
# Includes:
#   - test_no_sql_injection_in_admin_api_and_mcp_server  (the gate)
#   - test_scan_covers_admin_api_health_and_middleware  (smoke)
#   - 22 new scanner self-tests

$ cd admin-api && uv run pytest ../tests/unit/admin_api/ -v
138 passed                # exit 0; no regressions

$ git status --short
M admin-api/src/admin_api/api/agents.py
M admin-api/src/admin_api/api/api_keys.py
M admin-api/src/admin_api/api/api_keys_shortcut.py
M admin-api/src/admin_api/api/permissions.py
M tests/acceptance/test_no_sql_injection.py
?? admin-api/src/admin_api/db/tables.py
# (Plus 99-report.md staging — this file)
# Exactly the documented scope; no wire_ids.py change; no ADRs touched.

$ git diff --name-only HEAD~2 HEAD -- "**/wire_ids.py" docs/architecture/01-architecture/adr/ mintkey-models/ .github/
# empty — out-of-scope honored
```

## Chunks completed

| Chunk | Commit | Closes | Reviewer | Rounds |
|---|---|---|---|---|
| SI-A: scanner hardening (regex + LiteralVarTracker + 22 self-tests) | `e20092f` | wire_ids.py:59, mcp-server wire_ids.py:98 FPs; future detection of real injection patterns | PASS | 1 |
| SI-B: refactor 5 text() callers + new tables.py | `2111b6b` | 5 text() caller FPs; defense-in-depth (production code now provably safe to even a strict scanner) | PASS | 1 |

2 atomic commits over session scaffold.

## DoD checklist — final state

- [x] `test_no_sql_injection_in_admin_api_and_mcp_server` passes locally.
- [x] Scanner self-tests added (22 cases: positive + negative + tracker + keyword-helper).
- [x] All 5 `text(base_sql)` callers refactored.
- [x] All 138 admin-api unit tests pass post-refactor.
- [x] No accepted-ADR change.
- [x] No wire_ids.py change (test fix alone resolved their FPs).
- [x] No `Co-Authored-By` trailer.
- [x] No `--no-verify`.
- [x] API response shapes preserved (verified per endpoint).
- [x] ORDER BY direction preserved.

## Residual risks / deferred items

- **`admin-api/src/admin_api/db/tables.py` nullability flags** — the new Table definitions do not declare `nullable=False` on columns that are NOT NULL in the Liquibase schema (permission_grants.service_id/action/constraints/created_at/created_by; services.name/slug; agents.name). For SELECT-only construction (current use), this is decorative metadata. If these tables are later used for INSERT/UPDATE or DDL, the flags should be added.
- **Option B full-literal branching** is more verbose than the original dynamic concatenation (4-8 branches per query vs 1 builder). Trade-off is intentional: each branch is independently auditable; future contributor can't accidentally introduce f-string interpolation in one branch without affecting others. Migration to full Option A (SQLAlchemy Core everywhere) would unify the style but requires a larger Table-definition session.
- **Pre-existing real bugs from prior sessions** still red on main (Lint Go errcheck, Schema Integrity Gates openapi drift, Dependency Review license, container-scan CVE drift). Each is its own session.

## Escalation resolutions

None during the session. Owner pre-answered both forks:
1. Approach → hybrid (test + refactor).
2. Test scope → same scope, smarter detection.

## Lessons learned

- **Substring matching in static-analysis tests is fragile.** Always use word-boundary regex when matching keywords in unparsed source. The `(?<!\.)` negative-lookbehind is essential to avoid method-call false positives — plain `\bJOIN\b` would still match `.join(`.
- **Static SQL-injection scanners need scope-aware variable tracking.** Without it, the safest pattern (literal-concat into a base_sql var, then `text(base_sql)` with bound params) trips the test. With it, the scanner can statically verify the literal-only invariant.
- **AST visitor with shared scope state** requires the visitor pattern + scope stack to be wired carefully — both the LiteralVarTracker and the SqlInjectionVisitor needed to push/pop scopes in lockstep so `text(name)` checks consult the right scope.
- **Defense-in-depth often pays back beyond test compliance.** The Option B branches are uglier than dynamic concat but each branch is independently grepable for "what SQL does this endpoint execute". This is valuable for security review even after the test passes.
- **SQLAlchemy Core (Table + select()) is reachable without ORM.** Mintkey doesn't have an ORM model layer; Table reflections + Core API give the safety + ergonomics of an ORM-style fluent API for the most complex query (permissions.py:350) without committing to a full ORM.
