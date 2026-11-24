# Design: tenant-session-routes

## Context

`require_tenant_session(request, tenant_id)` in `apps/admin-api/src/admin_api/auth/sessions.py` reads the
`mintkey_session` cookie, answers 401 (`mintkey:code` `unauthenticated`) for a missing or unknown session, lets a
platform admin through, and answers 403 (`permission_denied`) when the session's tenant differs from the path's. Handlers
declare it as their last parameter, `_authz: None = Depends(require_tenant_session)` (for example `list_permissions` in
`permissions.py`, every handler of `agent_secrets.py`).

The change covers seven handlers, the ones the architecture test names:

| Handler | Module | Method and path under `/v1/tenants/{tenant_id}` |
|---|---|---|
| `update_permission` | `permissions.py` | PATCH `/agents/{agent_id}/permissions/{permission_id}` |
| `reset_budget_counter` | `permissions.py` | POST `/agents/{agent_id}/permissions/{permission_id}/budget/reset` |
| `get_permission_budget` | `permissions.py` (`tenant_permissions_router`) | GET `/permissions/{permission_id}/budget` |
| `get_permission` | `permissions.py` (`tenant_permissions_router`) | GET `/permissions/{permission_id}` |
| `get_budget_status` | `budgets.py` | GET `/agents/{agent_id}/permissions/{permission_id}/budget` |
| `reset_budget` | `budgets.py` | POST `/agents/{agent_id}/permissions/{permission_id}/budget/reset` |
| `list_budget_consumers` | `budget_consumers.py` | GET `/budget-consumers` |

`reset_budget_counter` and `reset_budget` share one method and path: `create_app` in `main.py` includes the permissions
router before the budgets router, so the first one answers requests and the second is registered but shadowed. Both get
the dependency, so the rule holds whichever the router order is. The architecture test's `AGENT_SECRETS_ALLOWLIST`
entries are redundant (every handler of `agent_secrets.py` already declares the dependency); this change leaves that
test file alone.

Callers checked: the admin UI's server side (`apps/admin-ui/src/routes/budget.ts`, `routes/budget-consumers.ts`) calls
the routes with the operator's session. The three GET handlers (`budgetGetHandler`, `lookupPermission`,
`budgetConsumersHandler`) forward the browser's `Cookie` header, which holds `mintkey_session`; the three writes
(`budgetEditHandler`, `budgetRemoveHandler`, `budgetResetHandler`) call `apiWrite` with `operatorOptsFromAdmin(adminUser)`,
and `signedFetch` (`lib/signed-request.ts`) sets `Cookie: mintkey_session=<token>`. `apps/admin-ui/tests/test_budget_bff.test.ts`
and `test_budget_consumers_bff.test.ts` already cover those handlers. No admin-ui file changes, and no requirement of
this change concerns admin-ui code.

Test files that exercise these routes: `apps/admin-api/tests/test_budget_removal.py` calls `update_permission` as a
function (the new parameter has a default, so it is unaffected); `apps/admin-api/tests/api/test_budget_consumers.py` calls
the budget-consumers route over HTTP with no session cookie and, once someone runs it, needs `require_tenant_session` in its
dependency overrides (its own authentication test expects 401). No job runs those two files: the L4 gate runs
`tests/unit/admin_api` and `tests/acceptance`, and `ci.yml`'s unit job runs `tests/unit/admin_api`.
`tests/integration/admin_api` needs Docker and is not run by `ci.yml`. This change edits none of them.

## Decisions

**D1. Per-handler dependency, not a router-level one.** It is the form of the existing handlers and keeps the diff to one
line per handler. A router-level `dependencies=[...]` would also satisfy the architecture test; it is not used so that
the three modules read like their neighbours.

**D2. The gate test builds the application and walks dependency trees.** The architecture test walks
`APIRoute.dependant` of `create_app()`; the same walk in `tests/unit/admin_api/test_tenant_session_routes.py` lets the
gate decide "every tenant-scoped route". Its allowlist holds only the two OAuth2 consent callbacks, whose protection is
the single-use state token: `/v1/tenants/{tenant_id}/email-services/{service_id}/oauth2/{provider}/callback` and
`/v1/tenants/{tenant_id}/oauth2/{provider}/callback`.

**D3. HTTP behaviour is tested per router.** The shadowed budget reset route cannot be reached through the full
application, so the 401/403/200-path tests build small FastAPI apps from one group of routers each (the pattern of
`tests/unit/admin_api/test_cross_tenant_403.py`): group `grants` = `admin_api.api.permissions.router`,
`admin_api.api.permissions.tenant_permissions_router` and `admin_api.api.budget_consumers.router`; group `budgets` =
`admin_api.api.budgets.router` alone. (`main.py` imports the three `router` objects as `permissions_router`,
`budget_consumers_router` and `budgets_router`; the names in this document and the module paths in tasks.md are the same
objects.) `get_db_session` is overridden with a recording
fake session that fails the test if a statement runs before the dependency has answered.

**D4. The background document is neutral and requirement-free.** `docs/architecture/agent-governance.md` describes terms
and where things live; the requirements stay in the changes. A test pins its shape (headings, no normative keywords,
size) so a later edit cannot turn it into a second source of requirements.

**D5. The "reaches the handler" check relies on `set_tenant_context`.** Each of the seven handlers calls
`set_tenant_context(session, tenant_id)` right after it decodes its ids and before any lookup that could answer early; that
call executes `SELECT set_config('app.current_tenant', ...)`, so the recording session sees at least one statement for every
request whose ids decode (the test ids do), whatever the fake's empty `fetchone()` and `fetchall()` lead the handler to
answer. The count of 50 tenant-scoped routes is a floor: the router decorators of the tenant-prefixed modules number about 65
at the base.

**D6. The background document stays in this unit.** It is the first unit of the plan, the later changes refer to the document,
and it holds no requirement (a test pins that). Where it speaks of behaviour that later changes build (agent routes, access
requests, revocation reaching the proxy), it describes the model of the plan; each statement is made true by the change that
`## Where it lives` names, and none of them is a requirement of this change.

## Risks and edge cases

- A client that calls these routes receives 401 without a session. The admin UI sends one (Context).
  `tests/integration/admin_api/test_budget_endpoints.py` calls them through the app without a session cookie; it needs
  Docker and no job runs it.
- Platform admins keep access to every tenant, as `require_tenant_session` already allows.
- The dependency runs before the handler body, so a request that fails authentication touches no table and reveals
  nothing about the permission's existence.
- No change to responses of authenticated callers: the handlers' bodies are untouched.

## Follow-ups

- Remove the redundant `AGENT_SECRETS_ALLOWLIST` of `tests/architecture/test_authz_coverage.py`, and give the two
  dormant test files above their session override, in a later cleanup.
