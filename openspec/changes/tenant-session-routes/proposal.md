# Every tenant-scoped route requires the tenant session

## Why

The admin API's routes under `/v1/tenants/{tenant_id}/...` are meant to be reached only by an operator whose session
belongs to that tenant (or by a platform admin). `require_tenant_session` (`admin_api.auth.sessions`) enforces that, and
the architecture test `tests/architecture/test_authz_coverage.py::test_tenant_scoped_routes_have_require_tenant_session`
checks that every such route declares it. This change completes the set: it adds the dependency to seven handlers of
three modules (`permissions.py`, `budgets.py`, `budget_consumers.py`), so that the test passes.

The coming agent-governance changes add routes that act on grants, services and credentials. They build on the rule that
a tenant-scoped route always has a tenant session, so the rule is completed first, and a test that the gate runs keeps
it true.

## What Changes

- The seven handlers take `_authz: None = Depends(require_tenant_session)`, the form the other handlers of
  `permissions.py` use:
  - `permissions.py`: `update_permission` (PATCH grant), `reset_budget_counter` (POST budget reset), `get_permission_budget`
    and `get_permission` (the two GETs of `tenant_permissions_router`);
  - `budgets.py`: `get_budget_status` and `reset_budget`;
  - `budget_consumers.py`: `list_budget_consumers`.
- A new admin-api unit test, which the L4 gate runs, decides the rule: it builds the application, walks every
  tenant-scoped route's dependency tree, and calls each of the seven routes with no session, a session of another tenant
  and a session of the right tenant. The architecture test passes as well (it is not part of the gate).
- A short background document, `docs/architecture/agent-governance.md`, describes the governance model that the
  following changes build. It holds no requirements.

## Capabilities

### New Capabilities
- `tenant-session-routes`: the tenant session requirement of the tenant-scoped admin-api routes, and the background
  document that later changes refer to.

## Impact

- Changed: `apps/admin-api/src/admin_api/api/permissions.py`, `apps/admin-api/src/admin_api/api/budgets.py`,
  `apps/admin-api/src/admin_api/api/budget_consumers.py`.
- New: `tests/unit/admin_api/test_tenant_session_routes.py`, `tests/unit/admin_api/test_agent_governance_doc.py`,
  `docs/architecture/agent-governance.md`.
- Callers: the admin UI calls all seven routes with the operator's session cookie (design.md, Context), so it keeps
  working without a change. A request without a session receives 401.
- No migration, no OpenAPI path change (`tests/acceptance/openapi_snapshot.json` lists router prefixes only), no new
  configuration.
