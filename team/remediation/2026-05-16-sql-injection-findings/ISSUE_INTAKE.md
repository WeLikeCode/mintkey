# Issue Intake — 2026-05-16-sql-injection-findings

**Session:** `team/remediation/2026-05-16-sql-injection-findings/`
**Reported:** 2026-05-16
**Reporter:** Owner — "Open a session for the SQL injection findings"
**Source:** `tests/acceptance/test_no_sql_injection.py` (T-1.0.15; ADR-0014; Req SEC-1/SEC-2)

---

## Problem statement (required)

The `test_no_sql_injection_in_admin_api_and_mcp_server` AST scanner test fails with 7 violations on main HEAD. Per architect review, **all 7 are test false positives** — the production code is actually safe (uses literal-only base SQL + SQLAlchemy bound parameters). The test is too strict in two ways:

1. **wire_ids.py false positives (2 of 7)**: the scanner searches for SQL keywords (`JOIN`, etc.) as substrings against `ast.unparse()` output. Python's `''.join()` method call gets matched because `'JOIN'.lower() in '...join(...)...'.lower()` is True. The fix is word-boundary regex.

2. **`text()` callers false positives (5 of 7)**: the scanner rejects `text(arg)` where `arg` is not a string-literal `ast.Constant`/`BinOp`. But in all 5 callers, `arg` is a local variable (e.g., `base_sql`) that was built via literal-only concatenation — no f-strings, no user input. SQLAlchemy bound parameters carry user input through the `params` dict. The pattern is safe but the test can't see it.

Owner decision: **hybrid** — harden the test (fix the false-positive logic + keep same rule scope) AND refactor the 5 `text()` callers to eliminate the dynamic-string pattern entirely (defense-in-depth).

## User-visible symptom (required)

- `Architecture Tests` job fails on every PR push to GitHub.
- Branch protection's status checks effectively block clean PR merges.
- Test output: "AssertionError: SQL injection patterns found in 7 location(s)" with each file:line.

## Expected behavior (required)

- `test_no_sql_injection_in_admin_api_and_mcp_server` passes on main HEAD.
- Test continues to catch REAL injection patterns (f-string SQL, user-controlled concatenation) in future code.
- Production endpoints still pass their existing test suites (unit + integration + acceptance).
- No regression in API behavior (response shapes, sort order, filter semantics preserved).

## Evidence (required)

Pytest run on 2026-05-16:
```
FAILED tests/acceptance/test_no_sql_injection.py::test_no_sql_injection_in_admin_api_and_mcp_server
AssertionError: SQL injection patterns found in 7 location(s):
  admin-api/src/admin_api/utils/wire_ids.py:59: f-string contains SQL keyword 'JOIN'
  admin-api/src/admin_api/api/api_keys_shortcut.py:91: text() called with non-literal argument
  admin-api/src/admin_api/api/agents.py:402: text() called with non-literal argument
  admin-api/src/admin_api/api/permissions.py:263: text() called with non-literal argument
  admin-api/src/admin_api/api/permissions.py:350: text() called with non-literal argument
  admin-api/src/admin_api/api/api_keys.py:471: text() called with non-literal argument
  mcp-server/src/mcp_server/utils/wire_ids.py:98: f-string contains SQL keyword 'JOIN'
```

Per-violation analysis:

| # | Location | What's there | Why it trips the test | Real risk |
|---|---|---|---|---|
| 1 | wire_ids.py:59 | `return f"{prefix}_{chars[0]}{''.join(chars[1:])}"` | `'JOIN'.lower() == 'join'` is substring of `.join(` | NONE — Python method call, no SQL |
| 2 | api_keys_shortcut.py:91 | `await session.execute(text(base_sql), params)` where `base_sql` = literal concatenation | `text(base_sql)` arg is a `Name` node, not a `Constant` | NONE — base_sql built from literals only; user input bound via params |
| 3 | agents.py:402 | same pattern | same | NONE |
| 4 | permissions.py:263 | same | same | NONE |
| 5 | permissions.py:350 | same; also has `'%' \|\| :q_escaped \|\| '%'` for ILIKE | same; q_escaped is properly bound | NONE |
| 6 | api_keys.py:471 | same | same | NONE |
| 7 | mcp-server wire_ids.py:98 | same as #1 | same as #1 | NONE |

Test source-of-truth: `tests/acceptance/test_no_sql_injection.py` (~125 lines; reviewed in full).

