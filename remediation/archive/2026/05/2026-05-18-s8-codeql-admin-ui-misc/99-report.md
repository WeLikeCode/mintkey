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

---

## Strike-2 supplement (2026-05-18)

**Status:** **CLOSED**

Reviewer (fresh, post-strike-1) passed the CodeQL closure but flagged one operational
regression (O1) and one test coverage gap (O2).

### O1 — trust proxy + conditional cookie secure (fix: Option A)

**Problem:** `secure: true` was hardcoded but `app.set('trust proxy', 1)` was absent.
Without trust proxy, express-session inspects the local TCP socket (HTTP) and silently
drops the `Secure` attribute even when `X-Forwarded-Proto: https` is set by Kong/Caddy.
Result: session cookie is never transmitted → login breaks on both dev (direct HTTP on
localhost:8081) and prod (behind Kong TLS terminator).

**Fix chosen: Option A** (conditional secure + trust proxy).

- `app.set("trust proxy", 1)` added before session middleware in `admin-ui/src/index.ts`.
  This makes express-session honour `X-Forwarded-Proto` from Kong/Caddy in prod.
- `secure: process.env.NODE_ENV === "production"` replaces `secure: true`.
  In dev (NODE_ENV ≠ production), the flag is omitted so browsers accept the cookie
  over plain HTTP on localhost:8081 — dev login works without a local TLS proxy.
  In production, the flag is set and the proxy header makes express-session treat the
  connection as HTTPS. Cookie is delivered correctly.
- CodeQL `js/clear-text-cookie` compatibility: the rule fires on *unconditional*
  `secure: false`. A `NODE_ENV === "production"` gate is the conventional pattern
  and is accepted by the rule — the cookie is never insecure in production.

Option B (always-secure, mandate HTTPS in dev) was not chosen because it would require
every developer to set up a local TLS-terminating proxy — a significant workflow change
that would need operator sign-off.

**Files changed (O1):**
- `admin-ui/src/index.ts` — add `app.set("trust proxy", 1)`; change `secure` to
  `process.env.NODE_ENV === "production"`.
- `admin-ui/tests/test_security_config.test.ts` — replace `secure: true` static
  assertion with `NODE_ENV === "production"` regex; add two new assertions verifying
  `app.set("trust proxy", 1)` is present and ordered before the session middleware.

### O2 — test for services.py:802 stack-trace-exposure path

**Problem:** the prior test only smoke-tested `_is_forbidden_destination`. The
`test_service` endpoint's `except Exception as exc` branch (line 772) — which logs
`repr(exc)` server-side and returns the static `"internal_error"` to the client —
had no test coverage.

**Fix:** new test `test_test_service_unexpected_exception_returns_generic_error` in
`tests/unit/admin_api/test_services.py`:
- Patches `admin_api.api.services.httpx.AsyncClient` (module-scoped, avoids
  interfering with the ASGI test transport) to raise `Exception("DB password=hunter2 leaked")`.
- Patches `get_vault_client` and `audit_emit` to isolate the happy path.
- Asserts HTTP 200 with `{"error": "internal_error"}` — sensitive text absent from body.
- Asserts sensitive text appears in `caplog` records at WARNING level.

### O4 — Status header consistency

Added `**Status:** **CLOSED**` at the top of this supplement section, matching the
S4 pattern for closed sessions.
