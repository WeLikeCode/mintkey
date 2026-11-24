# Design: agent-service-tools

## Context

Facts at the base (staging `2c4c814`); the requirements name symbols, the anchors are for review only.

- MCP: `TOOLS` (`MCP/tools/jsonrpc.py:96`), `_handle_tools_list` (456), `_handle_tools_call` (461), `_dispatch_tool` (511);
  the REST path of a tool is `/v1/tools/<name without mintkey_>`. The ten tools now in `TOOLS` are `mintkey_bootstrap`,
  `mintkey_list_services`, `mintkey_discover`, `mintkey_describe_service`, `mintkey_get_openapi`, `mintkey_request_token`,
  `secret_put`, `secret_get`, `secret_list` and `secret_delete`.
- Existing tests build agent contexts without `role` and expect those ten tools; `apps/mcp-server/tests/test_tools_list_trim.py`
  patches `validate_agent_key` in `mcp_server.main` and `mcp_server.tools.jsonrpc`.
- The MCP server writes audit rows directly (`audit_emit`) and reaches admin-api through `AdminApiClient`.

## Relied on (given by the named change; not redefined here)

- `agent-service-routes`: `POST /v1/agent/services`, `GET /v1/agent/services`, `PATCH /v1/agent/services/{service_ref}` and
  `PUT /v1/agent/services/{service_ref}/credential`, with the bodies and answers of its requirements; a `service_ref` that is
  an id or a slug; error bodies in the agent convention, `code` and `title`.
- `agent-principal-and-egress`: the audit event type `agent.operation.denied` with payload `{agent_id, role, operation}`
  (`ev_agent_operation_denied`); this change writes it from the MCP server with the tool name as `operation`.
- `agent-roles-and-ownership`: `mintkey_models.roles.normalize_role(value: object) -> str`, and the `role` that the MCP agent
  context (`AgentContext`) carries from the key check (default `consumer`).

## Decisions

**D1. One registry.** `mcp_server.policy.roles` holds both name sets and the only function that refuses. A later change adds
its tool to `TOOLS`, a router and a REST path without editing the sets; the sets already name the three access-request tools
(every agent) and, for publishers, the grant and request-decision tools. `tools/list` is `TOOLS` filtered by `tool_allowed`,
so a name in a set but not in `TOOLS` is not listed.

**D2. Role per call.** The key check reads the role on every request, so an operator's change applies at once; the context's
role defaults to `consumer`.

**D3. Refusal.** `enforce_tool_role` refuses a tool for a role and writes `agent.operation.denied` with `operation` the tool
name (for example `mintkey_service_create`). REST: 403; JSON-RPC: the error `-32003` (a refused call, not a failed tool). A
name in neither set is refused for every role.

**D4. The caller's key is forwarded**, never the MCP server's own identity: admin-api authenticates the agent itself. A
transport failure or a 5xx answer of admin-api reaches the agent as 502 `mintkey:admin_api_unavailable`. The tools stay out
of the unauthenticated landing listing.

**D5. Argument checks happen first.** A missing required argument, an unknown key, or a `service_id` that is not a safe path
segment (`^[A-Za-z0-9_.-]{1,128}$`, not only dots) answers 422 `mintkey:invalid_params` without calling admin-api, so a
tool argument can never change the path it is forwarded to.

**D6. Added: tests assert membership.** The tests of this change check that a list contains the expected tool names and none
of the names of a role that may not see them, not that a list equals a fixed set, so the tools of later changes can be added
without editing them.

**Error body convention.** Agent-facing error bodies (every answer of a `/v1/agent/` route and every MCP tool result an
agent receives) use the MCP server's existing convention `{"code": "mintkey:<name>", "title": "<text>", ...extra fields}`;
the MCP server writes `"code": "mintkey:..."` in 98 places, for example `mintkey:auth_required`. Operator routes under
`/v1/tenants/...` keep admin-api's flat `{"mintkey:code": "<name>", "title": "<text>", ...}`. Codes keep their names; only
the key and the `mintkey:` prefix placement follow the audience.

## Interfaces

Given to `agent-granted-access`, `agent-access-requests`:

- `mcp_server.policy.roles`: `ROLE_FORBIDDEN_RPC_CODE`, `CONSUMER_TOOLS`, `PUBLISHER_TOOLS`, `agent_role`, `tool_allowed`,
  `enforce_tool_role` (signatures in the spec).
- `mcp_server.auth.agent_key.agent_key_from_request`, `AdminApiClient.agent_request`, the `-32003` mapping of a 403
  `mintkey:role_forbidden` answer, and the `x-mintkey-role` key of `tools.yaml`.
- The REST handler convention: `/v1/tools/<name without mintkey_>`, a handler that checks the role first, then arguments,
  then forwards.

## Failure cases

- No agent context: 401 `mintkey:auth_required`. A refused role: 403 and one event; when the event write raises, the refusal is
  still answered and the failure is logged, as in `agent-principal-and-egress`.
- A bad argument: 422, nothing forwarded. admin-api answering below 500: relayed with its status and JSON body; 500 or more,
  a transport error or a timeout: 502.

## Relation to the other changes

`agent-granted-access` and `agent-access-requests` add REST routers, `TOOLS` entries and `tools.yaml` entries, and share
forwarding helpers of their own; they do not edit `roles.py`. `admin-ui-agent-governance` does not touch the MCP server.

## Follow-ups

Out of scope here: a fetch-time re-check of an agent-owned `openapi_url` by MCP `get_openapi`, and a configurable quota of
services per agent.
