# Python Test Infra — Escalation Log

**Session:** `2026-05-16-python-test-infra`

---

## Escalations

### E-1 — ruff + mypy pre-existing errors (admin-api)

**Raised by:** ORCHESTRATOR
**Date:** 2026-05-16
**Blocking:** Lint Python CI job

**Question:** admin-api has 53 ruff errors and 126 mypy errors that are pre-existing. These are far over the ≤5/file inline-fix threshold. Should a dedicated lint/type-fix session be dispatched?

**Options considered:**
- A: Fix inline in this session (too broad; risks introducing bugs)
- B: Defer to dedicated session (recommended)

**Owner answer:** Deferred — separate lint session needed.
**Status:** ✅ resolved (deferred)

---

### E-2 — mintkey-models Python version mismatch

**Raised by:** ORCHESTRATOR
**Date:** 2026-05-16
**Blocking:** mintkey-models test CI job

**Question:** The mintkey-models tests run with system Python 3.9 (anaconda) but `pyproject.toml` requires `>=3.11`. 13 tests fail with `TypeError: Unable to evaluate type annotation 'str | None'`. This is an environment/CI config issue, not a code issue.

**Options considered:**
- A: Lower `requires-python` (wrong — regresses the package)
- B: Add `eval_type_backport` for 3.9 compat (wrong — the code is correct for 3.11+)
- C: Fix CI to use Python 3.11+ for mintkey-models (correct)

**Owner answer:** Deferred — CI env fix needed; not a code change.
**Status:** ✅ resolved (deferred)

---

### E-3 — mcp-server ruff errors

**Raised by:** ORCHESTRATOR
**Date:** 2026-05-16
**Blocking:** Lint Python CI job (low priority)

**Question:** mcp-server has 3 pre-existing ruff fixable errors (unused imports). Should these be fixed in this session?

**Options considered:**
- A: Fix inline — only 3 errors, all auto-fixable
- B: Defer to dedicated lint session

**Owner answer:** Deferred — out of scope for this infra session.
**Status:** ✅ resolved (deferred)
