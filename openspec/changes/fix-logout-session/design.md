# Design: logout invalidates the server-side session

## Context

What the base branch has (module, function and value names; no line numbers):

- **Sessions.** `admin_api.auth.sessions.create_session(operator_id, tenant_id, auth_method)` inserts a `sessions` row
  (id = a UUID, `expires_at` = now + 8 h) and returns the id as the token stored in the `mintkey_session` cookie.
  `validate_session(token)` returns `None` for a token that is not a UUID, else opens `AsyncSessionLocal()`, runs
  `set_config('app.current_tenant', '00000000-0000-0000-0000-000000000000', true)` and
  `set_config('app.platform_admin_view', 'on', true)` in one transaction (the `tenant_isolation` RLS policy of
  `sessions`, changelog `002-operators.yaml`), then selects the row with `expires_at > now()`. Nothing deletes a session
  row today. `mintkey_app` has DELETE on every table (`009-roles.yaml`).
- **whoami.** `admin_api.api.auth._whoami_lookup(session_token)` answers from `_WHOAMI_CACHE`
  (`dict[str, tuple[dict, float]]`, `time.monotonic()` stamps, `_WHOAMI_TTL = 15.0`) when the entry is fresh; else it
  calls `validate_session`, reads the operator joined to the session row through `AsyncSessionLocal`, stores the result
  and prunes stale entries. `whoami` answers 401 `{"mintkey:code": "unauthenticated", ...}` when the lookup is `None`.
  admin-api runs as one uvicorn process (`apps/admin-api/Dockerfile` CMD has no `--workers`), so there is one cache.
- **logout.** `logout(response: Response)` calls `response.delete_cookie("mintkey_session")` and returns a new
  `Response(status_code=204)`; FastAPI ignores the injected response's headers when a `Response` is returned, so no
  Set-Cookie is sent (measured with the app and httpx `ASGITransport`). `create_app` registers
  `csrf_exempt("/v1/auth/logout")`; `CsrfMiddleware` (`admin_api.middleware.csrf`) is the double-submit check of
  ADR-0013: `csrf_token` cookie against the `X-Mintkey-Csrf` header, `hmac.compare_digest`.
- **admin-ui.** `apps/admin-ui/src/index.ts` mounts `express-session` (`name: "adminjs.sid"`, `MemoryStore`,
  `saveUninitialized: false`, SameSite Strict) before every route; `requireSession` calls whoami for each `/admin`
  request and writes `req.session.adminUser` (`email`, `operatorId`, `tenantId`, `isPlatformAdmin`, `sessionToken`,
  `csrfToken`, `authMethod`; `sessionToken` and `csrfToken` are copied from the request's `mintkey_session` and
  `csrf_token` cookies), and skips `/admin/logout`. `app.get("/admin/logout", logoutRateLimit,
  createLogoutHandler(ADMIN_API_URL))` is the logout today. AdminJS 7's top bar renders its `LoggedIn` component when
  `session.email` is set; its "Log out" item sets `window.location.href = paths.logoutPath` (a GET of
  `/admin/logout`). `LoggedIn` is overridable with `componentLoader.override` (the project already overrides
  `DefaultShowProperty` in `src/components/index.ts`). admin-api sets `mintkey_session` (httpOnly) and `csrf_token`
  (readable by page script) with SameSite Lax, no `Domain` (host-only) and Starlette's default `Path=/`, only at login
  (`internal_login`, `oidc_callback`): a `delete_cookie(name, path="/")` with no domain matches them. Over HTTPS the
  clearing header comes from a secure origin, so it may replace a `Secure` cookie.

## Goals / Non-Goals

**Goals:** a replayed old `mintkey_session` cookie gets 401 right after logout, also inside the 15 s cache window; the
AdminJS session ends with the operator's session; logout cannot be triggered cross-site; every criterion is proven by
the L4 gates (admin-api pytest, admin-ui Vitest), with the e2e spec as extra evidence in the repository's CI.

**Non-Goals:** ending the Keycloak SSO session (RP-initiated logout: the next `/auth/start` may log the operator in
without a password prompt); an audit event for a session end; a cache shared between processes; sessions removed by
anything other than logout while cached (none exists; the 15 s staleness of ADR-0019 §3 stays for that case); the
copy of `adminUser` that AdminJS embeds in its pages.

## Decisions

1. **Delete by id under the platform-admin RLS view.** `delete_session(token)` mirrors `validate_session`: a non-UUID
   token returns False without a database session (so `CAST(... AS uuid)` cannot raise), then one transaction runs the
   two `set_config` statements and `DELETE FROM sessions WHERE id = CAST(:token AS uuid)` through `text()` with a bound
   parameter (`tests/acceptance/test_no_sql_injection.py` forbids built SQL). No `expires_at` condition: an expired row
   is removed too. It returns `rowcount > 0`. Without the `set_config` lines RLS would hide every row and the delete
   would remove nothing silently. Alternative: set `app.current_tenant` to the row's tenant, which needs a read first.
