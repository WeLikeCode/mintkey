# Closing Report — S8 codeql-admin-ui-misc

**Session:** `2026-05-18-s8-codeql-admin-ui-misc`
**Branch:** `fix/s8-codeql-admin-ui-misc-2026-05-18`
**Closed:** 2026-05-18

## Alerts closed (4/4)

| Alert | File | Fix |
|-------|------|-----|
| `js/missing-rate-limiting` (high) | `admin-ui/src/index.ts:203` | Added `express-rate-limit@7.5.0`; applied `loginRateLimit` (20 req/15 min/IP) to `GET /admin/login` and `POST /auth/internal-login-proxy` |
| `js/clear-text-cookie` (medium) | `admin-ui/src/index.ts:181` | Changed session cookie from `secure:false, sameSite:"lax"` to `secure:true, sameSite:"strict"` |
| `py/stack-trace-exposure` (medium) | `admin-api/.../agents.py:641` | Replaced `str(e)` (included user input) with static title `"expires_in must be one of 30d/90d/180d/365d or empty string"`; added `logger.warning` for server-side detail |
| `py/stack-trace-exposure` (medium) | `admin-api/.../services.py:802` | Replaced `str(exc)` with `"internal_error"`; added `logger.warning` with `repr(exc)` for server-side detail; also sanitized audit payload error field (line 792) |

## Files changed

- `admin-ui/src/index.ts` — import rateLimit, add loginRateLimit middleware, fix cookie flags
- `admin-ui/package.json` — `express-rate-limit@7.5.0` in dependencies
- `admin-ui/pnpm-lock.yaml` — lockfile update
- `admin-ui/tests/test_security_config.test.ts` — new: security config static tests
- `admin-api/src/admin_api/api/agents.py` — add logging import + logger, fix error title at line 641
- `admin-api/src/admin_api/api/services.py` — fix error at lines 792 + 802
- `tests/unit/admin_api/test_agents.py` — new: rotate_key stack-trace exposure test
- `tests/unit/admin_api/test_services.py` — new: _is_forbidden_destination smoke test
- `team/remediation/2026-05-18-s8-codeql-admin-ui-misc/ISSUE_INTAKE.md`
- `team/remediation/2026-05-18-s8-codeql-admin-ui-misc/99-report.md` (this file)

## Commits

- `32150c6` docs(session): scaffold S8 codeql-admin-ui-misc session
- `0373c39` fix(admin-ui): add rate-limiting to login routes and harden session cookie
- `b7582cb` fix(admin-api): replace stack-trace exposure with generic error messages

## Verification

```
# admin-ui: pnpm exec tsc --noEmit
Pre-existing TS errors in resources/ (not introduced by S8). index.ts clean of new errors.

# admin-ui: pnpm test
Test Files  1 failed | 27 passed (28)   ← pre-existing test_permissions.test.ts failure
Tests  1 failed | 366 passed (367)

# admin-api: python -m pytest tests/unit/admin_api/ -x -q
140 passed, 58 warnings

# git log origin/main..HEAD
b7582cb fix(admin-api): replace stack-trace exposure with generic error messages
0373c39 fix(admin-ui): add rate-limiting to login routes and harden session cookie
32150c6 docs(session): scaffold S8 codeql-admin-ui-misc session
```

## Coordination note (S1)

S1 also edits `admin-api/src/admin_api/api/services.py` around line 537 (SSRF fix). S8 only touched the `except Exception as exc` block at lines 772–802 (test_service unexpected error). No conflict at current branch tip. If S1 lands on main before S8's PR is merged, a trivial rebase will be required.

## Open questions

None.
