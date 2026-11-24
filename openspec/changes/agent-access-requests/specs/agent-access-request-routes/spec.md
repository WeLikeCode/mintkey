# Agent access request routes

## Purpose

The agent and operator routes and the MCP tools over the access request rules of `agent-access-requests`: who may call
which route, how bodies and ids are checked, and how errors are answered.

## ADDED Requirements

### Requirement: The agent request routes
`admin_api/api/agent_access_requests.py` SHALL give a `router` (no prefix), included by `admin_api/api/agent.py`, with:
`POST /access-requests` (any agent: `require_agent_principal`; body `{service_id, ttl_seconds, action?, reason?}`, no other
key, `service_id` per the rule below, `ttl_seconds` an integer from 60 to 7776000, `action` matching `GRANT_ACTION_PATTERN`
(default `call`), `reason` a string of at most 500 characters (counted as sent, before the strip of `create_access_request`; a number is refused); answers 201 with the view); `GET /access-requests` (any agent; optional
`status` among the five statuses or `all`; the caller's own requests; answers 200 `{"access_requests": [view, ...]}`);
`POST /access-requests/{request_id}/cancel` (any agent; answers 200 with the cancelled view); `GET /incoming-access-requests`
(`require_publisher_principal`; `status` default `pending`, `all` allowed; optional `service_id`; the requests for services
the caller owns, through `owner_agent_id`; answers 200 `{"access_requests": [view, ...]}`) and `POST
/incoming-access-requests/{request_id}/decision` (publisher; body `{decision: "approve" | "deny", ttl_seconds?, note?}`, no
other key, `ttl_seconds` only with `approve` and checked by `check_decision_ttl`, `note` a string of at most 500 characters, counted as sent, decider
`Grantor("agent", <caller>)`; answers 200 with the decided view, plus `grant` for an approval). A route turns `all` into no
status filter before it calls `list_access_requests`, which takes a status or None.

The `service_id` rule (agent routes and tools): the create body field and the incoming-list query parameter match
`^[A-Za-z0-9_.-]{1,128}$` and are not only dots (else 422 `mintkey:validation_failed`; the MCP tools check only the pattern). A value
starting with `svc_` must decode with `decode_wire_id` (prefix `svc`), else 422 `mintkey:invalid_id` with `field` `service_id`;
any other value is a slug. Both resolve among the caller's tenant's services only. An unknown slug or an id of no such service
gives 404 `mintkey:not_found` on create and a 200 `{"access_requests": []}` on the incoming list.

Handlers SHALL call `set_tenant_context` first, read each body with `parse_agent_body`, check query parameters themselves (a bad
one: 422 `{"code": "mintkey:validation_failed", "title": "Invalid request body", "field": <name or null>}`, no input repeated),
decode ids with `decode_wire_id` (`areq`, `agent`; 422 `mintkey:invalid_id`, title "Invalid id", with `field`), and map
`AccessRequestError` to `AgentApiError` with `{"code": "mintkey:<code>", "title", ...detail}`, `invalid_expires_at` and
`invalid_ttl` included.

#### Scenario: the route table obeys the family rules
- **WHEN** the routes of `create_app()` are walked, and `admin_api/main.py` is read as text
- **THEN** the five paths and methods exist, each has `require_agent_principal` in its dependency tree and neither session
  dependency, the two incoming routes also depend on `require_publisher_principal`, no `/v1/agent/` route uses DELETE or
  has `transfer` or `role` in its path, and `main.py` does not contain `agent_access_requests`

#### Scenario: any agent asks, lists and cancels
- **WHEN** a consumer principal posts a valid request body, lists with `?status=pending` and `?status=all`, and cancels an id
- **THEN** the answers are 201, 200, 200 and 200 (the list calls bind the caller as requester and `pending`, then no status;
  both bodies are `{"access_requests": [...]}`), the cancel call passes the decoded request id and the caller and answers
  the view, `set_tenant_context` was called with the principal's tenant before each service function, and `?status=weird`
  answers 422 `mintkey:validation_failed` without the text `weird`

#### Scenario: refused bodies and ids
- **WHEN** the body has `ttl_seconds` 59, `"3600"` or 7776001, a `reason` of 501 characters or `7`, an extra key `agent_id`, no
  `service_id`; and the cancel id is `areq_xyz`
- **THEN** the bodies answer 422 `mintkey:validation_failed` (title `Invalid request body`, no answer text containing `agent_id`)
  and the id 422 `mintkey:invalid_id` (title `Invalid id`); no service function ran

#### Scenario: the service filter and the create reference
- **WHEN** a publisher lists incoming requests with `?service_id=payments`, `?service_id=svc_` plus a valid body,
  `?service_id=svc_xyz` (the patched `list_access_requests` raises `AccessRequestError` 422 `invalid_id` with `field`
  `service_id`), `?service_id=a/b` and `?service_id=..`; and a consumer posts a body with `service_id` `payments` and one with
  `a/b`
- **THEN** the first two list calls receive `service_ref` as sent with the caller as owner and answer 200; the third answers
  422 `mintkey:invalid_id` with `field` `service_id`; the fourth and fifth answer 422 `mintkey:validation_failed` with no service call;
  the first post passes `service_ref` `payments` to `create_access_request` and answers 201, the second answers 422
  `mintkey:validation_failed` with no call

#### Scenario: publishers decide, consumers do not
- **WHEN** a publisher lists incoming requests (no status, then `all`), approves with `ttl_seconds` 600, denies with a note,
  and sends `{"decision": "deny", "ttl_seconds": 60}`, `{"decision": "maybe"}`; and a consumer calls both incoming routes
- **THEN** the list binds the caller as owner and status `pending`, then all statuses; the decision calls pass
  `Grantor("agent", <caller>)`, the decision and the ttl (600); the two bad bodies answer 422 `mintkey:validation_failed`; the consumer gets
  403 `mintkey:role_forbidden` with one `agent.operation.denied` event per call (operations `GET
  /v1/agent/incoming-access-requests` and `POST /v1/agent/incoming-access-requests/<id>/decision` as sent)

#### Scenario: the decision ttl is checked
- **WHEN** a publisher approves with `ttl_seconds` 59, 7776001, `"600"` (a string), `true`, 60 and 7776000
- **THEN** the first four answer 422 with exactly `{"code": "mintkey:invalid_ttl", "title": "Invalid ttl_seconds",
  "reason": <reason>}`, the reason being `ttl_out_of_range` for 59 and 7776001 and `ttl_not_integer` for `"600"` and `true`,
  with `decide_access_request` not called; 60 and 7776000 reach `decide_access_request` as given

#### Scenario: errors keep their code
- **WHEN** the service function raises `AccessRequestError` 409 `request_not_pending` with `status` `approved`, and 422
  `invalid_expires_at` with `reason` `expires_at_in_past`, on the decision route
- **THEN** the answers are 409 with `{"code": "mintkey:request_not_pending", "title": ..., "status": "approved"}` and 422 with
  exactly `{"code": "mintkey:invalid_expires_at", "title": "Invalid expires_at", "reason": "expires_at_in_past"}`

### Requirement: The operator request routes
`admin_api/api/access_requests.py` SHALL give `router = APIRouter(prefix="/v1/tenants/{tenant_id}/access-requests")`,
imported by `main.py`, whose four routes depend on `require_tenant_session` and call `set_tenant_context(session,
tenant_id)` first: `GET ""` (filters `status` (a status or `all`: no filter), `service_id`, `requester_agent_id`,
`owner_agent_id`; ids decode with `decode_wire_id`; answers `{"access_requests": [...]}`), `GET "/{request_id}"`, `POST "/{request_id}/approve"` (`{ttl_seconds?,
note?}`, `ttl_seconds` checked by `check_decision_ttl` like the agent decision: integer, 60 to 7776000, else the flat 422
`invalid_ttl`) and `POST "/{request_id}/deny"` (`{note?}`), each body without other keys. The decider is `Grantor("operator", <operator id
of get_session_context>)`, with a None id when there is no context. `AccessRequestError` SHALL be answered as `{"mintkey:code":
<code>, "title", ...detail}`; a bad id 422 `{"mintkey:code": "invalid_id", "title", "field": <the parameter name>}`; a bad body or filter 422
`validation_failed`; the operator `service_id` filter takes a `svc_` wire id only (a slug or any other value that does not
decode with prefix `svc` is 422 `invalid_id` with `field` `service_id`). Operators decide any request.

#### Scenario: list and get
- **WHEN** an operator lists with `?status=pending&owner_agent_id=<agent wire id>`, with `?status=weird`, with
  `?service_id=svc_xyz`, `?service_id=payments`, `?service_id=svc_` plus a valid body, `?status=all`, and gets an existing and an
  unknown request id
- **THEN** `set_tenant_context` was called with the path's tenant before any statement; the first answers 200 with the
  views and the filters bound, then 422 `validation_failed`, 422 `invalid_id`, 422 `invalid_id`, 200 with the decoded
  service id bound, 200 with no status filter, 200 with the view and 404 `not_found`

#### Scenario: approve and deny as an operator
- **WHEN** an operator approves with `{"ttl_seconds": 600, "note": "ok"}` and denies another request, with a session context
  whose `operator_id` is a UUID
- **THEN** the approval calls `decide_access_request` with `Grantor("operator", <that id>)`, `approve`, 600 and the note, and
  answers 200 with the view and `grant`; the denial answers 200 with the view; a request that is not pending answers 409
  `request_not_pending`, an `AccessRequestError` 422 `invalid_expires_at` answers its flat body, and `ttl_seconds` 59
  answers the flat `invalid_ttl` body with `decide_access_request` not called; with no session context the decider is
  `Grantor("operator", None)`

#### Scenario: no session, extra keys
- **WHEN** a call has no `mintkey_session` cookie, and a body has `{"ttl_seconds": 60, "decision": "approve"}`
- **THEN** the first answers 401 with no statement, the body answers 422 `validation_failed`

#### Scenario: the router is registered once
- **WHEN** `main.py` is read as text, `tests/acceptance/openapi_snapshot.json` is loaded and
  `tests/acceptance/test_openapi_parity.py` runs
- **THEN** `main.py` imports `router as access_requests_router` from `admin_api.api.access_requests`, includes it once, the
  snapshot maps `access_requests` to `/v1/tenants/{tenant_id}/access-requests`, and the parity test passes

### Requirement: The request tools reach the routes with the caller's key
`TOOLS` in `mcp_server/tools/jsonrpc.py` SHALL list five tools with `additionalProperties: false`, and
`mcp_server/tools/access_requests.py` SHALL give their REST handlers (`router = APIRouter(prefix="/v1/tools")`, included by
`main.py`): `mintkey_request_access` (POST `request_access`; required `service_id`, `ttl_seconds`; optional `action`,
`reason`), `mintkey_list_my_access_requests` (GET `list_my_access_requests`; optional `status`),
`mintkey_cancel_access_request` (POST `cancel_access_request`; required `request_id`), `mintkey_list_incoming_access_requests`
(GET `list_incoming_access_requests`; optional `status`, `service_id`) and `mintkey_decide_access_request` (POST
`decide_access_request`; required `request_id`, `decision`; optional `ttl_seconds`, `note`). Handlers SHALL call
`guard_agent_tool`, reject with `invalid_params` (and no `agent_request` call) a missing required argument, an unknown key, a
`service_id` failing `matches_pattern` with `^[A-Za-z0-9_.-]{1,128}$`, a `request_id` failing `^areq_[0-9A-Za-z]{26,32}$`,
an `action` failing `matches_pattern` with `^[A-Za-z0-9_.:-]{1,64}$` (the value of `GRANT_ACTION_PATTERN`), a non-integer `ttl_seconds` (a boolean is not one), a
`decision` other than `approve` or `deny`, a `status` that is not one of the five statuses and `all` (any type), or a `reason`
or `note` that is not a string or has more than 500 characters; then call `forward_agent_call` with
`POST /v1/agent/access-requests` (arguments as the body), `GET /v1/agent/access-requests?status=...`, `POST
/v1/agent/access-requests/<id>/cancel`, `GET /v1/agent/incoming-access-requests?status=...&service_id=...` (given arguments only,
percent-encoded) and `POST /v1/agent/incoming-access-requests/<id>/decision` (`decision`, `ttl_seconds`, `note` as the body).
`docs/architecture/contracts/mcp/tools.yaml` SHALL list them with `x-mintkey-role` `consumer` (the first three) and `publisher`,
and `input_schema.properties` equal in keys to each `inputSchema.properties`.

#### Scenario: the lists equal the registry
- **WHEN** `tools/list` runs for a consumer and a publisher, after every change of the plan is merged
- **THEN** the consumer's names are the ten tools of the base plus `mintkey_request_access`,
  `mintkey_list_my_access_requests` and `mintkey_cancel_access_request` (13 names, equal to `CONSUMER_TOOLS` of
  `agent-service-tools`), the publisher's add the nine publisher-only tools, among them `mintkey_list_incoming_access_requests`
  and `mintkey_decide_access_request` (22 names, equal to `PUBLISHER_TOOLS`), and no entry has a `title` key

#### Scenario: roles
- **WHEN** a consumer calls `mintkey_decide_access_request` and `mintkey_list_incoming_access_requests`, and calls
  `mintkey_request_access` with valid arguments (`agent_request` answers 201)
- **THEN** the first two answer the JSON-RPC error `-32003` with `data.code` `mintkey:role_forbidden`, one
  `agent.operation.denied` event each (operations `mintkey_decide_access_request` and
  `mintkey_list_incoming_access_requests`) and no `agent_request` call; the third is forwarded and its result holds the body

#### Scenario: publisher calls are forwarded
- **WHEN** a publisher calls the five tools with valid arguments and `agent_request` answers 200 or 201
- **THEN** it was called with the methods and paths above, the caller's key and the bodies above (the decision body without
  `request_id`), and each result is not an error

#### Scenario: bad arguments and failures
- **WHEN** `mintkey_request_access` gets `ttl_seconds` `"3600"`, `true`, no `service_id`, a `service_id` `a/b`, an extra
  key `tenant_id`, a `reason` of 501 characters, a `reason` `7` and an `action` `a b`; `mintkey_decide_access_request` gets
  `decision` `maybe`, `request_id` `../x`, a `note` of 501 characters and a `note` `5`; `mintkey_list_my_access_requests` gets
  `status` `weird`; `mintkey_list_incoming_access_requests` gets `status` `["pending"]`; and `agent_request` answers 409 with
  a body, 500, and raises `httpx.ConnectError`
- **THEN** the first fourteen answer 422 `mintkey:invalid_params` without an `agent_request` call; the REST answers are 409
  with that body, then 502 `mintkey:admin_api_unavailable` twice

#### Scenario: the contract lists the tools
- **WHEN** `tools.yaml` is loaded
- **THEN** the five tools have the roles above and each `input_schema.properties` has the keys of its `TOOLS` entry
