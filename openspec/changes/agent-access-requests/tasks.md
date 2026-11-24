# Tasks: agent-access-requests

Each task writes its tests first and sees them fail for the reason it names, then changes the code; the red step stubs a
new module with the names and signatures of the spec (functions raise `NotImplementedError`). Run the touched
suites, `ruff check`, `mypy --strict` (`apps/admin-api`, `packages/python/mintkey-models`) and `ruff check src/` in
`apps/mcp-server`; `test_sqlalchemy_mirror.py` must pass after task 1.1 and `test_openapi_parity.py` after task 4.3 (both in
`tests/acceptance/`, in the L4 gate). No test needs a database, a network or a clock.

Service tests use a fake session whose `async execute(statement, params=None)` records `(str(statement), params)`, answers
by substrings of the statement (`FROM services`, `FROM agents`, `FROM permission_grants`, `FROM service_access_requests`,
`UPDATE service_access_requests`, `FOR UPDATE`; an UPDATE may answer no row), counts `commit` and `rollback` calls and can
raise `IntegrityError`; `audit_emit` and `write_grant` are patched at `admin_api.services.access_requests`, and
`set_tenant_context` at the route module under test. Agent route tests build a `FastAPI()` with the router under
`APIRouter(prefix="/v1/agent")`, `agent_api_error_handler` and `validation_error_handler`, `require_agent_principal`
overridden to return an `AgentPrincipal`, and the service functions patched at `admin_api.api.agent_access_requests`. Operator
route tests override `get_db_session`, `require_tenant_session` (a no-op) and `get_session_context` (returning
`types.SimpleNamespace(operator_id=<UUID>, tenant_id=<UUID>)`) and patch the service functions at `admin_api.api.access_requests`.
MCP tests patch `validate_agent_key` in `mcp_server.main` and `mcp_server.tools.jsonrpc` as
`apps/mcp-server/tests/test_tools_list_trim.py` does, and `AdminApiClient.agent_request`.

## 1. The schema

- [ ] 1.1 Tests first, new file `tests/unit/admin_api/test_access_requests_migration.py` (paths from
  `Path(__file__).resolve().parents[3]`, `yaml.safe_load`, `from mintkey_models import db`), covering the two scenarios of
  "The schema stores access requests"; it fails before the change. Then create
  `apps/admin-api/db/changelog/032-service-access-requests.yaml` (changesets `032-service-access-requests`,
  `-checks`, `-indexes`, `-rls`, `-grant`, each with a rollback; the RLS text copies `004-services.yaml`), append its include to
  `apps/admin-api/db/changelog/db.changelog-master.yaml`, add `ServiceAccessRequest` to
  `packages/python/mintkey-models/mintkey_models/db.py` and `"service_access_requests"` to the set `TENANT_SCOPED` in
  `tests/architecture/test_rls_coverage.py` (only the set changes). End state: `test_sqlalchemy_mirror.py` passes.

## 2. The audit contract

- [ ] 2.1 Tests first, new file `tests/unit/admin_api/test_audit_schema_access_requests.py` (loads
  `docs/architecture/contracts/events/audit-event.schema.json`), covering the scenario "the contract lists them"; it fails
  before the change. Then edit the schema file. The admin UI's audit filter list is `admin-ui-agent-governance`'s.

## 3. The rules

- [ ] 3.1 Tests first, new file `tests/unit/admin_api/test_access_requests_create.py`, covering the first scenario of "Pending
  requests end after 72 hours" and the four of "An agent asks for access to a service". Red stubs
  `apps/admin-api/src/admin_api/services/access_requests.py` with every name of the spec (`PENDING_WINDOW_SECONDS`,
  `AccessRequestError`, `access_request_view`, `approved_ttl_seconds`, `expire_pending_requests`, `create_access_request`,
  `cancel_access_request`, `decide_access_request`, `list_access_requests`, `get_access_request`). Then fill in the expiry,
  the view, the error class and `create_access_request`; the request id is `uuid.uuid4()`, its wire form
  `db_uuid_to_wire(id, "areq")`.

