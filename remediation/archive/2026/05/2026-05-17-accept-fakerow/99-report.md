# accept-fakerow — Closing Report

**Session:** `2026-05-17-accept-fakerow`
**Status:** CLOSED
**Closed by:** IMPLEMENTER ACCEPT-FIX

---

## Summary

`_FakeRow` in `tests/acceptance/test_multitenant_smoke.py` was missing the
`current_key_version` attribute. Production code `_service_row_to_dict`
(services.py:250) accesses it unconditionally. Added `self.current_key_version = 1`
to `_FakeRow.__init__`, matching the DB column default defined in
`admin-api/db/changelog/004-services.yaml` (INTEGER DEFAULT 1 NOT NULL). No
production code was changed. All 4 multitenant smoke tests now pass; full
acceptance suite (185 tests) passes with zero new failures.

---

## Verification commands and exit codes

```
cd admin-api && uv run pytest ../tests/acceptance/test_multitenant_smoke.py -v --tb=short
exit code: 0  (4 passed in 0.28s)

cd admin-api && uv run pytest ../tests/acceptance/ --ignore=../tests/acceptance/test_mock_backend_registered.py --tb=line
exit code: 0  (185 passed, 65 skipped in 24.01s)
```

Note: `test_mock_backend_registered.py` excluded — pre-existing import failure
(`ModuleNotFoundError: No module named 'tenacity'` in seed-job/main.py), unrelated
to this change and present on main before this branch.

---

## Chunks completed

| Chunk | Commit | Reviewer verdict | Rounds |
|---|---|---|---|
| C-1: scaffold + intake | 5415cca | PASS | 1 |
| C-2: fix _FakeRow | f1a2625 | PASS | 1 |

---

## DoD checklist — final state

- [x] `test_two_tenants_cant_see_each_others_services` passes — verified via pytest
- [x] Full acceptance suite (minus pre-existing broken import) passes — verified via pytest
- [x] No production code changed
- [x] No other tests modified
- [x] No ADRs modified
- [x] No `Co-Authored-By` trailer in any new commit
- [x] No `--no-verify` used

---

## Residual risks / deferred items

`test_mock_backend_registered.py` fails to import due to missing `tenacity`
dependency in `seed-job/`. Pre-existing on main; not in scope for this session.

---

## Escalation resolutions

None.

---

## Lessons learned / notes for next session

When a new column is added to a DB table (or a new field is added to
`_service_row_to_dict`), the corresponding `_FakeRow` test helper must be
updated in lockstep. Consider adding a dataclass or NamedTuple for `_FakeRow`
to get attribute-completeness checking at construction time.