ADR-0014: "No f-string interpolation into SQL" — current code complies; only literal concatenation + bound params.

## Scope (required)

May be changed:
- `tests/acceptance/test_no_sql_injection.py` (improve detection)
- `admin-api/src/admin_api/api/api_keys_shortcut.py` (refactor `text()` caller around line 91)
- `admin-api/src/admin_api/api/agents.py` (refactor `text()` caller around line 402)
- `admin-api/src/admin_api/api/permissions.py` (refactor two `text()` callers around lines 263, 350)
- `admin-api/src/admin_api/api/api_keys.py` (refactor `text()` caller around line 471)
- Possibly NEW: `admin-api/src/admin_api/db/tables.py` (SQLAlchemy Core `Table` definitions) — IF the implementer chooses the Core API approach.
- Session folder.

## Out of scope (required)

MUST NOT be touched:
- `wire_ids.py` files (admin-api + mcp-server) — they have no SQL; the test fix alone resolves their flags.
- `mintkey-models/` (data classes — already pure Pydantic).
- Any product code outside the 4 admin-api files listed above.
- Database schema (`db/migrations/`, `db/schema/`).
- Accepted ADRs.
- CI workflows (separate concern).
- Pre-existing failures from prior sessions (Lint Go errcheck, Schema Integrity Gates openapi drift, license incompatibility, CVE drift).

## Risk level (required)

- **Security**: low — the current code is actually safe (no real injection). The refactor adds defense-in-depth + makes the safety statically verifiable.
- **Behavior regression**: medium — refactoring SQL execution paths in 4 admin-api files. Existing unit/integration/acceptance tests cover these endpoints; implementer must run them post-refactor.
- **Test reliability**: positive — smarter detection reduces false positives, catches real issues going forward.

## Verification target (required)

### SI-A (test improvements)
- `python3 -c "import re; assert re.search(r'(?i)\\bjoin\\b', 'select x from y join z')"` — confirms word-boundary regex works.
- After SI-A: wire_ids.py:59 + mcp-server wire_ids.py:98 should no longer flag.
- The literal-var tracking enhancement: a variable assigned ONLY from string-literal expressions can be passed to `text()` without triggering the violation.
- Add lightweight scanner self-tests (positive + negative) so future regressions in the detection logic are caught.

### SI-B (text() callers refactor)
- After refactor: `text(base_sql)` patterns gone from the 5 sites.
- Approach options (implementer chooses; explain in commit):
  - **(preferred)** Use SQLAlchemy Core's `Table` + `select()/insert()/update()` API; define minimal `Table` schemas in `admin-api/src/admin_api/db/tables.py` for the affected tables.
  - **(simpler)** Split each dynamic if/else into discrete full-literal `text()` calls; each branch passes a string-Constant to `text()`. Pure-literal so it satisfies even the original test.
- Existing test suites for affected endpoints MUST still pass:
  - `tests/unit/admin_api/test_api_keys.py`
  - `tests/unit/admin_api/test_permissions.py`
  - `tests/unit/admin_api/test_agents.py`
  - `tests/integration/admin_api/test_api_keys.py`
  - `tests/integration/admin_api/test_permissions.py`
  - `tests/integration/admin_api/test_agents.py`
  - `tests/acceptance/test_api_keys_and_permissions_chain.py`
  - `tests/acceptance/test_api_keys_and_permissions_carry_forward.py`
- API behavior preserved: same response shapes, same filter semantics, same ORDER BY direction.

### Final integration
- `cd admin-api && uv run pytest ../tests/acceptance/test_no_sql_injection.py -v` → PASS.
- `cd admin-api && uv run pytest ../tests/unit/admin_api/ -v --tb=short` → unchanged pass/fail compared to baseline (pre-session).
- `cd admin-api && uv run pytest ../tests/integration/admin_api/ -v --tb=short` → unchanged pass/fail.

## Owner decisions

- ✅ **Approach**: hybrid (harden test + refactor 5 `text()` callers).
- ✅ **Test scope**: same scope (text() + f-string SQL keywords); just smarter detection.
- Implementer chooses Table API vs branching for SI-B refactor; preferred is Table API for "good condition" but branching is acceptable if Tables would require huge schema definition surgery.

---

## Checklist

- [x] Problem statement (with false-positive analysis)
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (per-violation table + test source)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target (per chunk + final)
- [x] Owner decisions noted
