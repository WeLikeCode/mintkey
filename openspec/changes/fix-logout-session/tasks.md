# Tasks: logout invalidates the server-side session

Each task writes its tests first (red: they fail on the code before the task), then the code (green). Every new test
names the criterion id of the scenario it proves: L4 gives each scenario an id `C-<8 hex>` and writes the ids with
their aliases (`operator-logout › <requirement> › <scenario>`) to the unit's `.l4/criteria.json` at intake; a pytest
test carries it in its name or as `@pytest.mark.l4("C-…")`, a Vitest test in its title (`it("C-…: …")`), a Playwright
test in its title (`@C-…`). Test seams: `design.md`, "How the gates prove it". No test may skip
or expect a failure (`pytest.mark.skip`, `xfail`, `test.skip`, `test.fixme`, ...), and existing tests stay unchanged
unless a task names them.

## 1. admin-api: delete a session row

- [x] 1.1 Add `delete_session(token: str) -> bool` to `apps/admin-api/src/admin_api/auth/sessions.py`
  - Red: `tests/unit/admin_api/test_delete_session.py` with a fake `AsyncSessionLocal` that records statements and
    params: "A session row is deleted", "No row to delete", "A token that is not a UUID".
  - Green: lazy imports and `text()` with string literals and a bound `token`, as `validate_session` does.

## 2. admin-api: evict a token from the whoami cache

- [x] 2.1 Add `_evict_whoami(session_token: str) -> None` and the counter `_WHOAMI_EVICTIONS` to `apps/admin-api/src/admin_api/api/auth.py`, and make `_whoami_lookup` skip the store when the counter moved
  - Red: `tests/unit/admin_api/test_whoami_eviction.py`: "Eviction removes only that token", "Evicting a token that
    is not cached", "A lookup in flight during logout is not cached" (patch `admin_api.api.auth.validate_session` with
    a coroutine that calls `_evict_whoami(T)` and then returns a context with `operator_id` and `tenant_id`; the fake
    `AsyncSessionLocal` returns the operator row for T).
  - Green: read the counter when the lookup starts; store only when it is unchanged; keep the TTL and the pruning.

## 3. admin-api: logout ends the session

- [x] 3.1 Rewrite `logout` in `apps/admin-api/src/admin_api/api/auth.py` (keep the name `logout`, listed in `AUDIT_EXEMPT` of `tests/acceptance/test_audit_coverage.py`, and keep `csrf_exempt("/v1/auth/logout")`): delete the row, evict the token, answer 204 that clears both cookies
  - Red: `tests/unit/admin_api/test_logout_session.py`: "The old cookie is refused after logout inside the cache
    window" (internal login, whoami 200, assert the cache entry, logout, whoami 401), "Logout clears both cookies",
    "Logout without a session cookie", "Logout twice with the same cookie", "Concurrent logouts with the same cookie",
    "A cookie that is not a UUID", "Logout of an expired session" (the store fake keeps an expired row;
    `delete_session` is awaited with its token).
  - Green: `logout(request: Request) -> Response` reads the `mintkey_session` cookie, awaits
    `delete_session(token)` (imported from `admin_api.auth.sessions` next to `create_session`), calls
    `_evict_whoami(token)`, and returns `Response(status_code=204)` after `delete_cookie("mintkey_session", path="/")`
    and `delete_cookie("csrf_token", path="/")` on that same response object. No cookie: no delete, no eviction.
- [x] 3.2 Answer 503 `session_store_unavailable` when `delete_session` raises, and add the 503 of `POST /v1/auth/logout` to `docs/architecture/contracts/rest/openapi.yaml`
  - Red: `tests/unit/admin_api/test_logout_store_failure.py`: "The session store raises" (`delete_session` raises
    `OSError`; `caplog.set_level(logging.ERROR, logger="admin_api.api.auth")`) and "The contract lists the outcomes"
    (`yaml.safe_load` of the contract file).
  - Green: catch `Exception` around the delete, `_logger.error("auth.logout_session_delete_failed error=%s",
    type(exc).__name__)`, evict in every case (`finally`), return a `JSONResponse(status_code=503, content=...)` that
    also clears both cookies; in the contract add
    `"503": $ref: "#/components/responses/ServiceUnavailable"` under the logout responses.

## 4. admin-ui: logout routes in `apps/admin-ui/src/routes/logout.ts`

- [x] 4.1 Add `readCookie(header: string | undefined, name: string): string | undefined` and `logoutGuard(req, res, next)`
  - Red: `apps/admin-ui/tests/test_logout_guard.test.ts` with fake `req`/`res`/`next`: "A missing token is refused",
    "A wrong token is refused" (same length and another length), "Nothing to log out", a valid token calls `next()`
    once; `readCookie` matches the exact name (`xcsrf_token=a` is not `csrf_token`), keeps a value's later `=`
    (`a=b=c` gives `b=c`), does not percent-decode, returns the first of repeated names, trims spaces and returns
    `undefined` for a missing header, a missing name or an empty value.
  - Green: the session test is `readCookie(cookie, "mintkey_session")` or `req.session?.adminUser`; the token is
    `req.body?._csrf` when it is a string; compare with `crypto.timingSafeEqual` on equal-length buffers; 403 is
    `text/plain` `Logout refused: missing or invalid CSRF token` and sets no cookie.