2. **Evict, and keep an in-flight lookup from re-caching.** `_evict_whoami(token)` pops the entry and increments the
   module counter `_WHOAMI_EVICTIONS`; `_whoami_lookup` reads the counter when it starts and stores its result only if
   the counter is unchanged. A lookup that read the row just before the delete therefore answers its own request but
   leaves nothing behind. Alternative: a per-token tombstone dict with its own expiry; more state for the same guarantee
   (an eviction of any token only costs one extra database read for lookups in flight at that moment).
3. **Fail closed on a store error.** When `delete_session` raises, `logout` logs `auth.logout_session_delete_failed`
   with the exception type (never the token), evicts the cache entry, clears the cookies and answers 503
   `session_store_unavailable`, so a caller knows the row may still be valid. A 204 would claim a logout that did not
   happen; a bare 500 would skip the cache eviction and the cookie clearing. The contract gets the 503 entry
   (`#/components/responses/ServiceUnavailable` exists).
4. **admin-api logout stays CSRF-exempt.** Kept: a logout without a session must stay 204 for scripts and for
   `tests/integration/admin_api/test_auth.py`; the cookies are SameSite Lax, so a cross-site POST carries no
   `mintkey_session`; admin-ui calls it server to server with only the Cookie header (`test_logout.test.ts` pins that
   call). The browser-facing check is in admin-ui. Alternative: drop the exemption and forward `X-Mintkey-Csrf`;
   rejected for this fix because it changes the API for every client.
5. **admin-ui CSRF is the double-submit cookie already in use.** `logoutGuard` compares the urlencoded form field
   `_csrf` with the `csrf_token` cookie through `crypto.timingSafeEqual` (different lengths fail first), as admin-api's
   `CsrfMiddleware` does with its header. Alternative: a synchronizer token in the AdminJS session; rejected because
   that session is a `MemoryStore` that `requireSession` does not populate on `/admin/logout`. The body parser
   (`express.urlencoded({ extended: false })`) is scoped to the POST route: a global parser breaks AdminJS's
   formidable parsing (comment in `index.ts`). A request with neither a `mintkey_session` cookie nor an `adminUser`
   has nothing to end and is redirected to `/admin/login` before the token check, so a second logout from a stale page
   lands on the login page instead of a 403; a cross-site POST carries none of the three cookies (Lax and Strict) and
   lands there too, changing nothing.
6. **The guard is a separate middleware; the handler keeps its contract.** `createLogoutHandler(adminApiUrl)` keeps
   its name, its admin-api call (`{ method: "POST", headers: { Cookie } }`) and its 302, so the two cases of
   `apps/admin-ui/tests/test_logout.test.ts` pass unchanged. Their shape: case 1 passes the fake request
   `{ headers: { cookie: "mintkey_session=abc; csrf_token=def" } }` with fetch resolving 204 and expects that exact
   fetch call, `clearCookie` of `mintkey_session` and `csrf_token` with `{ path: "/" }`, and `redirect(302,
   "/admin/login")`; case 2 passes `{ headers: {} }` with fetch rejecting and expects exactly two `clearCookie` calls
   and the redirect (it does not assert the fetch). So the session destroy and the `adminjs.sid` clearing run only when
   `req.session` exists, and skipping the admin-api call without a `mintkey_session` cookie keeps case 2 green. The
   handler logs with `console.warn` (the fake requests have no `req.log`).
