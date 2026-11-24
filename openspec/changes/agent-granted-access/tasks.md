# Tasks: agent-granted-access

Each task writes its tests first and sees them fail for the reason it names, then changes the code; a new module is
stubbed by the red step with the names and signatures of the spec (functions raise `NotImplementedError`). Run the touched
suites, `ruff check`, `mypy --strict` (`apps/admin-api` `src/admin_api/`) and `ruff check src/` in `apps/mcp-server`. No
test needs a database, a network or a clock: the routes take `now` from a value the test can read back (the `now` argument
`write_grant` received), and every expiry is relative to it.

Route tests build a `FastAPI()` with `agent_grants.router` under `APIRouter(prefix="/v1/agent")` and `agent_api_error_handler`, `get_db_session` overridden with a fake session (records `(str(statement), params)`,
answers by substrings of the statement), `require_agent_principal` overridden to return `AgentPrincipal(<tenant UUID>,
<agent UUID>, "publisher")`, and `audit_emit`, `notify_change`, `set_tenant_context`, `write_grant`, `delete_grant`, `require_owned_service`
and `require_grant_target` patched at `admin_api.api.agent_grants` unless a scenario says it runs the real one. MCP tests
patch `validate_agent_key` in `mcp_server.main` and `mcp_server.tools.jsonrpc` as `apps/mcp-server/tests/test_tools_list_trim.py`
does, and `AdminApiClient.agent_request`.

## 1. Wire ids, the grantee and the grant view

- [ ] 1.1 Tests first, new file `tests/unit/admin_api/test_agent_grants_service.py`, covering the three scenarios of
  "Wire ids, the grantee and the grant view have one implementation" (a fake session answers the agent SELECT by
  substring; `GrantRecord` built directly); red stubs `apps/admin-api/src/admin_api/services/agent_grants.py`. Then
  fill it in.

## 2. The routes

- [ ] 2.1 Tests first, new file `tests/unit/admin_api/test_agent_grants_create.py`, covering the six scenarios of "An
  owner gives time-boxed access" (the cap scenario and the real-write-path scenario set `MINTKEY_AGENT_GRANT_MAX_TTL` with `monkeypatch.setenv` where they need the cap and run
  the real `admin_api.services.grants.write_grant` over the fake session, which answers the SELECT of the existing row with
  no row, or with a live row, as the scenario says). Red creates `apps/admin-api/src/admin_api/api/agent_grants.py` with a `router` and no routes. Then add
  `POST ""` (`Body` model with `extra="forbid"`, `Constraints` imported from `admin_api.api.permissions`, `ttl_seconds`
  as `StrictInt`, read with `parse_agent_body`) and map `GrantExpiryError` (the 422 body in the agent convention, with
  `max_ttl_seconds` for `expires_at_too_far`) and `GrantConflict` as the requirement says.

- [ ] 2.2 Tests first, new file `tests/unit/admin_api/test_agent_grants_revoke_list.py`, covering the scenarios of "An
  owner revokes any grant of its service" and "An owner lists the live grants of its service". Then add the two routes
  to `apps/admin-api/src/admin_api/api/agent_grants.py`: the revoke selects `service_id` from `permission_grants` by
  `id` and tenant, resolves the service with `require_owned_service(session, principal, db_uuid_to_wire(service_id,
  "svc"))`, calls `delete_grant`, writes the event and publishes the NOTIFY; the list reads `service_id` from `request.query_params` (a missing one raises the 422 of the requirement), selects the grants
  of the service with the live-grant condition and joins `agents` for `name`.

## 3. Wiring and isolation

- [ ] 3.1 Tests first, new file `tests/unit/admin_api/test_agent_grants_isolation.py` (builds `create_app()` with
  `MINTKEY_AUDIT_HMAC_KEY` and `MINTKEY_VAULT_BACKEND=sqlite` set as `tests/unit/admin_api/test_agent_routes_isolation.py`
  does, walks the routes and their dependency trees, reads `apps/admin-api/src/admin_api/main.py` as text, and sends the
  keyless request with `httpx.ASGITransport`; the consumer calls override `require_agent_principal` and patch
  `admin_api.auth.agent_principal.AsyncSessionLocal` and `audit_emit` as `tests/unit/admin_api/test_agent_role_refusal.py`
  does), covering the two scenarios of "The grant routes are agent routes for publishers" (the operation strings of the
  role refusals are the literals of the scenario). Then in
  `apps/admin-api/src/admin_api/api/agent.py` add `from admin_api.api import agent_grants` and
  `router.include_router(agent_grants.router)`. `tests/acceptance/openapi_snapshot.json` does not change (no module is
  imported by `main.py`); `tests/unit/admin_api/test_agent_routes_isolation.py` passes unchanged.

## 4. The forwarding helpers

- [ ] 4.1 Tests first, new file `apps/mcp-server/tests/test_agent_forward.py`, covering the two scenarios of "Shared
  helpers forward an agent tool call" (a fake session records the `audit_emit` call patched at
  `mcp_server.policy.roles`; `AdminApiClient.agent_request` patched with an `AsyncMock`; a `starlette.requests.Request`
  built from a scope with and without an `Authorization: Bearer mk_agent_x` header). Red stubs
  `apps/mcp-server/src/mcp_server/tools/agent_forward.py`. Then fill it in. `service_publishing.py` is not changed.

## 5. The tools

- [ ] 5.1 Tests first, new file `apps/mcp-server/tests/test_agent_grant_tools.py`, covering the four scenarios of "The
  publisher grant tools reach the routes with the caller's key" (JSON-RPC through `create_app()` and
  `httpx.ASGITransport`; REST by the same client with `Authorization: Bearer mk_agent_x`; `tools.yaml` through
  `yaml.safe_load`). The tests of this task assert
  membership (the names that must be present and absent), not equality or a count, and no existing test file changes. Then create
  `apps/mcp-server/src/mcp_server/tools/access_grants.py` (three REST handlers over `guard_agent_tool` and
  `forward_agent_call`), include its router in `apps/mcp-server/src/mcp_server/main.py`, add the three `TOOLS` entries (no `title` key,
  as `test_tools_list_no_titles` checks) and `_dispatch_tool` branches in `apps/mcp-server/src/mcp_server/tools/jsonrpc.py` (the loopback calls
  `/v1/tools/grant_access`, `/v1/tools/revoke_access` and `/v1/tools/list_service_grants`), and add the three entries to
  `docs/architecture/contracts/mcp/tools.yaml`. `apps/mcp-server/tests/test_jsonrpc.py` (ten tools for a context without a
  role) passes unchanged.