- [ ] 4.2 Make `createLogoutHandler(adminApiUrl)` destroy the AdminJS session and clear `adminjs.sid` (export `ADMINJS_SESSION_COOKIE = "adminjs.sid"`), keeping its name, its admin-api call and its 302
  - Red: `apps/admin-ui/tests/test_logout_session.test.ts` with supertest and `express-session` (name `adminjs.sid`,
    a `MemoryStore`, a test route that sets `req.session.adminUser`), the handler at `POST /admin/logout` behind
    `express.urlencoded` only: "A full logout", "admin-api is unreachable or refuses" (fetch rejects; fetch answers
    503), "The session store fails to destroy" (a store whose `destroy` calls back with an error), "A request with no
    session object" (fake `req`/`res`), "Two concurrent logouts". `apps/admin-ui/tests/test_logout.test.ts` stays as
    it is and passes.
  - Green: call admin-api only when `readCookie(req.headers.cookie, "mintkey_session")` is set; await
    `req.session.destroy` (wrapped in a promise) when `req.session` exists, then `res.clearCookie(ADMINJS_SESSION_COOKIE,
    { path: "/" })`; then clear `mintkey_session` and `csrf_token` as today; warnings go to `console.warn`.
- [ ] 4.3 Add `renderLogoutPage(csrfToken: string): string`, `logoutPageHandler(req, res)` and `createLogoutRouter(adminApiUrl: string, rateLimiter: RequestHandler): Router`
  - Red: `apps/admin-ui/tests/test_logout_router.test.ts` (supertest, `express-session`, the router with a counting
    limiter): "GET renders a confirmation form", "GET without a CSRF cookie", "GET without a session", "The router serves
    both methods behind the limiter".
  - Green: the page escapes `& < > " '` in the token, has no `<script>`, and is sent with `Cache-Control: no-store`;
    `POST /admin/logout` runs the limiter, `express.urlencoded({ extended: false })`, `logoutGuard`, then
    `createLogoutHandler(adminApiUrl)`.

## 5. admin-ui: top bar, wiring, end-to-end spec

- [ ] 5.1 Add the `LoggedIn` override `apps/admin-ui/src/components/app/LoggedIn.tsx` and register it in `apps/admin-ui/src/components/index.ts` with `componentLoader.override("LoggedIn", "./app/LoggedIn")`
  - Red: `apps/admin-ui/tests/LoggedIn.render.test.tsx` (jsdom project; `fireEvent.submit(form)` fires the submit
    event): "The top bar renders the form", "Submit sends the current CSRF cookie", "A session without a CSRF token";
    and in `apps/admin-ui/tests/test_logout_wiring.test.ts` (reads the source, as
    `test_index_security_config.test.ts` does): "The override is registered".
  - Green: plain `div`, `span`, `form`, `input` and `button` elements (no `@adminjs/design-system` import), props
    `session` and `paths` as AdminJS passes them to `LoggedIn`; the hidden input uses `defaultValue`, and the form's
    `onSubmit` writes the `csrf_token` value parsed from `document.cookie` into it when present (no `preventDefault`).
- [ ] 5.2 Mount `createLogoutRouter(ADMIN_API_URL, logoutRateLimit)` in `apps/admin-ui/src/index.ts` in place of `app.get("/admin/logout", ...)`, and write the e2e spec `apps/admin-ui/e2e/tests/21-logout-replay.spec.ts`
  - Red: append to `apps/admin-ui/tests/test_logout_wiring.test.ts`: "The server mounts the routes". In the same red
    step write the Playwright files; the L4 gates do not run them (`playwright.yml` does):
    - `apps/admin-ui/e2e/tests/21-logout-replay.spec.ts`, structured as `21-logout-session.spec.ts` (imports from
      `../fixtures/test.js`, `ADMIN_API` from `../env.js`, a `beforeAll` that expects `PLAYWRIGHT_PASS`). Test 1: clear
      the context's cookies, log in through `/auth/start` and the Keycloak form, read the `mintkey_session` value,
      check that a new `playwright.request` context with only `Cookie: mintkey_session=<old>` gets 200 from
      `${ADMIN_API}/v1/auth/whoami`, click `[data-testid="logout"]`, wait for `/admin/login`, then expect 401 from
      whoami with the old cookie and no `mintkey_session`, `csrf_token` or `adminjs.sid` cookie left in the context.
      Test 2: after a fresh login, `GET /admin/logout` shows the confirmation form and whoami with the cookie still
      answers 200; clicking `[data-testid="logout-confirm"]` makes it 401. Each test fails, never returns early, when
      the stack or the Keycloak form is missing; each title carries the criterion id of the first scenario of
      "Logout deletes the server-side session".
    - `apps/admin-ui/e2e/tests/21-logout-session.spec.ts` test (a): after its `page.goto("/admin/logout")` fallback,
      click `[data-testid="logout-confirm"]` and wait for `/admin/login`; correct its header comment (issue #345 is
      fixed). Nothing else in the file changes.
  - Green: import `createLogoutRouter` instead of `createLogoutHandler`, mount it at the same place (after
    `express-session`, before `app.use(requireSession)`) with `logoutRateLimit`, and update the route comments in
    `index.ts` and the header comment of `logout.ts` (no known limitation left).
