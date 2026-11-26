# Tasks: tenant-session-routes

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Run
`ruff check src/` and `mypy --strict src/admin_api/` in `apps/admin-api` after the code step.

## 1. The seven handlers require the tenant session

- [x] 1.1 Tests first, new file `tests/unit/admin_api/test_tenant_session_routes.py`. It puts `apps/admin-api/src` and
  `packages/python/mintkey-models` on `sys.path` as `tests/unit/admin_api/test_cross_tenant_403.py` does, and sets
  `MINTKEY_AUDIT_HMAC_KEY` (64 `0` characters) and `MINTKEY_VAULT_BACKEND=sqlite` with `os.environ.setdefault` before it
  imports `admin_api.main`. Constants: `TA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"`, `TB = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"`,
  `AG = "agent_3C7JAGMBGR9EMRS2AVGXDHQXDX"`, `PM = "perm_3C7JAGMBGR9EMRS2AVGXDHQXDX"`.
  `test_every_tenant_scoped_route_has_the_tenant_session` covers the scenario "every tenant-scoped route has the
  dependency": it builds `create_app()`, collects the `APIRoute` objects (directly and under `original_router`, as
  `tests/architecture/test_authz_coverage.py` does), walks each route's `dependant` tree depth first for its `call`
  values, skips the two callback paths named in the spec, and asserts `require_tenant_session` is in every other
  matching route's set and that at least 50 routes matched; the failure message lists each missing `METHOD path`. It stays
  red until the seven handlers declare the dependency.
  The HTTP tests use `httpx.AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False))` and a file-local
  `RecordingSession` whose `async def execute(self, *a, **k)` appends the call to `self.statements` and returns a
  `MagicMock` whose `fetchone()` returns `None` and `fetchall()` returns `[]`. A helper `build_app(group)` returns a
  `FastAPI()` that includes, for `"grants"`, `admin_api.api.permissions.router`, `.tenant_permissions_router` and
  `admin_api.api.budget_consumers.router`, and for `"budgets"`, `admin_api.api.budgets.router`, with
  `app.dependency_overrides[get_db_session]` yielding one `RecordingSession` per app. The case table is
  `(group, method, path, json_body)` for: `grants` PATCH `/v1/tenants/{T}/agents/{AG}/permissions/{PM}` with
  `{"constraints": {"budget": null}}`, `grants` POST `.../agents/{AG}/permissions/{PM}/budget/reset`, `grants` GET
  `/v1/tenants/{T}/permissions/{PM}`, `grants` GET `/v1/tenants/{T}/permissions/{PM}/budget`, `grants` GET
  `/v1/tenants/{T}/budget-consumers`, `budgets` GET `/v1/tenants/{T}/agents/{AG}/permissions/{PM}/budget` and `budgets`
  POST `/v1/tenants/{T}/agents/{AG}/permissions/{PM}/budget/reset`, with `T = TA`.
  `test_requests_without_a_session_are_refused_before_any_statement` (parametrised over the table) sends each with no
  cookie and asserts 401, `resp.json()["detail"]["mintkey:code"] == "unauthenticated"` and an empty `statements` list.
  `test_an_unknown_or_expired_session_is_refused_before_any_statement` sends each with the cookie `mintkey_session=x` under
  `patch("admin_api.auth.sessions.validate_session", new=AsyncMock(return_value=None))` and asserts 401, code `unauthenticated`
  and no statement. `test_a_session_of_another_tenant_is_refused_before_any_statement` sends each with the cookie `mintkey_session=x` under
  `patch("admin_api.auth.sessions.validate_session", new=AsyncMock(return_value=SimpleNamespace(operator_id="op-1",
  tenant_id=TB)))` and `patch("admin_api.auth.sessions._is_operator_platform_admin", new=AsyncMock(return_value=False))`
  and asserts 403, code `permission_denied` and no statement. `test_a_session_of_the_tenant_or_a_platform_admin_reaches_the_handler`
  runs each twice, once with the session's tenant `TA` and `_is_operator_platform_admin` false, once with tenant `TB` and
  it true, and asserts the status is neither 401 nor 403 and `statements` is not empty. The first three HTTP
  tests stay red until the dependency answers before the handler runs; the fourth guards the reachable case.
  Then add `_authz: None = Depends(require_tenant_session)` as the last parameter of the seven handlers named in the spec
  (import `from admin_api.auth.sessions import require_tenant_session` in `budgets.py` and `budget_consumers.py`;
  `permissions.py` has it) and one docstring line in each saying the route requires the tenant session. Nothing else in
  these three modules changes.

## 2. The background document

- [x] 2.1 Tests first, new file `tests/unit/admin_api/test_agent_governance_doc.py` (path built from
  `os.path.dirname(__file__)` as `tests/unit/admin_api/test_cross_tenant_403.py` builds `REPO_ROOT`):
  `test_document_has_its_shape` covers the scenario "the document has its shape": it reads
  `docs/architecture/agent-governance.md`, asserts the file exists, `len(text) <= 6000`, that the lines starting with
  `## ` equal, in order, `## Terms`, `## Roles and operations`, `## Ownership and grants`, `## Access requests`,
  `## Agent-supplied targets`, `## Where it lives`, that the first line starts with `# `, and that neither `SHALL` nor
  `MUST` occurs. It fails because the file does not exist.
  Then create the document with a one-paragraph introduction and the six sections; plain prose and short tables, no
  normative keywords, no requirement. The content: the terms (operator, agent, service, credential, grant, owner,
  publisher and consumer roles, access request); the two roles and which operations each has (a consumer asks for access
  and reads its own requests; a publisher also creates and updates the services it owns, sets their credentials and
  grants access to them; no agent deletes a service, transfers ownership, sets a role or reads a credential); ownership
  (a service is owned by an operator or by one agent; transfer is an operator action) and grants (an optional expiry,
  the grantor on every grant, revocation reaching the egress proxy); access requests (one pending request per requester
  and service, a decision by the owner or an operator, a time-boxed grant on approval); agent-supplied targets (https and
  public addresses only, checked when stored and again when the proxy connects); and a table of where each part lives
  (admin-api `/v1/agent` routes and operator routes, the MCP server's tools, the vault adapter, the egress proxy, the
  broker, the admin UI) using the module names of this repository. Link to no URL outside the repository.
