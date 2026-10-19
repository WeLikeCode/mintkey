# Verification: openspec:fix-logout-session: FAIL (round 1)

traceability: not checked (an earlier step failed)

- Base: `26caa837b78f8dea782089c6bf7d7dfd6ebd2937`
- Head: `984e47f2841c5fc50294cfea34768b0012e17072`
- Implementer profiles: deepseek, glm
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.4 | base staging@26caa837b7 contained |
| 1 | integrity | ok | 0.5 | 7 sub-checks; scope: 33 changed file(s) |
| 2 | build | failed | 4.5 | `sh .l4/gates/lint-go.sh` failed: exit code 1 |
| 3 | tests | not_run | 0.0 | an earlier step failed |
| 4 | traceability | not_run | 0.0 | an earlier step failed |
| 4a | audit sampling | not_run | 0.0 | an earlier step failed |
| 5 | ui test generation | not_run | 0.0 | an earlier step failed |
| 6 | quality | not_run | 0.0 | an earlier step failed |
| 8 | s1 judge | not_run | 0.0 | an earlier step failed |
| 9 | judge | not_run | 0.0 | an earlier step failed |
| 10 | aggregation | ok | 0.0 | FAIL |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --directory apps/admin-api` | .l4-out/gates/r-20261019T1313Z-104d/505-setup.log |
| setup | pass | `uv sync --frozen --directory packages/python/mintkey-models` | .l4-out/gates/r-20261019T1313Z-104d/506-setup.log |
| setup | pass | `uv sync --frozen --directory apps/mcp-server` | .l4-out/gates/r-20261019T1313Z-104d/507-setup.log |
| setup | pass | `sh .l4/gates/setup-go.sh` | .l4-out/gates/r-20261019T1313Z-104d/508-setup.log |
| setup | pass | `pnpm --dir apps/admin-ui install --frozen-lockfile` | .l4-out/gates/r-20261019T1313Z-104d/509-setup.log |
| lint | pass | `uv run --frozen --directory apps/admin-api ruff check src/` | .l4-out/gates/r-20261019T1313Z-104d/510-lint.log |
| lint | pass | `uv run --frozen --directory packages/python/mintkey-models ruff check mintkey_models/` | .l4-out/gates/r-20261019T1313Z-104d/511-lint.log |
| lint | pass | `uv run --frozen --directory apps/mcp-server ruff check src/` | .l4-out/gates/r-20261019T1313Z-104d/512-lint.log |
| lint | fail | `sh .l4/gates/lint-go.sh` | .l4-out/gates/r-20261019T1313Z-104d/513-lint.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 5 test file(s) compared with the base |
| red-green freeze | ok | 9 task(s): red and green compared |
| test path freeze | ok | 9 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | skipped | not checked: python only; changed files outside it: apps/admin-ui/e2e/tests/21-logout-replay.spec.ts, apps/admin-ui/e2e/tests/21-logout-session.spec.ts, apps/admin-ui/src/components/app/LoggedIn.tsx, apps/admin-ui/src/components/index.ts, apps/admin-ui/src/index.ts (+6 more) |
| tdd history | ok | 9 task(s); red tests passing at head: step 3 |

## Evidence

### Needs attention

Nothing needs attention.

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `apps/admin-api/src/admin_api/api/auth.py` | admin-api | relevant | named in the spec |
| `apps/admin-api/src/admin_api/auth/sessions.py` | admin-api | relevant | named in the spec |
| `apps/admin-ui/e2e/tests/21-logout-replay.spec.ts` |  | relevant | new test file |
| `apps/admin-ui/e2e/tests/21-logout-session.spec.ts` |  | relevant | named in the spec |
| `apps/admin-ui/src/components/app/LoggedIn.tsx` | admin-ui | relevant | named in the spec |
| `apps/admin-ui/src/components/index.ts` | admin-ui | relevant | named in the spec |
| `apps/admin-ui/src/index.ts` | admin-ui | relevant | named in the spec |
| `apps/admin-ui/src/routes/logout.ts` | admin-ui | relevant | named in the spec |
| `apps/admin-ui/tests/LoggedIn.render.test.tsx` |  | relevant | new test file |
| `apps/admin-ui/tests/test_logout_guard.test.ts` |  | relevant | new test file |
| `apps/admin-ui/tests/test_logout_router.test.ts` |  | relevant | new test file |
| `apps/admin-ui/tests/test_logout_session.test.ts` |  | relevant | new test file |
| `apps/admin-ui/tests/test_logout_wiring.test.ts` |  | relevant | new test file |
| `docs/architecture/contracts/rest/openapi.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1246Z-38f3.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1247Z-1460.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1248Z-cdea.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1250Z-2273.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1251Z-db38.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1253Z-94f0.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1255Z-b911.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1301Z-6147.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1303Z-8159.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1304Z-1c90.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1305Z-6c11.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1307Z-e8b3.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/.l4/ledger/r-20261019T1313Z-104d.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-logout-session/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `tests/unit/admin_api/conftest.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_delete_session.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_logout_session.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_logout_store_failure.py` |  | relevant | new test file |
| `tests/unit/admin_api/test_whoami_eviction.py` |  | relevant | new test file |

