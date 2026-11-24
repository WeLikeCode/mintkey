# Tasks: agent-service-tools

Each task writes its tests first and sees them fail for the reason it names, then changes the code; a new module is
stubbed by the red step with the names and signatures of the spec (functions raise `NotImplementedError`). Run the touched
suites and `ruff check src/` in `apps/mcp-server`. No test needs a database, a network or a clock. MCP tests patch
`validate_agent_key` in `mcp_server.main` and `mcp_server.tools.jsonrpc` as `apps/mcp-server/tests/test_tools_list_trim.py`
does, and `AdminApiClient.agent_request`. The lists in the tests assert membership (the names that must be present and the
names that must be absent), not equality with a fixed set.

## 1. The role registry

- [ ] 1.1 Tests first, new file `apps/mcp-server/tests/test_roles_registry.py`, covering the three scenarios of "The role
  registry decides which tools an agent sees and may call" (a fake session records the `audit_emit` call patched at
  `mcp_server.policy.roles`). Red stubs `apps/mcp-server/src/mcp_server/policy/roles.py` with every name of the spec. Then
  fill it in.

## 2. The forwarding client and the tools

- [ ] 2.1 Tests first, new file `apps/mcp-server/tests/test_service_publishing_tools.py`, covering the four scenarios of "The
  publisher tools reach admin-api with the caller's key" (JSON-RPC through `create_app()` and `httpx.ASGITransport` as
  `test_tools_list_trim.py` does; REST by the same client with `Authorization: Bearer mk_agent_x`). Then add
  `agent_key_from_request` to `apps/mcp-server/src/mcp_server/auth/agent_key.py` and `agent_request` to
  `apps/mcp-server/src/mcp_server/admin_api_client.py`; create `apps/mcp-server/src/mcp_server/tools/service_publishing.py`
  (four REST routes) and include its router in `apps/mcp-server/src/mcp_server/main.py`; in
  `apps/mcp-server/src/mcp_server/tools/jsonrpc.py` add the four `TOOLS` entries (no `title` key, as `test_tools_list_no_titles`
  checks) and `_dispatch_tool` branches, make `_handle_tools_list` filter by the caller's role (default `consumer`, so
  existing callers work) and map a 403 `mintkey:role_forbidden` answer to the `-32003` error in `_handle_tools_call`. The
  existing `apps/mcp-server/tests/test_jsonrpc.py` (ten tools for a context without a role) passes unchanged.

## 3. The contract

- [ ] 3.1 Tests first, new file `apps/mcp-server/tests/test_service_tools_contract.py` (`yaml.safe_load` of
  `docs/architecture/contracts/mcp/tools.yaml`; the `TOOLS` list imported from `mcp_server.tools.jsonrpc`), covering the
  scenario of "The contract lists the four tools"; it fails before the change. Then add the four entries to the file.
