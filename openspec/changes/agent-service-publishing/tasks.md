# Tasks: agent-service-publishing

Each task writes its tests first and sees them fail for the reason it names, then changes the code; a new module is
stubbed by the red step with the names and signatures of the spec (functions raise `NotImplementedError`). Run the touched
suites, `ruff check`, `mypy --strict` (`apps/admin-api` `src/admin_api/`, `packages/python/mintkey-models` `mintkey_models/`)
and `ruff check src/` in `apps/mcp-server`. No test needs a database, a network or a clock: DNS goes through `resolve_host`,
the vault through a fake `put_credential`.

Route tests build a `FastAPI()` with `agent_services.router`, `agent_api_error_handler` and `validation_error_handler`,
`get_db_session` overridden with a fake session (records `(str(statement), params)`, answers by substrings of the
statement, raises `IntegrityError` on request), `require_agent_principal` overridden to return `AgentPrincipal(<tenant
UUID>, <agent UUID>, "publisher")`, `get_vault_client` overridden with a fake, and `audit_emit`, `notify_change` and
`check_agent_target_url` patched at `admin_api.api.agent_services`. MCP tests patch `validate_agent_key` in `mcp_server.main`
and `mcp_server.tools.jsonrpc` as `apps/mcp-server/tests/test_tools_list_trim.py` does, and `AdminApiClient.agent_request`.

## 1. The egress policy

- [ ] 1.1 Tests first, new file `packages/python/mintkey-models/tests/test_egress.py` (`monkeypatch.setattr(egress,
  "resolve_host", ...)` and `setenv`), covering the two scenarios of "Agent-supplied URLs must be public https
  targets" (spec `agent-egress-policy`) and the deny-name reader; red stubs `packages/python/mintkey-models/mintkey_models/egress.py`. Then fill it in.

## 2. The agent principal

- [ ] 2.1 Tests first, new file `tests/unit/admin_api/test_agent_principal.py`, covering the four scenarios of "An agent
  key authenticates the /v1/agent routes": `admin_api.auth.agent_principal.AsyncSessionLocal` is patched with a factory
  of fake async-context-manager sessions, `internal.check_agent_key` with an `AsyncMock`, `audit_emit` at the module; the
  last scenario also runs `tests/unit/admin_api/test_validate_agent_key_errors.py` unchanged. Red stubs the module
  `apps/admin-api/src/admin_api/auth/agent_principal.py`. Then fill it in, and in
  `apps/admin-api/src/admin_api/api/internal.py` move the lookup, the verify and the expiry branches of
  `validate_agent_key` into `check_agent_key(session, api_key)` (returning the row or the response it answered
  with, role read as `getattr(row, "role", None)`), so that `validate_agent_key` answers exactly as before (the verify
  still goes through `internal._verify_argon2`).

## 3. The service routes

- [ ] 3.1 Tests first, new file `tests/unit/admin_api/test_agent_services.py`, covering the scenarios of the requirements "A
  publisher creates a service" and "A publisher lists and updates only its own services". The fake session answers a
  statement containing `FROM services` with the service row (with `owner_agent_id`, `base_url`, `auth_scheme` and a
  `credential_set` flag) and one containing `FROM credentials` with a row or None. Red stubs
  `apps/admin-api/src/admin_api/services/agent_publishing.py` (`require_owned_service`, `service_view`) and creates the
  empty modules `apps/admin-api/src/admin_api/api/agent_services.py` (a `router` with no routes) and
  `apps/admin-api/src/admin_api/api/agent.py`. Then fill them in; the service id is derived as `create_service` of
  `apps/admin-api/src/admin_api/api/services.py` does (`_new_svc_id`, 128-bit decode).

- [ ] 3.2 Tests first, new file `tests/unit/admin_api/test_agent_credential.py`, covering the three scenarios of "A
  credential is written, never read, and bound to its target" (the fake vault records its `put_credential` call and
  can raise). Then add the PUT route to `apps/admin-api/src/admin_api/api/agent_services.py` (it takes the `Request`, reads `await
  request.json()` and validates by hand with fixed 422 titles; no request model), with the statements of
  steps 3b to 4 of `create_credential` in `apps/admin-api/src/admin_api/api/credentials.py` (same SQL, no operator
  checks), passing `egress_scope="public"` to `put_credential` as design D6 says; the fake `put_credential` records that
  keyword.

## 4. Wiring and isolation

- [ ] 4.1 Tests first, new file `tests/unit/admin_api/test_agent_routes_isolation.py` (builds `create_app()` with
  `MINTKEY_AUDIT_HMAC_KEY` and `MINTKEY_VAULT_BACKEND=sqlite` set as `tests/architecture/test_authz_coverage.py` does,
  walks the routes and their dependency trees, sends the cookie-less POST with `httpx.ASGITransport`, and reads
  `tests/acceptance/openapi_snapshot.json`), covering the two scenarios of "The agent routes are separate from the
  operator routes". Then in `apps/admin-api/src/admin_api/main.py` import `router as agent_router` from
  `admin_api.api.agent`, include it, register `agent_api_error_handler` for `AgentApiError` and call
  `csrf_exempt("/v1/agent")`; in `agent.py` include the `agent_services` router. The snapshot file
  `tests/acceptance/openapi_snapshot.json` is a data fixture: adding `"agent": "/v1/agent"` needs a person's answer.

## 5. The MCP role registry and tools

- [ ] 5.1 Tests first, new file `apps/mcp-server/tests/test_roles_registry.py`, covering the one scenario of "The role
  registry decides which tools an agent sees and may call" (spec `agent-tool-roles`) (a fake session records the `audit_emit` call patched at
  `mcp_server.policy.roles`). Red stubs `apps/mcp-server/src/mcp_server/policy/roles.py`. Then fill it in.

- [ ] 5.2 Tests first, new file `apps/mcp-server/tests/test_service_publishing_tools.py`, covering the four scenarios of
  "The publisher tools reach admin-api with the caller's key" (JSON-RPC through `create_app()` and `httpx.ASGITransport`
  as `test_tools_list_trim.py` does; REST by the same client with `Authorization: Bearer mk_agent_x`; `tools.yaml` through
  `yaml.safe_load`). Then: add `agent_key_from_request` to `apps/mcp-server/src/mcp_server/auth/agent_key.py` and
  `agent_request` to `apps/mcp-server/src/mcp_server/admin_api_client.py`; create
  `apps/mcp-server/src/mcp_server/tools/service_publishing.py` (four REST routes) and include its router in
  `apps/mcp-server/src/mcp_server/main.py`; in `apps/mcp-server/src/mcp_server/tools/jsonrpc.py` add the four `TOOLS`
  entries (no `title` key, as `test_tools_list_no_titles` checks) and `_dispatch_tool` branches, pass the caller's role to `_handle_tools_list` (default `consumer`, so existing
  callers work) and map a 403 `mintkey:role_forbidden` upstream answer to the `-32003` error in `_handle_tools_call`;
  add the four entries to `docs/architecture/contracts/mcp/tools.yaml`. The existing `apps/mcp-server/tests/test_jsonrpc.py`
  (ten tools for a context without a role) passes unchanged.

## 6. The audit contract

- [ ] 6.1 Tests first, new file `tests/unit/admin_api/test_audit_schema_publishing.py` (loads
  `docs/architecture/contracts/events/audit-event.schema.json`), covering the scenario "the contract lists them"; it fails
  before the change. Then edit the schema file. The admin UI's audit filter list is not changed here.
