# SQL Injection Findings 2026-05-16 — Tracking Matrix

**Session:** `2026-05-16-sql-injection-findings`
**Status:** ✅ SI-A done; SI-B done

---

## Severity legend

| Severity | Meaning |
|---|---|
| P0 | Blocking — session cannot close without this |
| P1 | High — must address before the closing report |
| P2 | Medium — fix this session if possible; escalate if not |
| P3 | Low — document as residual; defer acceptable |

## Status legend

| Symbol | Meaning |
|---|---|
| ⬜ | Not started |
| 🔵 | In progress |
| ✅ | Fixed and reviewer-verified |
| ⏭️ | Deferred to a future session (document in 99-report.md) |
| n/a | Not applicable |

---

## Matrix

| # | Area | Finding | Severity | Chunk | Status | Notes |
|---|---|---|---|---|---|---|
| M-1 | `admin-api` scanner | `wire_ids.py` f-string with JOIN keyword flags `test_no_sql_injection` | P0 | SI-A | ✅ | Word-boundary + `(?<!\.)` lookbehind regex; no longer flags |
| M-2 | `mcp-server` scanner | `wire_ids.py` f-string with JOIN keyword flags `test_no_sql_injection` | P0 | SI-A | ✅ | Same fix as M-1; no longer flags |
| M-3 | `api_keys_shortcut.py:91` | `text(base_sql)` dynamic-string pattern — defense-in-depth | P2 | SI-B | ✅ | Option B: 4-branch explicit literals |
| M-4 | `agents.py:402` | `text(base_sql)` dynamic-string pattern — defense-in-depth | P2 | SI-B | ✅ | Option B: 4-branch explicit literals (includes EXISTS subquery) |
| M-5 | `permissions.py:263` | `text(base_sql)` dynamic-string pattern — defense-in-depth | P2 | SI-B | ✅ | Option B: 2-branch explicit literals |
| M-6 | `permissions.py:350` | `text(base_sql)` dynamic-string pattern — defense-in-depth; 3 optional filters + LEFT JOINs | P2 | SI-B | ✅ | Option A: SQLAlchemy Core select() with chained .where(); tables.py created |
| M-7 | `api_keys.py:471` | `text(base_sql)` dynamic-string pattern — defense-in-depth | P2 | SI-B | ✅ | Option B: 4-branch explicit literals |

---

## SI-A Verification (2026-05-16)

```
$ cd admin-api && uv run pytest ../tests/acceptance/test_no_sql_injection.py -v --tb=short
============================= test session starts ==============================
platform darwin -- Python 3.12.12, pytest-9.0.3, pluggy-1.6.0
collected 24 items

test_no_sql_injection_in_admin_api_and_mcp_server PASSED
test_scan_covers_admin_api_health_and_middleware PASSED
test_scanner_kw_join_matches_in_sql_context PASSED
test_scanner_kw_join_not_matched_in_python_join_method PASSED
test_scanner_kw_join_not_matched_in_wire_ids_fstring_repr PASSED
test_scanner_kw_from_matches_as_word PASSED
test_scanner_kw_from_not_matched_in_identifier_substring PASSED
test_scanner_kw_set_local_multiword_flexible_whitespace PASSED
test_scanner_positive_fstring_with_sql_where PASSED
test_scanner_positive_text_with_fstring_arg PASSED
test_scanner_positive_text_with_string_plus_variable PASSED
test_scanner_positive_text_with_var_tainted_by_user_input PASSED
test_scanner_positive_fstring_sql_join_keyword PASSED
test_scanner_positive_text_var_reassigned_from_noliteral PASSED
test_scanner_negative_text_pure_literal PASSED
test_scanner_negative_text_var_built_from_literals_only PASSED
test_scanner_negative_production_base_sql_pattern PASSED
test_scanner_negative_python_join_in_fstring_not_flagged PASSED
test_scanner_negative_fstring_no_sql_keywords PASSED
test_scanner_negative_text_literal_binop PASSED
test_literal_var_tracker_simple_literal PASSED
test_literal_var_tracker_tainted_by_unknown_name PASSED
test_literal_var_tracker_augassign_stays_pure PASSED
test_literal_var_tracker_augassign_taints PASSED

24 passed in 0.08s
```

---

## Verification DoD checklist

Reviewer runs these before writing `99-report.md`:

- [x] wire_ids.py:59 and mcp-server wire_ids.py:98 no longer flag (M-1, M-2 fixed by SI-A)
- [x] All 5 text(base_sql) callers accepted by scanner with literal-var tracking (SI-A) OR refactored out (SI-B)
- [x] 24 total tests in test_no_sql_injection.py all pass (22 new self-tests + 2 original)
- [ ] `uv run pytest tests/unit/admin_api/test_api_keys.py tests/unit/admin_api/test_permissions.py tests/unit/admin_api/test_agents.py -v` — verify unchanged post-SI-B
- [ ] `test_no_sql_injection_in_admin_api_and_mcp_server` PASSES (verified ✅ by SI-A above)
- [x] No `Co-Authored-By` trailer in any new commit
- [x] No `--no-verify` used
