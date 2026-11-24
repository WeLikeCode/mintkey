# Agent service tools

## Purpose

Four MCP tools let a publisher agent create, update and list its own services and write a service credential, by forwarding
its own key to the routes of `agent-service-routes`.

## ADDED Requirements

### Requirement: The publisher tools reach admin-api with the caller's key
`mcp_server/auth/agent_key.py` SHALL give `agent_key_from_request(request: Request) -> str | None` (the `mk_agent_...` token of
an `Authorization: Bearer` header, else None); `AdminApiClient.agent_request(method: str, path: str, api_key: str, json:
dict[str, Any] | None = None) -> httpx.Response` (10 s timeout) SHALL send `Authorization: Bearer <api_key>`. `TOOLS` SHALL
list these tools, each with `additionalProperties: false` (REST path `/v1/tools/<name without mintkey_>`):
`mintkey_service_create` (POST `service_create`; required `name`, `base_url`, `auth_scheme`; optional `display_name`,
`description`, `openapi_url`), `mintkey_service_update` (POST `service_update`; required `service_id`; optional `base_url`,
`auth_scheme`, `display_name`, `description`, `openapi_url`), `mintkey_service_set_credential` (POST
`service_set_credential`; required `service_id`, `value`; optional `header_name`, `query_param`) and `mintkey_list_my_services`
(GET `list_my_services`; no arguments); their results are the route bodies. `tools/call` of a tool the role refuses SHALL
answer a JSON-RPC error `-32003` with the REST body as `data`. Each REST handler in `mcp_server/tools/service_publishing.py`
SHALL answer 401 `{"code": "mintkey:auth_required", "title": "Agent key required"}` without a context, call
`enforce_tool_role`, check the arguments (a missing required one, an unknown key, or a `service_id` that does not match
`^[A-Za-z0-9_.-]{1,128}$` or is only dots, answers 422 `{"code": "mintkey:invalid_params", "title": "Invalid parameters",
"detail": <text>}` without calling admin-api), and forward with the caller's
key, the `service_id` percent-encoded in the path, relaying a status below 500 with its JSON body (`{}` when it is not
JSON) and answering 502 `{"code": "mintkey:admin_api_unavailable", "title": "Admin API unavailable"}` for a status of 500 or more or any
exception. The
forwards are `POST /v1/agent/services`, `PATCH /v1/agent/services/<service_id>`, `PUT
/v1/agent/services/<service_id>/credential` (body `value`, `header_name`, `query_param`) and `GET /v1/agent/services`; for
the update and the credential tool the body holds every argument except `service_id`.

#### Scenario: the list and the call follow the role
- **WHEN** `tools/list` runs for a context with role `consumer`, with no role, and with role `publisher`; and a consumer
  calls `mintkey_service_create`
- **THEN** the first two lists contain the ten existing names and none of the four new names; the publisher's list contains
  the ten and the four; the call answers a JSON-RPC error `-32003` whose `data.code` is `mintkey:role_forbidden`, with one
  `agent.operation.denied` event whose operation is `mintkey_service_create` and no `agent_request` call

#### Scenario: a publisher call is forwarded
- **WHEN** a publisher calls each tool with valid arguments and `agent_request` answers 200 or 201 with a JSON body
- **THEN** it was called with `POST /v1/agent/services`, `PATCH /v1/agent/services/<id>`, `PUT
  /v1/agent/services/<id>/credential` and `GET /v1/agent/services`, the caller's key and the arguments (without
  `service_id` in the body), and each result is not an error and holds the body

#### Scenario: bad arguments and failures
- **WHEN** `mintkey_service_update` gets `service_id` `../internal/x`, `a/b`, `a?b`, `.`, `..` or no `service_id`, and
  `my-svc.v2`; `mintkey_service_create` gets an extra key `owner_agent_id`; and `agent_request` answers 400 `target_not_allowed`,
  500, or raises `httpx.ConnectError`
- **THEN** the first seven answer 422 with `{"code": "mintkey:invalid_params", "title": "Invalid parameters", "detail": ...}`
  without an `agent_request` call, `my-svc.v2` is forwarded to `PATCH /v1/agent/services/my-svc.v2`, and the REST answers are
  400 with that body, then 502 `{"code": "mintkey:admin_api_unavailable", "title": "Admin API unavailable"}` twice

#### Scenario: a request without an agent key
- **WHEN** a REST tool path is called with no agent context, and with a context whose request has no `Authorization` header
- **THEN** both answer 401 `{"code": "mintkey:auth_required", "title": "Agent key required"}` and no `agent_request` call was made

### Requirement: The contract lists the four tools
`docs/architecture/contracts/mcp/tools.yaml` SHALL list `mintkey_service_create`, `mintkey_service_update`,
`mintkey_service_set_credential` and `mintkey_list_my_services` with the key `x-mintkey-role: "publisher"` and, in each
`input_schema.properties`, the same keys as the tool's `TOOLS` `inputSchema.properties`.

#### Scenario: the contract lists the tools
- **WHEN** `tools.yaml` is loaded
- **THEN** the four tools have `x-mintkey-role` `publisher`, and each `input_schema.properties` has the keys of its `TOOLS`
  entry's `inputSchema.properties`