7. **The top bar posts a form; GET only confirms.** The `LoggedIn` override (`src/components/app/LoggedIn.tsx`, plain
   elements only, so the render project's mocks need no change) shows `session.email` and a form posting to
   `paths.logoutPath` with a hidden `_csrf` and a button `data-testid="logout"`, which is also what the locator of
   `21-logout-session.spec.ts` looks for. The field starts as `session.csrfToken`, which equals the `csrf_token`
   cookie of the request that rendered the page; on submit it takes the cookie's current value from
   `document.cookie`, because a login in another tab sets a new `csrf_token` and would make the rendered copy stale. `GET /admin/logout` renders a confirmation page with the same form
   (`data-testid="logout-confirm"`) for bookmarks and typed URLs. It never submits by itself: an auto-submitting page
   would turn any cross-site navigation into a logout again. Alternatives: a `fetch` from the top bar (needs script
   and redirect handling; a form works without the SPA); answering GET with 405 (a dead end for a typed URL).
8. **One router factory.** `createLogoutRouter(adminApiUrl, rateLimiter)` returns an Express `Router` with
   `GET /admin/logout` (limiter, `logoutPageHandler`) and `POST /admin/logout` (limiter, urlencoded parser,
   `logoutGuard`, `createLogoutHandler`). `index.ts` mounts it where the GET route was, after `express-session` and
   before `requireSession`, with the existing `logoutRateLimit`. Supertest can then test the real routes; `index.ts`
   itself starts the server on import, so its wiring is checked by reading the source, as
   `test_index_security_config.test.ts` and `test_oauth2_bff_route.test.ts` already do.
9. **The e2e spec is written in a red step.** The L4 test gate runs Vitest with `e2e/**` excluded, so a step whose only
   new test is a Playwright file has no failing test id and cannot pass its red check; a green step may not change a
   test file. The e2e file (and the fallback edit of `21-logout-session.spec.ts`) is therefore written in the red step
   of task 5.2, next to that task's Vitest tests, and stays frozen through green. No criterion depends on it.

## How the gates prove it (no database, no Docker)

- admin-api tests live in `tests/unit/admin_api/` (the gate runs that folder, not `tests/integration`). They use
  `admin_api.main.create_app()` with httpx `AsyncClient(transport=ASGITransport(app=app))`, as `test_auth.py` does, and
  clear `_WHOAMI_CACHE` before each test. An in-memory session store stands in for the database: patch
  `admin_api.api.auth.create_session`, `admin_api.api.auth.validate_session` and `admin_api.api.auth.delete_session`
  (the names `auth.py` imports), and for internal login `admin_api.auth.internal.fetch_operator`,
  `record_failed_attempt` and `clear_failed_attempts` (an operator mock with an Argon2 hash of the test password). The
  identity query of `_whoami_lookup` and the statements of `delete_session` run against a fake `AsyncSessionLocal`
  (patch `admin_api.db.session.AsyncSessionLocal`; it is imported inside the functions): a callable returning an async
  context manager whose session has an async-context `begin()` and an `execute(statement, params)` that records
  `str(statement)` and the params and returns an object with `rowcount` and `fetchone()`; the identity row is
  `(o.id, o.tenant_id, o.email, o.is_platform_admin, s.auth_method)`. No test sleeps.
- A red test must fail by assertion on the code before its task. A test written before `auth.py` imports
  `delete_session` patches it with `patch("admin_api.api.auth.delete_session", ..., create=True)`, and the 503 test
  uses `ASGITransport(app=app, raise_app_exceptions=False)`, so the unhandled `OSError` of the old code is a 500 response
  and not an exception in the test.
- "No Set-Cookie" for a refused or no-op request holds because `index.ts` builds the session with `resave: false`,
  `saveUninitialized: false` and no `rolling`: `express-session` then sends `adminjs.sid` only for a session that the
  request modified or created. The tests build their session middleware with the same options.
- admin-ui tests use Vitest's node project (`tests/**/*.test.ts`) with `supertest` and `express-session`, as
  `test_budget_bff.test.ts` does, and the jsdom project (`tests/**/*.render.test.tsx`) with `@testing-library/react`
  for the override. `fetch` is stubbed with `vi.stubGlobal`. A cleared cookie is a Set-Cookie for that name with an
  empty value and `Expires=Thu, 01 Jan 1970 00:00:00 GMT`.
- The plan gives the unit no `acceptance_profile`, so it gets the default `all`: every gate configured in
  `.l4/config.yaml` (setup, lint, typecheck, test); there is no e2e gate.
- `apps/admin-ui/e2e/tests/01-login.spec.ts` clears the cookies before each of its tests and logs in itself; its test 4
  asserts only that a GET of `/admin/logout` ends on an `/admin` path without a JavaScript error, which the
  confirmation page satisfies. No later spec relies on that GET having ended a session.
- The repository's `playwright.yml` runs the e2e specs on pull requests to `main` or `develop` that touch
  `apps/admin-ui/**` or `apps/admin-api/**`, nightly, and on `workflow_dispatch`; the unit's pull request to `staging`
  runs only the L4 workflow.

## Risks / Trade-offs

- **The AdminJS bundle.** If the override fails to bundle, the top bar falls back to AdminJS's GET link, which now
  shows the confirmation page: logout still works with one more click. The e2e spec covers the override.
- **A 503 is not shown to the operator.** When admin-api cannot delete the row, admin-ui still ends its own session,
  clears the cookies and redirects to `/admin/login` (it logs a warning): the browser is logged out while a copied
  cookie may stay valid until the row expires. The fail-closed answer is for API clients; surfacing it in the UI is a
  follow-up.
- **Unexecuted e2e files.** The L4 gates do not lint, type-check or run `apps/admin-ui/e2e/**` (`tsconfig.json`
  includes `src/**` only and both Vitest projects exclude `e2e/**`); the repository's Playwright workflow is their
  first run.
- **Lost CSRF cookie.** An operator whose `csrf_token` cookie is gone while `mintkey_session` stays gets 403 from the
  form; logging in again sets a new `csrf_token`. Both cookies are set and cleared together, so this needs a manual
  cookie deletion.
- **Multiple admin-api processes.** The eviction is per process. A deployment with several workers would keep a cached
  identity in the other processes for up to 15 s; today there is one process.
