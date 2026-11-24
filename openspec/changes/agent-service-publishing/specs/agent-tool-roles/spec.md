# Agent tool roles

## Purpose

Which MCP tools an agent sees and may call depends on its role. One registry decides, one function refuses and records the
refusal, and the publisher tools reach admin-api with the caller's own key.

## ADDED Requirements

### Requirement: The role registry decides which tools an agent sees and may call
`mcp_server.policy.roles` SHALL give:

```python
ROLE_FORBIDDEN_RPC_CODE: Final[int] = -32003
CONSUMER_TOOLS: Final[frozenset[str]]   # the ten tools now in TOOLS, plus mintkey_request_access,
                                        # mintkey_list_my_access_requests, mintkey_cancel_access_request
PUBLISHER_TOOLS: Final[frozenset[str]]  # CONSUMER_TOOLS plus mintkey_service_create, mintkey_service_update,
    # mintkey_service_set_credential, mintkey_list_my_services, mintkey_grant_access, mintkey_revoke_access,
    # mintkey_list_service_grants, mintkey_list_incoming_access_requests, mintkey_decide_access_request
def agent_role(agent_ctx: dict[str, Any] | None) -> str           # normalize_role(ctx.get("role"))
def tool_allowed(role: str, tool_name: str) -> bool
async def enforce_tool_role(session: AsyncSession, agent_ctx: dict[str, Any], tool_name: str) -> JSONResponse | None
```

`tool_allowed` SHALL be false for a name in neither set, and an unknown role SHALL use the consumer set. A later change adds
its tool to `TOOLS`, a router and a REST path without editing the sets. `enforce_tool_role` SHALL return None for an allowed
tool, and otherwise write `agent.operation.denied` (`actor_type` `agent`, payload `{agent_id, role, operation}`) and
return 403 `{"code": "mintkey:role_forbidden", "tool", "role", "required_role": "publisher", "hint"}`.

#### Scenario: the sets, allowed, refused and unknown
- **WHEN** the sets are read; `enforce_tool_role` runs for a publisher on `mintkey_service_create`, a consumer on it, a
  consumer on `mintkey_request_token` and a publisher on `mintkey_made_up`; and `agent_role` runs on a context with no
  role and one with `"admin"`
- **THEN** the sets hold the names above (13 and 22 names, none a delete, transfer, role or credential-read name); the
  results are None, a 403 with one audit event, None, and a 403 with one audit event; both roles read `consumer`

### Requirement: The publisher tools reach admin-api with the caller's key
`mcp_server/auth/agent_key.py` SHALL give `agent_key_from_request(request) -> str | None`; `AdminApiClient.agent_request(method:
str, path: str, api_key: str, json: dict | None = None) -> httpx.Response` (10 s timeout) SHALL send `Authorization: Bearer
<api_key>`. `TOOLS` SHALL list these tools, each with `additionalProperties: false` (REST path `/v1/tools/<name without
mintkey_>`): `mintkey_service_create` (POST `service_create`; required `name`, `base_url`, `auth_scheme`; optional
`display_name`, `description`, `openapi_url`), `mintkey_service_update` (POST `service_update`; required `service_id`; optional
`base_url`, `auth_scheme`, `display_name`, `description`, `openapi_url`), `mintkey_service_set_credential` (POST
`service_set_credential`; required `service_id`, `value`; optional `header_name`, `query_param`) and `mintkey_list_my_services`
(GET `list_my_services`; no arguments); their results are the route bodies. `tools/list` SHALL return only the tools
`tool_allowed` admits for the caller's role; `tools/call` of a refused tool SHALL answer a JSON-RPC error `-32003` with the
REST body as `data`. Each REST handler in `mcp_server/tools/service_publishing.py` SHALL answer 401 `mintkey:auth_required`
without a context, call `enforce_tool_role`, check the arguments (a missing required one, or a `service_id` that does not match
`^[A-Za-z0-9_.-]{1,128}$` or is only dots, answers 422 `mintkey:invalid_params` without calling admin-api), and forward with
the caller's key, the `service_id` percent-encoded in the path, relaying a status below 500 with its JSON body and answering
502 `mintkey:admin_api_unavailable` otherwise. `docs/architecture/contracts/mcp/tools.yaml` SHALL list the four tools with
`x-mintkey-role: "publisher"` and the same `properties` as the schemas.

#### Scenario: the list and the call follow the role
- **WHEN** `tools/list` runs for a context with role `consumer`, with no role, and with role `publisher`; and a consumer
  calls `mintkey_service_create`
- **THEN** the lists are the ten existing names twice, then those and the four new names; the call answers a JSON-RPC
  error `-32003` whose `data.code` is `mintkey:role_forbidden`, with one `agent.operation.denied` event and no
  `agent_request` call

#### Scenario: a publisher call is forwarded
- **WHEN** a publisher calls each tool with valid arguments and `agent_request` answers 200 or 201 with a JSON body
- **THEN** it was called with `POST /v1/agent/services`, `PATCH /v1/agent/services/<id>`, `PUT
  /v1/agent/services/<id>/credential` and `GET /v1/agent/services`, the caller's key and the arguments (without
  `service_id` in the body), and each result is not an error and holds the body

#### Scenario: bad arguments and failures
- **WHEN** `mintkey_service_update` gets `service_id` `../internal/x`, `a/b`, `a?b`, `.`, `..` or no `service_id`, and
  `my-svc.v2`; and `agent_request` answers 400 `target_not_allowed`, 500, or raises `httpx.ConnectError`
- **THEN** the first six answer 422 `mintkey:invalid_params` without an `agent_request` call, `my-svc.v2` is forwarded to
  `PATCH /v1/agent/services/my-svc.v2`, and the REST answers are 400 with that body, then 502
  `mintkey:admin_api_unavailable` twice

#### Scenario: the contract lists the tools
- **WHEN** `tools.yaml` is loaded
- **THEN** the four tools have `x-mintkey-role` `publisher`, and each `input_schema.properties` has the keys of its `TOOLS`
  entry's `inputSchema.properties`