- [ ] 3.2 Tests first, new file `tests/unit/admin_api/test_access_requests_decide.py`, covering the two scenarios of "A requester
  cancels its own pending request", the eight scenarios of "The owner or an operator decides a request" (with
  `monkeypatch.setenv` and `delenv` for `MINTKEY_AGENT_GRANT_MAX_TTL`; the sweep scenario makes the fake `UPDATE` return the
  request), the two scenarios of "Requests are listed by their audience" and the second scenario of "Pending requests end after 72
  hours" (all five functions). Then fill in
  `cancel_access_request`, `decide_access_request`, `list_access_requests` and `get_access_request` in
  `apps/admin-api/src/admin_api/services/access_requests.py`.

## 4. The routes

- [ ] 4.1 Tests first, new file `tests/unit/admin_api/test_agent_access_requests_routes.py`, covering the six scenarios of
  "The agent request routes" other than the route table (a consumer principal for the first, a publisher for the others; the
  consumer scenario patches `admin_api.auth.agent_principal.AsyncSessionLocal` and `audit_emit` as
  `test_agent_role_refusal.py` in that directory does). Red creates `apps/admin-api/src/admin_api/api/agent_access_requests.py`
  with a `router` and no routes. Then add the five routes (bodies with `extra="forbid"` and `StrictInt` for the create `ttl_seconds`; the
  `ttl_seconds` of a decision typed `object` and passed to `check_decision_ttl`) and in `apps/admin-api/src/admin_api/api/agent.py`
  `router.include_router(agent_access_requests.router)`.

- [ ] 4.2 Tests first, new file `tests/unit/admin_api/test_access_requests_operator_routes.py`, covering the three scenarios of
  "The operator request routes" other than the registration one (the no-session scenario builds the router without the
  `require_tenant_session` override and with its real 401). Red creates `apps/admin-api/src/admin_api/api/access_requests.py`
  with the `router` and no routes. Then add the four routes.

- [ ] 4.3 Tests first, new file `tests/unit/admin_api/test_access_requests_isolation.py` (builds `create_app()` with
  `MINTKEY_AUDIT_HMAC_KEY` and `MINTKEY_VAULT_BACKEND=sqlite` set as `tests/unit/admin_api/test_agent_routes_isolation.py`
  does, walks the routes and their dependency trees, reads `apps/admin-api/src/admin_api/main.py` as text and
  `tests/acceptance/openapi_snapshot.json`), covering the route-table scenario of "The agent request routes" and the
  registration scenario of "The operator request routes". Then in `apps/admin-api/src/admin_api/main.py` import and include
  `router as access_requests_router`. In the same task edit the data fixture `tests/acceptance/openapi_snapshot.json`: add
  exactly the entry `"access_requests": "/v1/tenants/{tenant_id}/access-requests"` before `"agent"` (keys are sorted;
  `agent-service-routes` added `"agent"`) and change no other line. Design D7 authorises this edit. End state:
  `tests/acceptance/test_openapi_parity.py` and the new test pass.

## 5. The tools

- [ ] 5.1 Tests first, new file `apps/mcp-server/tests/test_access_request_tools.py`, covering the five scenarios of "The
  request tools reach the routes with the caller's key" (JSON-RPC through `create_app()` and `httpx.ASGITransport`; REST by
  the same client with `Authorization: Bearer mk_agent_x`; `tools.yaml` through `yaml.safe_load`). In the existing
  `apps/mcp-server/tests/test_jsonrpc.py` the tests `test_tools_list_with_auth_returns_tools` and `test_tools_list_count_is_10`
  (a context without a role is a consumer) now expect 13 tools; other test files assert membership and stay. Then create
  `apps/mcp-server/src/mcp_server/tools/access_requests.py` (five REST handlers over `guard_agent_tool` and
  `forward_agent_call`), include its router in `apps/mcp-server/src/mcp_server/main.py`, add the five `TOOLS` entries (no
  `title` key, as `test_tools_list_no_titles` checks) and `_dispatch_tool` branches in `apps/mcp-server/src/mcp_server/tools/jsonrpc.py`,
  and add the five entries to `docs/architecture/contracts/mcp/tools.yaml`.
