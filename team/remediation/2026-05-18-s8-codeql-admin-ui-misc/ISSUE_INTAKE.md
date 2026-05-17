# Issue Intake — 2026-05-18-s8-codeql-admin-ui-misc

**Session:** `team/remediation/2026-05-18-s8-codeql-admin-ui-misc/`
**Branch:** `fix/s8-codeql-admin-ui-misc-2026-05-18` (from main @ `5203e23`)
**Reported:** 2026-05-18
**Reporter:** CodeQL campaign S8 — 4 alerts across admin-ui and admin-api edges

## Problem statement (required)

Four CodeQL alerts across two files require remediation:
1. `js/missing-rate-limiting` (high) — `admin-ui/src/index.ts:203`: `GET /admin/login` route has no rate-limiting middleware, enabling brute-force enumeration.
2. `js/clear-text-cookie` (medium) — `admin-ui/src/index.ts:181`: express-session cookie configured with `secure: false` and `sameSite: "lax"`, violating CWE-614.
3. `py/stack-trace-exposure` (medium) — `admin-api/.../agents.py:641`: `str(e)` from a `ValueError` (which includes user-supplied input) is returned directly in the HTTP response `title` field.
4. `py/stack-trace-exposure` (medium) — `admin-api/.../services.py:802`: `str(exc)` from an arbitrary external exception (httpx network error, etc.) is returned directly in the HTTP response `error` field.

## User-visible symptom (required)

- An attacker can enumerate the admin login page (or iterate break-glass credentials) without rate-limiting feedback.
- Session cookies transmitted over HTTP would not be protected by the `Secure` flag.
- Internal exception messages (potentially containing stack traces, internal addresses, or user input echoes) are visible in API responses.

## Expected behavior (required)

- `GET /admin/login` and `POST /auth/internal-login-proxy` are rate-limited to 20 req / 15 min / IP.
- Session cookie has `Secure=true`, `HttpOnly=true`, `SameSite=Strict`.
- On `invalid_expires_in` error in `agents.py`, return a static error message; log the detail server-side.
- On unexpected exception in `services.py` test-service endpoint, return `"internal_error"`; log the exception server-side.

## Evidence (required)

- `admin-ui/src/index.ts:181` — `secure: false, sameSite: "lax"` in express-session cookie options.
- `admin-ui/src/index.ts:203` — `app.get("/admin/login", ...)` with no rate-limit middleware.
- `admin-api/src/admin_api/api/agents.py:641` — `{"mintkey:code": "invalid_expires_in", "title": str(e)}` where `e` is a `ValueError` containing user-supplied `expires_in` value.
- `admin-api/src/admin_api/api/services.py:802` — `JSONResponse({"ok": False, "error": str(exc)})` where `exc` is an arbitrary external exception (httpx, network, etc.).

## Scope (required)

- `admin-ui/src/index.ts` — cookie flags, rate-limit import + middleware
- `admin-ui/package.json` + `admin-ui/pnpm-lock.yaml` — add `express-rate-limit@7.5.0`
- `admin-api/src/admin_api/api/agents.py` — add logging import, fix error title at line 641 only
- `admin-api/src/admin_api/api/services.py` — fix error at line 802 only (NOT line 537 area — that is S1's territory)
- `admin-ui/tests/test_security_config.test.ts` — new test file for A+B
- `tests/unit/admin_api/test_agents.py` — add rotate-key stack-trace test
- `tests/unit/admin_api/test_services.py` — add services stack-trace smoke test
- Session folder

## Out of scope (required)

- `admin-api/src/admin_api/api/services.py` line ~537 area (S1's SSRF fix)
- Any other files in the codebase
- Kong-level rate-limiting configuration (existing primary control; this is defense-in-depth)

## Risk level (required)

- **Security** (primary): closes CWE-614, CWE-307, CWE-209.
- **Behavior change**: `secure: true` on the session cookie means admin-ui must be served over HTTPS (or via TLS-terminating proxy) — already the case in production and local dev (Caddy/ngrok).
- **Operator UX**: login endpoint now rate-limited at 20 req/15 min; legitimate operators are unaffected.
- **API surface**: error message in `services.py` test-service changes from exception text to `"internal_error"` — callers should check `ok` field, not parse `error` text.

## Verification target (required)

```bash
cd /Users/alexandruiacobescu/gooseProjects/mintkey-s8-codeql-admin-ui-misc
# admin-ui
cd admin-ui && pnpm exec tsc --noEmit 2>&1 | tail -10 && pnpm test 2>&1 | tail -20 && cd ..
# admin-api
cd admin-api && python -m pytest tests/ -x -q 2>&1 | tail -25 && cd ..
git status --short
git diff --stat origin/main..HEAD
git log --oneline origin/main..HEAD
```

## Owner decisions noted

- `secure: true` on the session cookie: admin-ui must always be behind HTTPS (confirmed — production and dev both use TLS-terminating proxy).
- Rate-limit values: 20 req / 15 min / IP chosen as a conservative default; can be tuned via env var in a follow-up.
- `express-rate-limit@7.5.0` pinned — current stable release as of 2026-05-18.

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with file:line)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted
