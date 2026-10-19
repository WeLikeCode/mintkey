# Operator logout

## Purpose

Ending an operator's admin session for good: admin-api deletes the session row and forgets the cached identity,
admin-ui destroys its AdminJS session and clears every session cookie, and the browser-facing logout is a POST
protected against cross-site requests. A copy of the old `mintkey_session` cookie must not keep access after logout.

## ADDED Requirements

### Requirement: Logout deletes the server-side session

`POST /v1/auth/logout` (`admin_api.api.auth.logout`) SHALL delete the session row named by the request's
`mintkey_session` cookie, evict that token from the whoami cache (`_evict_whoami`), and answer 204 with Set-Cookie
headers that clear `mintkey_session` and `csrf_token`. The route SHALL stay CSRF-exempt
(`csrf_exempt("/v1/auth/logout")` in `create_app`).

#### Scenario: The old cookie is refused after logout inside the cache window

- **GIVEN** an operator logged in with `POST /v1/auth/internal-login`, and `GET /v1/auth/whoami` answered 200 for that
  `mintkey_session` cookie, so `_WHOAMI_CACHE` holds the token (the test asserts the entry is present)
- **WHEN** `POST /v1/auth/logout` is sent with that cookie and no `X-Mintkey-Csrf` header, and then
  `GET /v1/auth/whoami` is sent with the same old cookie, with no wait between the calls
- **THEN** the logout answers 204, the session store no longer holds the token, `_WHOAMI_CACHE` has no entry for it,
  and whoami answers 401 with `mintkey:code` `unauthenticated`

#### Scenario: Logout clears both cookies

- **WHEN** `POST /v1/auth/logout` answers 204
- **THEN** the response has a Set-Cookie header for `mintkey_session` and one for `csrf_token`, each with `Max-Age=0`
  and `Path=/`

#### Scenario: Logout without a session cookie

- **WHEN** `POST /v1/auth/logout` is sent with no `mintkey_session` cookie
- **THEN** it answers 204 with both cookie-clearing headers, `delete_session` is not called and `_WHOAMI_CACHE` is
  unchanged

#### Scenario: Logout twice with the same cookie

- **WHEN** the same `mintkey_session` cookie is sent to `POST /v1/auth/logout` twice in a row
- **THEN** both responses are 204, no request raises, and the session store does not hold the token after either call

#### Scenario: Concurrent logouts with the same cookie

- **WHEN** two `POST /v1/auth/logout` requests with the same `mintkey_session` cookie run concurrently
  (`asyncio.gather`)
- **THEN** both responses are 204, neither raises, and afterwards the session store does not hold the token and
  `_WHOAMI_CACHE` has no entry for it

#### Scenario: A cookie that is not a UUID

- **WHEN** `POST /v1/auth/logout` is sent with `mintkey_session=not-a-uuid`
- **THEN** it answers 204 with both cookie-clearing headers

#### Scenario: Logout of an expired session

- **GIVEN** a `mintkey_session` cookie whose session row is past its `expires_at`
- **WHEN** `POST /v1/auth/logout` is sent with it
- **THEN** it answers 204 and `delete_session` is called with that token, so the row is removed by its id

### Requirement: A failed session delete is reported

When `delete_session` raises during logout, admin-api SHALL answer 503 as a `JSONResponse` (content type
`application/json`) with the body `{"mintkey:code": "session_store_unavailable", "title": "Session store
unavailable"}`, still evict the whoami cache entry and clear both cookies, and log the failure at ERROR level through
the module's stdlib logger (`logging.getLogger("admin_api.api.auth")`, the `_logger` of `auth.py`) with a message
starting `auth.logout_session_delete_failed` and naming the exception type, never the token. The REST contract SHALL
list that answer.

#### Scenario: The session store raises

- **GIVEN** `_WHOAMI_CACHE` holds an entry for token T and `delete_session` raises `OSError`
- **WHEN** `POST /v1/auth/logout` is sent with `mintkey_session=T`
- **THEN** it answers 503 with that body and content type, `_WHOAMI_CACHE` has no entry for T, the response clears
  `mintkey_session` and `csrf_token`, pytest's `caplog` holds an ERROR record of `admin_api.api.auth` whose message
  starts `auth.logout_session_delete_failed` and names `OSError`, and no captured log text contains T

#### Scenario: The contract lists the outcomes

- **GIVEN** the base branch's contract lists only `204` for `POST /v1/auth/logout`
- **WHEN** `docs/architecture/contracts/rest/openapi.yaml` is loaded with `yaml.safe_load`
- **THEN** the response keys of `paths./v1/auth/logout.post.responses` are exactly `204` and `503`, `503` is
  `{"$ref": "#/components/responses/ServiceUnavailable"}`, and `components.responses.ServiceUnavailable` exists

### Requirement: delete_session removes a session row

`admin_api.auth.sessions.delete_session(token: str) -> bool` SHALL delete the `sessions` row whose id is the token,
whatever its `expires_at`, in one transaction that first sets `app.current_tenant` to
`00000000-0000-0000-0000-000000000000` and `app.platform_admin_view` to `on` (as `validate_session` does, for the
`tenant_isolation` RLS policy), and SHALL return whether a row was deleted.

#### Scenario: A session row is deleted

- **WHEN** `delete_session` is called with a UUID token and the delete statement reports one row
- **THEN** the session executes, in this order, the two `set_config` statements and
  `DELETE FROM sessions WHERE id = CAST(:token AS uuid)` with the token bound as `token`, the delete has no
  `expires_at` condition, and the call returns True

#### Scenario: No row to delete

- **WHEN** `delete_session` is called with a UUID token and the delete statement reports zero rows
- **THEN** it returns False and raises nothing

#### Scenario: A token that is not a UUID

- **WHEN** `delete_session` is called with `not-a-uuid`
- **THEN** it returns False and opens no database session

### Requirement: The whoami cache forgets a logged-out token

`admin_api.api.auth._evict_whoami(session_token: str) -> None` SHALL remove that token's `_WHOAMI_CACHE` entry and add
one to the module counter `_WHOAMI_EVICTIONS`. `_whoami_lookup` SHALL NOT store its result when
`_WHOAMI_EVICTIONS` changed while the lookup ran.

#### Scenario: Eviction removes only that token

- **GIVEN** `_WHOAMI_CACHE` holds fresh entries for tokens A and B
- **WHEN** `_evict_whoami(A)` is called
- **THEN** the cache has no entry for A, still has B's entry, and `_WHOAMI_EVICTIONS` is one higher

#### Scenario: Evicting a token that is not cached

- **WHEN** `_evict_whoami` is called for a token with no cache entry
- **THEN** it raises nothing and the other entries stay

#### Scenario: A lookup in flight during logout is not cached

- **GIVEN** a `GET /v1/auth/whoami` for token T whose session validation succeeds, and `_evict_whoami(T)` runs after
  the validation and before the lookup stores its result
- **WHEN** the whoami request completes
- **THEN** that request answers 200, and `_WHOAMI_CACHE` has no entry for T afterwards

### Requirement: admin-ui logout ends the AdminJS session

`createLogoutHandler(adminApiUrl)` in `apps/admin-ui/src/routes/logout.ts` SHALL, when the request carries a
`mintkey_session` cookie, call `POST {adminApiUrl}/v1/auth/logout` with `{ method: "POST", headers: { Cookie: <the
request's Cookie header> } }`; then destroy `req.session` when it exists and clear `adminjs.sid`; then clear
`mintkey_session` and `csrf_token` (path `/`); and redirect 302 to `/admin/login`. An admin-api error or non-2xx answer,
or a failed session destroy, SHALL be logged and SHALL NOT stop these steps.

#### Scenario: A full logout

- **GIVEN** an Express app with `express-session` (cookie name `adminjs.sid`, a `MemoryStore`) whose session holds an
  `adminUser`, and fetch answering 204
- **WHEN** the handler serves a POST carrying that `adminjs.sid`, `mintkey_session` and `csrf_token`
- **THEN** fetch was called once with the admin-api logout URL and the request's Cookie header, the response clears
  `adminjs.sid`, `mintkey_session` and `csrf_token`, redirects 302 to `/admin/login`, the store holds no session, and
  a later request with the old `adminjs.sid` sees no `adminUser`

#### Scenario: admin-api is unreachable or refuses

- **WHEN** fetch rejects, or answers 503
- **THEN** the AdminJS session is still destroyed, the three cookies are cleared and the response redirects 302 to
  `/admin/login`

#### Scenario: The session store fails to destroy

- **WHEN** the store's destroy calls back with an error
- **THEN** the response still clears the three cookies and redirects 302 to `/admin/login`

#### Scenario: A request with no session object

- **WHEN** the handler serves a request that has no `req.session` and no cookies
- **THEN** it clears only `mintkey_session` and `csrf_token`, redirects 302 to `/admin/login`, and does not call fetch

#### Scenario: Two concurrent logouts

- **WHEN** two POSTs with the same cookies are served concurrently
- **THEN** both redirect 302 to `/admin/login`, both clear `adminjs.sid`, and the store holds no session afterwards

### Requirement: admin-ui logout is a CSRF-protected POST

`POST /admin/logout` SHALL pass `logoutGuard` before `createLogoutHandler`: a request with neither a `mintkey_session`
cookie nor `req.session.adminUser` is redirected 302 to `/admin/login` with nothing changed; otherwise the form field
`_csrf` must equal the `csrf_token` cookie (compared in constant time, `crypto.timingSafeEqual`) or the answer is 403
`text/plain` with the body `Logout refused: missing or invalid CSRF token`. Cookies are read with
`readCookie(header: string | undefined, name: string): string | undefined`: the exact name, the value after the first
`=` (later `=` kept), trimmed, not percent-decoded, the first occurrence when a name repeats, and `undefined` when the
header, the name or the value is missing or empty.
`GET /admin/logout` SHALL change nothing: it renders a confirmation page whose form posts the token.

