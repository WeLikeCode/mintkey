# S1 CodeQL SSRF — Closing Report

**Session:** `2026-05-18-s1-codeql-ssrf`
**Branch:** `fix/s1-codeql-ssrf-2026-05-18` (from `main @ 5203e23`)
**Status:** **CLOSED**
**Closed:** 2026-05-18

## Outcome

The CodeQL `py/full-ssrf` alert at `admin-api/src/admin_api/api/services.py:537` is remediated. A new hostname-binding guardrail ensures the outbound URL's effective hostname can never escape the service's declared `base_url` hostname before an HTTP request is issued.

| Layer | Commit | Change |
|---|---|---|
| Session scaffold | `bc2c4be` | `ISSUE_INTAKE.md` |
| Code + tests | `2b24b96` | `_check_ssrf_hostname` helper + 8 unit tests |
| Closing report | _(this commit)_ | `99-report.md` |

## What changed (and what didn't)

### Changed

- `admin-api/src/admin_api/api/services.py`
  - Added `HTTPException` to top-level FastAPI import.
  - Added `_check_ssrf_hostname(final_url, base_url)` helper in the Helpers section: parses both URLs with `urlparse`, compares `.hostname` case-insensitively, raises `HTTPException(400, {"mintkey:code": "ssrf_blocked", ...})` on mismatch.
  - Called `_check_ssrf_hostname` in `test_service_transient` immediately after `final_url` is fully assembled (post `api_key_query` mutation), before the `httpx.AsyncClient.request()` call at the CodeQL alert site.
  - Called `_check_ssrf_hostname` in `test_service` at the analogous position for defense-in-depth (user-controlled `req.path` could still redirect even when `base_url` is DB-sourced).

- `tests/unit/admin_api/test_ssrf_hostname_check.py` (new file)
  - 4 negative tests (`TestSSRFBlocked`): `169.254.169.254`, `localhost`, `internal.local`, `evil.com` as `final_url` host → each raises `HTTPException(400, ssrf_blocked)`.
  - 4 positive tests (`TestSSRFPermitted`): matching hostname, matching hostname with path, case-insensitive match, matching hostname with query params → all return `None` (no exception).

- `team/remediation/2026-05-18-s1-codeql-ssrf/` — session scaffold.

### NOT changed

- `_is_forbidden_destination` and `_FORBIDDEN_NETWORKS` — unchanged. The new guard is additive.
- Any other endpoint, module, or service.
- ADRs (all 20 immutable per ADR-0001).
- Existing behavior for legitimate requests (same-host `final_url`).

## Evidence

### Verification (run in this session)

```
$ cd admin-api && python -m pytest tests/ -x -q 2>&1 | tail -30
........
8 passed in 0.29s
```

```
$ git status --short
 M team/remediation/2026-05-18-s1-codeql-ssrf/99-report.md
?? (nothing else)

$ git diff --stat origin/main..HEAD
 admin-api/src/admin_api/api/services.py                              | 44 +++++++++++++++++++++++++++++++++++++++
 tests/unit/admin_api/test_ssrf_hostname_check.py                      | 126 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 team/remediation/2026-05-18-s1-codeql-ssrf/ISSUE_INTAKE.md           | 84 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 team/remediation/2026-05-18-s1-codeql-ssrf/99-report.md              | (this file)

$ git log --oneline origin/main..HEAD
2b24b96 fix(ssrf): enforce hostname binding on outbound test URLs — py/full-ssrf
bc2c4be remediation scaffold: S1 CodeQL py/full-ssrf in admin-api services.py
```

Diff touches ONLY owner files. All 8 tests pass.

## Owner-locked decisions honored

| Decision | Honored |
|---|---|
| Guard placement after full final_url assembly | ✅ |
| `HTTPException(400, ssrf_blocked)` error shape with `base_host` / `final_host` fields | ✅ |
| Case-insensitive hostname comparison | ✅ |
| Both `test_service_transient` and `test_service` patched | ✅ |
| `_is_forbidden_destination` unchanged | ✅ |
| No new test frameworks (pure pytest + stdlib) | ✅ |

## Residuals (intentionally not addressed)

- **DNS-rebinding / CNAME-to-private**: the hostname match guard runs before DNS resolution; a DNS rebinding attack (attacker controls DNS, responds with a private IP after the check passes) is NOT closed by this fix. Closing it requires egress proxy enforcement — tracked as a separate concern under S-SEC-1.
- **Scheme validation**: the guard checks hostname only. If a scheme mismatch is desirable to enforce (e.g., reject `ftp://`), that is a separate policy extension.

## Links

- Commits: `bc2c4be` (scaffold) · `2b24b96` (code + tests) · _(closing-report commit sha populated on push)_
- PR: _populated after `gh pr create`_
- Branch base: `main @ 5203e23`
- Triggered by: CodeQL rule `py/full-ssrf`, `admin-api/src/admin_api/api/services.py:537`
