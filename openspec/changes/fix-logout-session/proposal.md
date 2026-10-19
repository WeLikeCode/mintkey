# Logout invalidates the server-side session (issue #345)

## Why

Logging out does not end the session on the server. Anyone holding a copy of the operator's `mintkey_session` cookie
keeps admin access after the operator logs out, for the rest of the session row's 8 h lifetime. Measured on the base
branch (`staging`):

- `POST /v1/auth/logout` (`admin_api.api.auth.logout`) never touches the `sessions` table. It calls
  `response.delete_cookie("mintkey_session")` on the injected `Response` and then returns a new `Response(204)`, so
  FastAPI drops that header: the 204 carries no Set-Cookie at all. The REST contract
  (`docs/architecture/contracts/rest/openapi.yaml`) already promises "Invalidates the server-side session row, clears
  the session cookie".
- `GET /v1/auth/whoami` answers from a 15 s in-process cache (`_WHOAMI_CACHE`, `_WHOAMI_TTL = 15.0`) keyed by the
  session token, so even a deleted row would keep validating for up to 15 s.
- admin-ui's `GET /admin/logout` (`createLogoutHandler`, added in #344) clears `mintkey_session` and `csrf_token` in the
  browser and calls the admin-api logout above, but never destroys the AdminJS server session (`adminjs.sid`,
  `req.session`, which holds `adminUser` with copies of the session and CSRF tokens).
- It is a state-changing GET without CSRF protection: any page can force a logout with
  `<img src=".../admin/logout">`.

## What Changes

- **admin-api.** New `admin_api.auth.sessions.delete_session(token: str) -> bool` deletes the session row by id (under
  the same RLS settings as `validate_session`). `logout` deletes the row, evicts the token from `_WHOAMI_CACHE`
  (`_evict_whoami`), and answers 204 with Set-Cookie headers that clear `mintkey_session` and `csrf_token`. A lookup
  that was in flight when the token was evicted does not put it back into the cache (`_WHOAMI_EVICTIONS`). When the
  delete raises, logout answers 503 `session_store_unavailable` (fail closed, cache still evicted); the contract lists
  the 503.
- **admin-ui.** `POST /admin/logout` replaces the GET: `logoutGuard` checks the double-submit CSRF token (form field
  `_csrf` against the `csrf_token` cookie), then `createLogoutHandler` calls admin-api, destroys the AdminJS session
  and clears `adminjs.sid`, `mintkey_session` and `csrf_token`; a request with no session at all is sent to
  `/admin/login` with nothing changed. `GET /admin/logout` changes nothing: it renders a confirmation page with that
  form (or redirects to `/admin/login` when there is no session). `createLogoutRouter(adminApiUrl, rateLimiter)` mounts
  both; the AdminJS top bar gets a `LoggedIn` override that logs out through a POST form (`data-testid="logout"`).
- **End-to-end spec.** A Playwright spec `apps/admin-ui/e2e/tests/21-logout-replay.spec.ts`, next to
  `21-logout-session.spec.ts`, logs in, saves the cookie, logs out through the UI, replays the old cookie against
  `/v1/auth/whoami` and expects 401. It runs in the repository's Playwright workflow, not in the L4 gates (no Docker in
  the gate sandbox); every criterion of this change is proven by admin-api pytest and admin-ui Vitest tests.

## Capabilities

### New Capabilities

- `operator-logout`: ending an operator's admin session in admin-api and admin-ui, and the CSRF-protected logout.

### Modified Capabilities

None.

## Impact

- `apps/admin-api/src/admin_api/auth/sessions.py`, `apps/admin-api/src/admin_api/api/auth.py`,
  `docs/architecture/contracts/rest/openapi.yaml` (the 503 of `POST /v1/auth/logout`).
- `apps/admin-ui/src/routes/logout.ts`, `apps/admin-ui/src/index.ts`, `apps/admin-ui/src/components/index.ts`, new
  `apps/admin-ui/src/components/app/LoggedIn.tsx`.
- New tests: `tests/unit/admin_api/test_delete_session.py`, `test_whoami_eviction.py`, `test_logout_session.py`,
  `test_logout_store_failure.py`; `apps/admin-ui/tests/test_logout_guard.test.ts`, `test_logout_session.test.ts`,
  `test_logout_router.test.ts`, `test_logout_wiring.test.ts`, `LoggedIn.render.test.tsx`; the e2e spec above.
- One e2e edit: `apps/admin-ui/e2e/tests/21-logout-session.spec.ts` test (a) falls back to `page.goto("/admin/logout")`
  when it finds no logout element, which no longer logs out; its fallback now clicks the confirmation button
  `data-testid="logout-confirm"`. Its test names and test (b) stay as they are.
- Unchanged and still passing: `apps/admin-ui/tests/test_logout.test.ts` (the handler keeps its name and call shape),
  `tests/acceptance/test_audit_coverage.py` (the handler keeps the name `logout`, which `AUDIT_EXEMPT` lists),
  `tests/integration/admin_api/test_auth.py` (logout without a cookie is still 204, still CSRF-exempt),
  `apps/admin-ui/e2e/tests/01-login.spec.ts` (its GET of `/admin/logout` still ends on an `/admin` path).
- No database migration, no new dependency, no configuration key.
- Out of scope: Keycloak end-session (RP-initiated logout), an audit event for the session end, and sessions removed
  by anything other than logout while cached (no such code path exists). See `design.md`.