#### Scenario: A missing token is refused

- **GIVEN** a request with a live AdminJS session and a `mintkey_session` cookie
- **WHEN** it posts without the `_csrf` field, or without a `csrf_token` cookie
- **THEN** the answer is 403 with that body, admin-api is not called, no Set-Cookie header is sent and the AdminJS
  session keeps its `adminUser`

#### Scenario: A wrong token is refused

- **WHEN** such a request posts `_csrf` different from its `csrf_token` cookie, of the same or of another length
- **THEN** the answer is 403 and nothing changes, as for a missing token

#### Scenario: Nothing to log out

- **WHEN** a POST carries no `mintkey_session` cookie and its session has no `adminUser`
- **THEN** it is redirected 302 to `/admin/login`, admin-api is not called and no Set-Cookie header is sent

#### Scenario: GET renders a confirmation form

- **GIVEN** a request with a live session and the cookie `csrf_token` whose value contains `"`
- **WHEN** it sends `GET /admin/logout`
- **THEN** the answer is 200 HTML with `Cache-Control: no-store`, holding a form with method POST and action
  `/admin/logout`, a hidden input `_csrf` with the cookie value HTML-escaped, a submit button
  `data-testid="logout-confirm"` and no `<script>`; admin-api is not called, no Set-Cookie header is sent and the
  session keeps its `adminUser`

#### Scenario: GET without a CSRF cookie

- **GIVEN** a request with a live session and no `csrf_token` cookie
- **WHEN** it sends `GET /admin/logout`
- **THEN** the page renders the same form with an empty `_csrf` value (a POST of it is refused with 403, as a missing
  token is), and nothing changes

#### Scenario: GET without a session

- **WHEN** `GET /admin/logout` carries no `mintkey_session` cookie and no `adminUser`
- **THEN** it is redirected 302 to `/admin/login`

### Requirement: The admin UI logs out through a POST form

The AdminJS top bar SHALL log out through a POST form: the `LoggedIn` override shows the operator's email and a form
posting to `paths.logoutPath` with a hidden `_csrf` and a submit button `data-testid="logout"`. The field starts as
`session.csrfToken` (AdminJS passes `req.session.adminUser` as `session`, and `requireSession` copies `csrfToken` from
the request's `csrf_token` cookie on every `/admin` request); on submit the form replaces it with the current
`csrf_token` value of `document.cookie` when that cookie is readable, so a page rendered before a later login still
sends the token the server will compare. `createLogoutRouter(adminApiUrl, rateLimiter)` SHALL mount both logout routes, and
`apps/admin-ui/src/index.ts` SHALL mount it in place of the former GET logout route.

#### Scenario: The top bar renders the form

- **WHEN** the `LoggedIn` override renders with `session` `{email: "op@example.test", csrfToken: "tok"}` and
  `paths.logoutPath` `/admin/logout`
- **THEN** it shows the email, a form with method `post` and action `/admin/logout`, a hidden input `_csrf` with value
  `tok`, a submit button `data-testid="logout"`, and no link to the logout path

#### Scenario: Submit sends the current CSRF cookie

- **GIVEN** `document.cookie` holds `csrf_token=fresh` and the override rendered with `session.csrfToken` `stale`
- **WHEN** the form's submit event fires
- **THEN** the hidden `_csrf` value is `fresh`

#### Scenario: A session without a CSRF token

- **GIVEN** `document.cookie` has no `csrf_token`
- **WHEN** the override renders with a `session` that has no `csrfToken`, and the form's submit event fires
- **THEN** the form renders and submits an empty `_csrf` value, which the server refuses with 403

#### Scenario: The override is registered

- **WHEN** `apps/admin-ui/src/components/index.ts` is read
- **THEN** it calls `componentLoader.override("LoggedIn", "./app/LoggedIn")`

#### Scenario: The router serves both methods behind the limiter

- **GIVEN** `createLogoutRouter` mounted behind `express-session` with a limiter that counts its calls
- **WHEN** it serves a GET of `/admin/logout` with a live session, a POST without `_csrf`, and a POST whose `_csrf`
  equals the `csrf_token` cookie
- **THEN** the limiter ran three times, the GET answers 200 with the confirmation form, the POST without a token
  answers 403, and the POST with the token redirects 302 to `/admin/login` and clears the three cookies

#### Scenario: The server mounts the routes

- **WHEN** `apps/admin-ui/src/index.ts` is read
- **THEN** it calls `createLogoutRouter(ADMIN_API_URL, logoutRateLimit)` before `app.use(requireSession)`, and it has
  no `app.get("/admin/logout"` and no other use of `createLogoutHandler`