### Changed functions

Diff coverage not run.

### Tests

Tests-ran check not run.

## Criteria

None judged.

## Findings

- [blocker, deterministic] lint gate failed: `sh .l4/gates/lint-go.sh` failed: exit code 1 Log: `.l4-out/gates/r-20261019T1313Z-104d/513-lint.log`.

## Fix unit

Fix unit 1 is created for these tasks:
- F-5964e3de lint gate failed

## New tests (red then green, `task.red_ok` in the ledger)

- `tests.unit.admin_api.test_delete_session::test_delete_session_deletes_row_and_returns_true` (task 1.1): not in the report
- `tests.unit.admin_api.test_delete_session::test_delete_session_non_uuid_opens_no_database` (task 1.1): not in the report
- `tests.unit.admin_api.test_delete_session::test_delete_session_returns_false_when_no_row` (task 1.1): not in the report
- `tests.unit.admin_api.test_logout_session::test_concurrent_logouts_with_same_cookie` (task 3.1): not in the report
- `tests.unit.admin_api.test_logout_session::test_logout_clears_both_cookies` (task 3.1): not in the report
- `tests.unit.admin_api.test_logout_session::test_logout_of_expired_session_deletes_by_token` (task 3.1): not in the report
- `tests.unit.admin_api.test_logout_session::test_logout_twice_with_same_cookie` (task 3.1): not in the report
- `tests.unit.admin_api.test_logout_session::test_logout_with_non_uuid_cookie_clears_both_cookies` (task 3.1): not in the report
- `tests.unit.admin_api.test_logout_session::test_logout_without_session_cookie_does_not_delete_or_evict` (task 3.1): not in the report
- `tests.unit.admin_api.test_logout_session::test_old_cookie_refused_after_logout_inside_cache_window` (task 3.1): not in the report
- `tests.unit.admin_api.test_logout_store_failure::test_delete_session_failure_answers_503_and_still_evicts` (task 3.2): not in the report
- `tests.unit.admin_api.test_logout_store_failure::test_openapi_logout_lists_204_and_503` (task 3.2): not in the report
- `tests.unit.admin_api.test_whoami_eviction::test_evicting_cached_token_removes_only_it` (task 2.1): not in the report
- `tests.unit.admin_api.test_whoami_eviction::test_evicting_uncached_token_keeps_other_entries` (task 2.1): not in the report
- `tests.unit.admin_api.test_whoami_eviction::test_lookup_in_flight_during_logout_is_not_cached` (task 2.1): not in the report
- `tests/LoggedIn.render.test.tsx::LoggedIn override — C-5f6816da no CSRF token > C-5f6816da: renders and submits an empty _csrf when session and cookie have no token` (task 5.1): not in the report
- `tests/LoggedIn.render.test.tsx::LoggedIn override — C-6d2b5e54 top bar form > C-6d2b5e54: shows the email and a POST form with hidden _csrf and logout button, without a logout link` (task 5.1): not in the report
- `tests/LoggedIn.render.test.tsx::LoggedIn override — C-d34b4cb5 current CSRF cookie on submit > C-d34b4cb5: submit replaces the rendered _csrf with the current csrf_token cookie` (task 5.1): not in the report
- `tests/test_logout_guard.test.ts::logoutGuard — C-de8201d5 wrong token > C-de8201d5: refuses a token of another length` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::logoutGuard — C-de8201d5 wrong token > C-de8201d5: refuses a token of the same length that differs` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::logoutGuard — C-e629437b nothing to log out > C-e629437b: redirects to login when the session has no adminUser and there is no cookie` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::logoutGuard — C-e629437b nothing to log out > C-e629437b: redirects to login when there is no session object and no cookie` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::logoutGuard — C-f475d740 missing token > C-f475d740: refuses a request without the _csrf field` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::logoutGuard — C-f475d740 missing token > C-f475d740: refuses a request without the csrf_token cookie` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::logoutGuard — valid token > calls next() once when _csrf equals the csrf_token cookie` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::readCookie > C-de8201d5: does not percent-decode the value` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::readCookie > C-de8201d5: keeps every '=' after the first one in the value` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::readCookie > C-de8201d5: returns the first occurrence of a repeated name` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::readCookie > C-de8201d5: trims surrounding spaces from the value` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::readCookie > C-f475d740: matches the exact cookie name (xcsrf_token is not csrf_token)` (task 4.1): not in the report
- `tests/test_logout_guard.test.ts::readCookie > C-f475d740: returns undefined for a missing header, missing name or empty value` (task 4.1): not in the report
- `tests/test_logout_router.test.ts::GET /admin/logout — C-12db9b82 without a CSRF cookie > C-12db9b82: renders the same form with an empty _csrf value and changes nothing` (task 4.3): not in the report
- `tests/test_logout_router.test.ts::GET /admin/logout — C-4749db35 renders a confirmation form > C-4749db35: renders an escaped _csrf form without side effects` (task 4.3): not in the report
- `tests/test_logout_router.test.ts::GET /admin/logout — C-f7e06575 without a session > C-f7e06575: redirects to /admin/login when there is no session` (task 4.3): not in the report
- `tests/test_logout_router.test.ts::createLogoutRouter — C-6a1cff5f serves both methods behind the limiter > C-6a1cff5f: the limiter runs for GET and both POSTs, and each answer is right` (task 4.3): not in the report
- `tests/test_logout_session.test.ts::createLogoutHandler — C-3cb4c380 a request with no session object > C-3cb4c380: calls no admin-api, clears only the operator cookies and redirects` (task 4.2): not in the report
- `tests/test_logout_session.test.ts::createLogoutHandler — C-5dc3374d admin-api is unreachable or refuses > C-5dc3374d: destroys the AdminJS session and clears the cookies when admin-api answers 503` (task 4.2): not in the report
- `tests/test_logout_session.test.ts::createLogoutHandler — C-5dc3374d admin-api is unreachable or refuses > C-5dc3374d: destroys the AdminJS session and clears the cookies when fetch rejects` (task 4.2): not in the report
- `tests/test_logout_session.test.ts::createLogoutHandler — C-a4f02538 the session store fails to destroy > C-a4f02538: still clears the three cookies and redirects when destroy reports an error` (task 4.2): not in the report
- `tests/test_logout_session.test.ts::createLogoutHandler — C-a6ef632a a full logout > C-a6ef632a: calls admin-api, destroys the AdminJS session, clears all three cookies and redirects` (task 4.2): not in the report
- `tests/test_logout_session.test.ts::createLogoutHandler — C-e0bc4928 two concurrent logouts > C-e0bc4928: both redirect, both clear adminjs.sid and the store ends empty` (task 4.2): not in the report
- `tests/test_logout_wiring.test.ts::components/index.ts — C-7ab935e2 LoggedIn override registration > C-7ab935e2: registers the LoggedIn override with ./app/LoggedIn` (task 5.1): not in the report
- `tests/test_logout_wiring.test.ts::src/index.ts — C-234b2839 mounts the logout router > C-234b2839: mounts createLogoutRouter before requireSession and keeps no GET logout handler` (task 5.2): not in the report

## Guard events

- guard.violation: apps/admin-api/.hypothesis/.gitignore
- guard.violation: apps/admin-api/.hypothesis/constants/005cb2d0b75b9414
- guard.violation: apps/admin-api/.hypothesis/constants/036533ff311156f8
- guard.violation: apps/admin-api/.hypothesis/constants/0442a4f9ff664719
- guard.violation: apps/admin-api/.hypothesis/constants/04b7d9b483ff416a
- guard.violation: apps/admin-api/.hypothesis/constants/04e20610335c1efd
- guard.violation: apps/admin-api/.hypothesis/constants/04ed1b57880398d1
- guard.violation: apps/admin-api/.hypothesis/constants/0d3a9017498e3f12
- guard.violation: apps/admin-api/.hypothesis/constants/14ef6ba5c8afc3e7
- guard.violation: apps/admin-api/.hypothesis/constants/19c615b0a90adb19
- guard.violation: apps/admin-api/.hypothesis/constants/1b881106c94d3162
- guard.violation: apps/admin-api/.hypothesis/constants/1b8d833b1bb06b3c
- guard.violation: apps/admin-api/.hypothesis/constants/1d6aa44528bb5e5b
- guard.violation: apps/admin-api/.hypothesis/constants/2ba4c0b09b43d140
- guard.violation: apps/admin-api/.hypothesis/constants/334e2cd35334a535
- guard.violation: apps/admin-api/.hypothesis/constants/33a8e71f1cf846ad
- guard.violation: apps/admin-api/.hypothesis/constants/3407634a43eb80e3
- guard.violation: apps/admin-api/.hypothesis/constants/3f1fcc632dadb1fb
- guard.violation: apps/admin-api/.hypothesis/constants/41e441930e6c3f19
- guard.violation: apps/admin-api/.hypothesis/constants/430558def4d4d762
- guard.violation: apps/admin-api/.hypothesis/constants/45b43bc4cd7408d6
- guard.violation: apps/admin-api/.hypothesis/constants/45e7300cb0b8c359
- guard.violation: apps/admin-api/.hypothesis/constants/477c89f2694a04a7
- guard.violation: apps/admin-api/.hypothesis/constants/47ecc356f6e12ff0
- guard.violation: apps/admin-api/.hypothesis/constants/4848be6476209b5a
- guard.violation: apps/admin-api/.hypothesis/constants/4ad84b7fa02c7c08
- guard.violation: apps/admin-api/.hypothesis/constants/59db66ad4bbd29cb
- guard.violation: apps/admin-api/.hypothesis/constants/675eaafa7040a6ef
- guard.violation: apps/admin-api/.hypothesis/constants/67b0a8ccf18bf5d2
- guard.violation: apps/admin-api/.hypothesis/constants/68c2001795193bfb
- guard.violation: apps/admin-api/.hypothesis/constants/6e823fefe683e026
- guard.violation: apps/admin-api/.hypothesis/constants/6fb98dde3112dfad
- guard.violation: apps/admin-api/.hypothesis/constants/783b996bd7418477
- guard.violation: apps/admin-api/.hypothesis/constants/7920a2051ef23688
- guard.violation: apps/admin-api/.hypothesis/constants/7e64b0f62de0d79e
- guard.violation: apps/admin-api/.hypothesis/constants/82db23fd656472a4
- guard.violation: apps/admin-api/.hypothesis/constants/894a586d5f2ed4bf
- guard.violation: apps/admin-api/.hypothesis/constants/8993f21eb5fba8fd
- guard.violation: apps/admin-api/.hypothesis/constants/8d8ee59068d4113f
- guard.violation: apps/admin-api/.hypothesis/constants/91b1032f0cb7da5b
- guard.violation: apps/admin-api/.hypothesis/constants/972dd3a4af379804
- guard.violation: apps/admin-api/.hypothesis/constants/9845bd703d94aabc
- guard.violation: apps/admin-api/.hypothesis/constants/a39392c1d25db545
- guard.violation: apps/admin-api/.hypothesis/constants/a4a4bfc444a036a6
- guard.violation: apps/admin-api/.hypothesis/constants/a939faedc6eb633e
- guard.violation: apps/admin-api/.hypothesis/constants/b06d435bdec50977
- guard.violation: apps/admin-api/.hypothesis/constants/b68093d4142c13cf
- guard.violation: apps/admin-api/.hypothesis/constants/bcea3d9f0ea3aad2
- guard.violation: apps/admin-api/.hypothesis/constants/c50e4315a75123bc
- guard.violation: apps/admin-api/.hypothesis/constants/c59c3c3d0ab38a43
- guard.violation: apps/admin-api/.hypothesis/constants/c5e393b944f93e17
- guard.violation: apps/admin-api/.hypothesis/constants/c854cc07e76b8294
- guard.violation: apps/admin-api/.hypothesis/constants/cc354972bffdf65c
- guard.violation: apps/admin-api/.hypothesis/constants/cf52bfc4d6d4552d
- guard.violation: apps/admin-api/.hypothesis/constants/d03f30b52f4b5e99
- guard.violation: apps/admin-api/.hypothesis/constants/d07acab8241772bc
- guard.violation: apps/admin-api/.hypothesis/constants/d51cb5d1491a2e75
- guard.violation: apps/admin-api/.hypothesis/constants/da39a3ee5e6b4b0d
- guard.violation: apps/admin-api/.hypothesis/constants/e155377647d3a41f
- guard.violation: apps/admin-api/.hypothesis/constants/e22ce368906cab3e
- guard.violation: apps/admin-api/.hypothesis/constants/ef119a92d73a4038
- guard.violation: apps/admin-api/.hypothesis/constants/ef9d4f4ea0f23d80
- guard.violation: apps/admin-api/.hypothesis/constants/f1b88638987c5dc7
- guard.violation: apps/admin-api/.hypothesis/unicode_data/15.0.0/charmap.json.gz
- guard.violation: apps/admin-api/.hypothesis/unicode_data/15.0.0/codec-v2-utf-8.json.gz
- guard.violation: apps/admin-api/.hypothesis/constants/005cb2d0b75b9414
- guard.violation: apps/admin-api/.hypothesis/constants/036533ff311156f8
- guard.violation: apps/admin-api/.hypothesis/constants/0442a4f9ff664719
- guard.violation: apps/admin-api/.hypothesis/constants/04b7d9b483ff416a
- guard.violation: apps/admin-api/.hypothesis/constants/04e20610335c1efd
- guard.violation: apps/admin-api/.hypothesis/constants/04ed1b57880398d1
- guard.violation: apps/admin-api/.hypothesis/constants/0d3a9017498e3f12
- guard.violation: apps/admin-api/.hypothesis/constants/14ef6ba5c8afc3e7
- guard.violation: apps/admin-api/.hypothesis/constants/19c615b0a90adb19
- guard.violation: apps/admin-api/.hypothesis/constants/1b881106c94d3162
- guard.violation: apps/admin-api/.hypothesis/constants/1b8d833b1bb06b3c
- guard.violation: apps/admin-api/.hypothesis/constants/1d6aa44528bb5e5b
- guard.violation: apps/admin-api/.hypothesis/constants/2ba4c0b09b43d140
- guard.violation: apps/admin-api/.hypothesis/constants/334e2cd35334a535
- guard.violation: apps/admin-api/.hypothesis/constants/3407634a43eb80e3
- guard.violation: apps/admin-api/.hypothesis/constants/3f1fcc632dadb1fb
- guard.violation: apps/admin-api/.hypothesis/constants/41e441930e6c3f19
- guard.violation: apps/admin-api/.hypothesis/constants/430558def4d4d762
- guard.violation: apps/admin-api/.hypothesis/constants/45b43bc4cd7408d6
- guard.violation: apps/admin-api/.hypothesis/constants/45e7300cb0b8c359
- guard.violation: apps/admin-api/.hypothesis/constants/477c89f2694a04a7
- guard.violation: apps/admin-api/.hypothesis/constants/47ecc356f6e12ff0
- guard.violation: apps/admin-api/.hypothesis/constants/4848be6476209b5a
- guard.violation: apps/admin-api/.hypothesis/constants/4ad84b7fa02c7c08
- guard.violation: apps/admin-api/.hypothesis/constants/59db66ad4bbd29cb
- guard.violation: apps/admin-api/.hypothesis/constants/675eaafa7040a6ef
- guard.violation: apps/admin-api/.hypothesis/constants/67b0a8ccf18bf5d2
- guard.violation: apps/admin-api/.hypothesis/constants/68c2001795193bfb
- guard.violation: apps/admin-api/.hypothesis/constants/6e823fefe683e026
- guard.violation: apps/admin-api/.hypothesis/constants/6fb98dde3112dfad
- guard.violation: apps/admin-api/.hypothesis/constants/7920a2051ef23688
- guard.violation: apps/admin-api/.hypothesis/constants/7e64b0f62de0d79e
- guard.violation: apps/admin-api/.hypothesis/constants/82db23fd656472a4
- guard.violation: apps/admin-api/.hypothesis/constants/894a586d5f2ed4bf
- guard.violation: apps/admin-api/.hypothesis/constants/8993f21eb5fba8fd
- guard.violation: apps/admin-api/.hypothesis/constants/8d8ee59068d4113f
- guard.violation: apps/admin-api/.hypothesis/constants/91b1032f0cb7da5b
- guard.violation: apps/admin-api/.hypothesis/constants/972dd3a4af379804
- guard.violation: apps/admin-api/.hypothesis/constants/9845bd703d94aabc
- guard.violation: apps/admin-api/.hypothesis/constants/9bff7cb592d55a76
- guard.violation: apps/admin-api/.hypothesis/constants/a39392c1d25db545
- guard.violation: apps/admin-api/.hypothesis/constants/a4a4bfc444a036a6
- guard.violation: apps/admin-api/.hypothesis/constants/a939faedc6eb633e
- guard.violation: apps/admin-api/.hypothesis/constants/b06d435bdec50977
- guard.violation: apps/admin-api/.hypothesis/constants/b68093d4142c13cf
- guard.violation: apps/admin-api/.hypothesis/constants/bcea3d9f0ea3aad2
- guard.violation: apps/admin-api/.hypothesis/constants/c50e4315a75123bc
- guard.violation: apps/admin-api/.hypothesis/constants/c59c3c3d0ab38a43
- guard.violation: apps/admin-api/.hypothesis/constants/c5e393b944f93e17
- guard.violation: apps/admin-api/.hypothesis/constants/c854cc07e76b8294
- guard.violation: apps/admin-api/.hypothesis/constants/cc354972bffdf65c
- guard.violation: apps/admin-api/.hypothesis/constants/cf52bfc4d6d4552d
- guard.violation: apps/admin-api/.hypothesis/constants/d03f30b52f4b5e99
- guard.violation: apps/admin-api/.hypothesis/constants/d07acab8241772bc
- guard.violation: apps/admin-api/.hypothesis/constants/d51cb5d1491a2e75
- guard.violation: apps/admin-api/.hypothesis/constants/da39a3ee5e6b4b0d
- guard.violation: apps/admin-api/.hypothesis/constants/e155377647d3a41f
- guard.violation: apps/admin-api/.hypothesis/constants/e22ce368906cab3e
- guard.violation: apps/admin-api/.hypothesis/constants/ef119a92d73a4038
- guard.violation: apps/admin-api/.hypothesis/constants/ef9d4f4ea0f23d80
- guard.violation: apps/admin-api/.hypothesis/constants/f1b88638987c5dc7
- guard.violation: apps/admin-api/.hypothesis/unicode_data/15.0.0/charmap.json.gz
- guard.violation: apps/admin-api/.hypothesis/unicode_data/15.0.0/codec-v2-utf-8.json.gz
- guard.violation: apps/admin-ui/src/routes/logout.ts
- guard.violation: apps/admin-ui/src/routes/logout.ts
- guard.violation: apps/admin-ui/src/components/app/LoggedIn.tsx
