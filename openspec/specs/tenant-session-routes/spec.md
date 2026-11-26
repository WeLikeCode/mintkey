# tenant-session-routes Specification

## Purpose
Every admin-api route under `/v1/tenants/{tenant_id}/` is available only to an operator whose session belongs to that
tenant, or to a platform admin; the two OAuth2 consent callbacks, which carry a single-use state token instead, are the
only exceptions. A short background document describes the agent-governance model the later changes build.

## Requirements

### Requirement: Every tenant-scoped route requires the tenant session
`admin_api.auth.sessions.require_tenant_session` SHALL be in the dependency tree of every route of the admin-api
application whose path matches `^/v1/tenants/\{[^}]+\}/.+`, except
`/v1/tenants/{tenant_id}/email-services/{service_id}/oauth2/{provider}/callback` and
`/v1/tenants/{tenant_id}/oauth2/{provider}/callback`. The handlers `update_permission`, `reset_budget_counter`,
`get_permission_budget` and `get_permission` (`admin_api.api.permissions`), `get_budget_status` and `reset_budget`
(`admin_api.api.budgets`) and `list_budget_consumers` (`admin_api.api.budget_consumers`) SHALL declare it as their last
parameter, `_authz: None = Depends(require_tenant_session)`. The test
`tests/architecture/test_authz_coverage.py::test_tenant_scoped_routes_have_require_tenant_session` passes as a result;
that file is not run by the L4 gate, so the gate decides the rule through the unit tests of these scenarios.

#### Scenario: every tenant-scoped route has the dependency
- **WHEN** the application of `admin_api.main.create_app()` is built (with `MINTKEY_AUDIT_HMAC_KEY` and
  `MINTKEY_VAULT_BACKEND=sqlite` set by the test) and the dependency tree of every route whose path matches the pattern
  above is walked, except the two callbacks
- **THEN** each route's tree contains `require_tenant_session`, and the walk finds at least 50 such routes (the count
  guards against an empty walk); the routes `PATCH .../agents/{agent_id}/permissions/{permission_id}`,
  `POST .../agents/{agent_id}/permissions/{permission_id}/budget/reset` (both registrations),
  `GET .../agents/{agent_id}/permissions/{permission_id}/budget`, `GET .../permissions/{permission_id}`,
  `GET .../permissions/{permission_id}/budget` and `GET .../budget-consumers` are among them

#### Scenario: a request without a session is refused before any statement
- **WHEN** each of the seven routes (the first group of routers `permissions_router`, `tenant_permissions_router` and
  `budget_consumers_router` for five of them, `budgets_router` alone for `get_budget_status` and `reset_budget`) is
  called for tenant `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`, agent `agent_3C7JAGMBGR9EMRS2AVGXDHQXDX` and permission
  `perm_3C7JAGMBGR9EMRS2AVGXDHQXDX` with no `mintkey_session` cookie
- **THEN** every answer is 401 with `detail["mintkey:code"]` equal to `unauthenticated`, and the fake database session
  recorded no statement

#### Scenario: an unknown or expired session is refused before any statement
- **WHEN** the same seven requests carry the cookie `mintkey_session=x` and `validate_session` resolves it to None
- **THEN** every answer is 401 with `detail["mintkey:code"]` equal to `unauthenticated`, and the fake session recorded no
  statement

#### Scenario: a session of another tenant is refused before any statement
- **WHEN** the same seven requests carry a session cookie that `validate_session` resolves to an operator of tenant
  `bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb` who is not a platform admin
- **THEN** every answer is 403 with `detail["mintkey:code"]` equal to `permission_denied`, and the fake session recorded
  no statement

#### Scenario: a session of the tenant, or a platform admin, reaches the handler
- **WHEN** the same seven requests carry a session of tenant `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` and, in a second run,
  a session of tenant `bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb` whose operator is a platform admin
- **THEN** no answer is 401 or 403, and the fake session recorded at least one statement for each request (every handler
  runs `set_tenant_context`, a `SELECT set_config(...)`, before any lookup)

### Requirement: A background document describes the governance model
The file `docs/architecture/agent-governance.md` SHALL exist, SHALL be at most 6,000 characters, SHALL contain exactly the
level-two headings `## Terms`, `## Roles and operations`, `## Ownership and grants`, `## Access requests`,
`## Agent-supplied targets` and `## Where it lives` in that order after its level-one title, and SHALL NOT contain the
words SHALL or MUST in capitals. The document is background only: the requirements are in the OpenSpec changes.

#### Scenario: the document has its shape
- **WHEN** the file is read
- **THEN** it exists, its length is at most 6,000 characters, its level-two headings are the six named above in that
  order, and neither `SHALL` nor `MUST` occurs in it
