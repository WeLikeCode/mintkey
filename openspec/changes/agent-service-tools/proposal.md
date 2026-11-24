# A publisher agent reaches its service routes through four MCP tools

## Why

Agents use Mintkey through the MCP server with their key; they do not call admin-api themselves. The routes of
`agent-service-routes` therefore need MCP tools, and which agent may see and call which tool needs one place that decides.
This change adds that place, the role registry, and the four tools of the publisher role.

## What Changes

- `mcp_server.policy.roles` is the one registry of which role may call which tool: `tools/list` shows a role only its tools,
  and a refused call answers 403 `mintkey:role_forbidden` (JSON-RPC error `-32003`) and writes `agent.operation.denied`
  with the tool name as the operation. The sets already name the tools of the later changes.
- Four tools, `mintkey_service_create`, `mintkey_service_update`, `mintkey_service_set_credential` and
  `mintkey_list_my_services`, for the `publisher` role, forwarding the caller's own key to the `/v1/agent/services` routes
  (`AdminApiClient.agent_request`, `agent_key_from_request`).
- `docs/architecture/contracts/mcp/tools.yaml` lists the four tools with `x-mintkey-role`.

## Capabilities

### New Capabilities
- `agent-tool-roles`: the role registry, the refusal and its record, the `tools/list` filter.
- `agent-service-tools`: the four tools, the forwarding client and the contract entries.

## Impact

- Changed: `apps/mcp-server/src/mcp_server/tools/jsonrpc.py`, `apps/mcp-server/src/mcp_server/main.py`,
  `apps/mcp-server/src/mcp_server/admin_api_client.py`, `apps/mcp-server/src/mcp_server/auth/agent_key.py`,
  `docs/architecture/contracts/mcp/tools.yaml`.
- New: `apps/mcp-server/src/mcp_server/policy/roles.py`, `apps/mcp-server/src/mcp_server/tools/service_publishing.py`; tests
  as listed per task in tasks.md.
- No change to admin-api, no migration, no change to `tests/acceptance/openapi_snapshot.json`. The existing
  `apps/mcp-server/tests/test_jsonrpc.py` (ten tools for a context without a role) passes unchanged: the four tools are
  publisher-only.
- Operators: a tool of the publisher role stays invisible to every agent until an operator makes it a publisher.
- Out of scope: the grant and access-request tools (later changes add their routers and `TOOLS` entries without editing the
  sets), a tool that deletes or transfers a service, sets a role, or reads or tests a credential.
- Depends on: `agent-service-routes` (the four routes and their answers), `agent-principal-and-egress` (the event
  `agent.operation.denied` in the audit contract) and `agent-roles-and-ownership` (`mintkey_models.roles.normalize_role`,
  and the `role` in the MCP agent context).
