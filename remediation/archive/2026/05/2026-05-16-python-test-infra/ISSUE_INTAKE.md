# Issue Intake — 2026-05-16-python-test-infra

## Problem statement

CI Python test jobs fail because `testcontainers` is not listed in `admin-api/pyproject.toml` dev dependencies. Acceptance tests that spin up a real PostgreSQL container via `testcontainers.postgres.PostgresContainer` cannot even be collected. Additionally, ruff (53 errors) and mypy (126 errors) show pre-existing lint/type violations that are out of scope for this infra-only session.

## User-visible symptom

```
ModuleNotFoundError: No module named 'testcontainers'
ERROR collecting tests/acceptance/test_audit_append_only.py
Interrupted: 1 error during collection
```

## Expected behavior

Acceptance tests that import `testcontainers` are collected and run. The infra gap is closed; real test failures (if any) surface rather than being masked by import errors.

## Evidence

- `tests/acceptance/test_audit_append_only.py:27` — `from testcontainers.postgres import PostgresContainer`
- `admin-api/pyproject.toml` `[dependency-groups].dev` — `testcontainers` absent
- Running `uv run pytest ../tests/acceptance/test_audit_append_only.py` confirms import error before fix.

## Scope

`admin-api/pyproject.toml` — add `testcontainers[postgres]>=4.7` to `[dependency-groups].dev`; regenerate `admin-api/uv.lock`.

## Out of scope

Ruff/mypy lint errors (pre-existing, 53 + 126 respectively — far over the ≤5/file threshold for inline fixes); mintkey-models Python 3.9 env issue (system anaconda Python conflicts with `requires-python = ">=3.11"` — separate session needed); mcp-server ruff errors (3, but pre-existing; no testcontainers needed there).

## Risk level

CI (acceptance test collection blocked).

## Verification target

```
cd admin-api && uv run pytest ../tests/acceptance/test_no_sql_injection.py \
  ../tests/acceptance/test_audit_coverage.py ../tests/acceptance/test_audit_append_only.py \
  ../tests/acceptance/test_sqlalchemy_mirror.py ../tests/acceptance/test_platform_admin_rls.py \
  ../tests/acceptance/test_no_plaintext_in_spans.py ../tests/acceptance/test_otel_collector_redaction.py
# 41 passed, exit 0
```

## Owner decisions needed

None for the testcontainers addition. The ruff/mypy and mintkey-models issues should be addressed in a dedicated session.

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with concrete file:line or command)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted (or "none")
