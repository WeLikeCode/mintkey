# Agent grant tools

## Purpose

Three MCP tools let a publisher agent give, revoke and list access to the services it owns, by forwarding its own key to the
grant routes. Shared helpers hold the steps every agent tool of the later changes repeats.

## ADDED Requirements

### Requirement: Shared helpers forward an agent tool call
`mcp_server/tools/agent_forward.py` SHALL give:

```python
async def guard_agent_tool(session: AsyncSession, agent_ctx: dict[str, Any] | None, tool_name: str) -> JSONResponse | None
async def forward_agent_call(request: Request, method: str, path: str,
                             json_body: dict[str, Any] | None = None) -> JSONResponse
def invalid_params(detail: str) -> JSONResponse
def matches_pattern(value: object, pattern: str) -> bool
```
`guard_agent_tool` SHALL return 401 `{"code": "mintkey:auth_required"}` for no context, else the result of
`enforce_tool_role(session, agent_ctx, tool_name)` of `agent-service-tools` (a refusal records the tool name as the
operation). `forward_agent_call` SHALL take the key from
`agent_key_from_request` (401 `mintkey:auth_required` when None), call `AdminApiClient().agent_request(method, path, key,
json_body)`, relay a status below 500 with its JSON body (`{}` when it is not JSON), and answer 502
`{"code": "mintkey:admin_api_unavailable"}` for a status of 500 or more or any exception. `invalid_params(detail)` SHALL
answer 422 `{"code": "mintkey:invalid_params", "detail": detail}`. `matches_pattern` SHALL be true for a `str` that
`re.fullmatch` accepts and that is not made only of dots.

#### Scenario: guard and forward
- **WHEN** `guard_agent_tool` runs with no context, with a consumer context for `mintkey_grant_access`, and with a
  publisher context; and `forward_agent_call` runs with `agent_request` answering 201 JSON, 404 JSON, 200 with a non-JSON
  body, 500, and raising `httpx.ConnectError`, and with a request that has no agent key
- **THEN** the guard returns 401, a 403 `mintkey:role_forbidden` (one `agent.operation.denied` event whose operation is
  `mintkey_grant_access`) and None; the
  forward answers 201 with the body, 404 with the body, 200 with `{}`, 502, 502, and 401 with no `agent_request` call

#### Scenario: argument checks
- **WHEN** `matches_pattern` runs with `my-svc.v2` and `^[A-Za-z0-9_.-]{1,128}$`, then `..`, `.`, `a/b`, an empty string and
  `7`
- **THEN** the results are true, false, false, false, false and false

### Requirement: The publisher grant tools reach the routes with the caller's key
`TOOLS` in `mcp_server/tools/jsonrpc.py` SHALL list these tools, each with `additionalProperties: false`, and
`mcp_server/tools/access_grants.py` SHALL give their REST handlers (`router = APIRouter(prefix="/v1/tools")`, included
by `main.py`): `mintkey_grant_access` (POST `/v1/tools/grant_access`; required `service_id`, `agent_id`, `ttl_seconds`;
optional `action`, `constraints`; the schema of `constraints` is `{"type": "object", "additionalProperties": false}` with
the five properties `rate_limit`, `time_window`, `request_path_prefix`, `source_ip_allowlist` and `budget`, each `{"type":
"object"}`: the inner shapes are checked by the route, whose 422 the tool relays), `mintkey_revoke_access` (POST `/v1/tools/revoke_access`; required `grant_id`) and
`mintkey_list_service_grants` (GET `/v1/tools/list_service_grants`; required `service_id`). Each handler SHALL call
`guard_agent_tool` first, then reject a missing required argument, an unknown key, a `service_id` that fails
`matches_pattern` with `^[A-Za-z0-9_.-]{1,128}$`, an `agent_id` that fails `^agent_[0-9A-Za-z]{26,32}$`, a `grant_id` that
fails `^perm_[0-9A-Za-z]{26,32}$`, an `action` that fails `GRANT_ACTION_PATTERN`, a `ttl_seconds` that is not an integer
(a boolean is not one), and a `constraints` that is not an object, with `invalid_params` and no `agent_request` call; then
it SHALL call `forward_agent_call` with `POST /v1/agent/grants` and the arguments as the body, `POST
/v1/agent/grants/<grant_id percent-encoded>/revoke` with no body, and `GET /v1/agent/grants?service_id=<percent-encoded>`.
`tools/list` and `tools/call` SHALL follow the registry of `agent-service-tools` (`PUBLISHER_TOOLS` already names the three
tools). `docs/architecture/contracts/mcp/tools.yaml`
SHALL list the three tools with `x-mintkey-role: "publisher"` and, in each `input_schema.properties`, the keys of the
tool's `inputSchema.properties`.

#### Scenario: the list and the call follow the role
- **WHEN** `tools/list` runs for a consumer, a context with no role and a publisher, and a consumer calls
  `mintkey_grant_access`
- **THEN** the first two lists contain none of the three names and the publisher's list contains all three and the four
  names of `agent-service-tools` (the tests check membership, not equality); the call answers the JSON-RPC error `-32003`
  with `data.code` `mintkey:role_forbidden`, one `agent.operation.denied` event whose operation is `mintkey_grant_access`
  and no `agent_request` call

#### Scenario: a publisher call is forwarded
- **WHEN** a publisher calls each tool with valid arguments (`ttl_seconds` 3600, `service_id` `my-svc.v2`) and
  `agent_request` answers 201, 200 and 200 with JSON bodies
- **THEN** it was called with `POST /v1/agent/grants` and the five arguments as the body, `POST
  /v1/agent/grants/perm_.../revoke` with no body, and `GET /v1/agent/grants?service_id=my-svc.v2`, each with the caller's
  key, and each result is not an error and holds the body

#### Scenario: bad arguments and failures
- **WHEN** `mintkey_grant_access` gets `ttl_seconds` `"3600"`, `true` and `3600.5`, an `agent_id` `x`, an extra key
  `tenant_id`, no `service_id`, a `constraints` of `[]` and an `action` of `a b`; `mintkey_revoke_access` gets `grant_id`
  `../x`; `mintkey_list_service_grants` gets `service_id` `a/b`; and `agent_request` answers 409 with a body, 500, and
  raises `httpx.ConnectError`
- **THEN** the first ten answer 422 `mintkey:invalid_params` without an `agent_request` call; the REST answers are 409
  with that body, then 502 `mintkey:admin_api_unavailable` twice

#### Scenario: the contract lists the tools
- **WHEN** `tools.yaml` is loaded
- **THEN** the three tools have `x-mintkey-role` `publisher`, and each `input_schema.properties` has the keys of its `TOOLS`
  entry's `inputSchema.properties`, and the `constraints` property is an object schema with the five keys above
