# Issue Intake — accept-fakerow-2026-05-17

## Problem statement (required)

`_FakeRow` in `tests/acceptance/test_multitenant_smoke.py::test_two_tenants_cant_see_each_others_services` is missing the `current_key_version` attribute. Production code `_service_row_to_dict` (admin-api/src/admin_api/api/services.py:250) accesses `row.current_key_version` unconditionally, causing `AttributeError: '_FakeRow' object has no attribute 'current_key_version'` when the test exercises the services endpoint.

## User-visible symptom (required)

CI failure:
```
FAILED tests/acceptance/test_multitenant_smoke.py::test_two_tenants_cant_see_each_others_services
E   AttributeError: '_FakeRow' object has no attribute 'current_key_version'
```

## Expected behavior (required)

Test should pass. `_FakeRow` should carry `current_key_version` matching the DB schema default (1), so `_service_row_to_dict` can serialize it cleanly.

## Evidence (required)

- `tests/acceptance/test_multitenant_smoke.py:229-243` — `_FakeRow.__init__` does not set `current_key_version`
- `admin-api/src/admin_api/api/services.py:250` — `"current_key_version": int(row.current_key_version or 0)` — unconditional attribute access
- `admin-api/db/changelog/004-services.yaml:62-66` — column `current_key_version INTEGER DEFAULT 1 NOT NULL`

## Scope (required)

`tests/acceptance/test_multitenant_smoke.py` — add `self.current_key_version = 1` to `_FakeRow.__init__` only.

## Out of scope (required)

Production code (no change needed — prod correctly accesses the field). Other tests. ADRs.

## Risk level (required)

CI (test helper desync with schema).

## Verification target (required)

```
cd admin-api && uv run pytest ../tests/acceptance/test_multitenant_smoke.py -v --tb=short
```
All 4 tests pass.

## Owner decisions needed (if any)

None. DB default is `1`; that is the correct test-fixture default.
