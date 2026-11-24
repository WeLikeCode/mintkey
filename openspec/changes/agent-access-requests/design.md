# Design: agent-access-requests

## Context

Facts at the base (staging `2c4c814`); the requirements name symbols.

- `tests/acceptance/test_sqlalchemy_mirror.py` needs a model for every `createTable` and reads `TENANT_SCOPED`;
  `test_openapi_parity.py` compares the router modules `main.py` imports with the snapshot.
- `delete_service` removes a service's children in application code and `DELETE FROM agents` deletes an agent, so rows
  that reference them need `ON DELETE CASCADE` (or `SET NULL`).
- The audit contract has an `ev_*` definition, a `oneOf` entry and a mapping entry per type; `target_type` has no request.
- Operator routes take the operator from `get_session_context` (None without a session cookie) and answer errors in the flat form.

## Relied on (given by the named change; not redefined here)

- `agent-granted-access`: `admin_api.services.agent_grants` (`decode_wire_id`, `grant_view`, `GRANT_ACTION_PATTERN`,
  `MIN_GRANT_TTL_SECONDS`, `MAX_GRANT_TTL_SECONDS`) and `mcp_server.tools.agent_forward` (`guard_agent_tool`,
  `forward_agent_call`, `invalid_params`, `matches_pattern`).
- `agent-principal-and-egress`: `AgentPrincipal`, `AgentApiError`, `require_agent_principal`, `require_publisher_principal`.
- `agent-service-routes`: `admin_api/api/agent.py` (`router`, prefix `/v1/agent`, extended with `include_router`) and
  `parse_agent_body`.
- `agent-service-tools`: `mcp_server.policy.roles` (`CONSUMER_TOOLS` and `PUBLISHER_TOOLS` already name the five tools),
  the `-32003` mapping, `AdminApiClient.agent_request`.
- `grant-expiry`: `Grantor`, `GrantRecord`, `GrantConflict`, `write_grant`, `grant_granted_audit_payload`,
  `agent_grant_max_ttl_seconds`. `agent-roles-and-ownership`: `services.owner_agent_id`. At the base, in
  `admin_api.auth.sessions`: `require_tenant_session` and `get_session_context` (`tenant-session-routes` applies the first to
  more routes).

## Decisions

**D1. Surfaces and rules.** Agent routes sit under `/v1/agent` (tenant and caller from the principal), operator routes use the
tenant session, no route takes both credentials; the rules live once in `admin_api.services.access_requests`, whose public
functions sweep overdue requests first (no scheduler). An approval is a grant from `write_grant` with the decider as grantor; every state change writes its event with the real actor.

**D2. One action per request.** `actions` is an array with `CHECK (cardinality(actions) = 1)`, so `grant_id` is
unambiguous.

**D3. The decider and what blocks a request.** An agent decides only requests for services it owns (`not_owner`, checked
before the status so a non-owner learns nothing) and never its own (`self_decision`, possible after an ownership transfer);
decision and cancel select `FOR UPDATE`, so the second of two writers sees a non-pending status, and every state-changing
UPDATE (sweep, cancel, deny, approve) carries `AND status = 'pending'`. A refusal writes nothing.

**D4. TTLs.** The requester asks for `ttl_seconds` from 60 to 7776000; a value above the cap is accepted and clamped at
approval. The decider's `ttl_seconds` is an integer in the same bounds, checked by `check_decision_ttl` on both decision
routes with the 422 `invalid_ttl` body of the surface (as `grant-expiry` does); a grant never outlasts the request's TTL or the cap.

**D5. Errors.** The rules raise `AccessRequestError(status_code, code, title, **detail)`; agent routes answer `{"code":
"mintkey:<code>", "title", ...}` through `AgentApiError`, operator routes `{"mintkey:code": <code>, "title", ...}`. A `GrantExpiryError` leaves the
request pending; any other failure propagates and the route's session rolls back.

**D6. Shapes.** Cancelling is a POST (the family has no DELETE); `all` means no status filter; agent routes and tools take a
`service_id` as a slug or a `svc_` wire id, the operator list as a `svc_` wire id only.

**D7. The snapshot edit is authorised.** Task 4.3 adds the one entry `"access_requests":
"/v1/tenants/{tenant_id}/access-requests"` to `tests/acceptance/openapi_snapshot.json`, nothing else, and ends with
`tests/acceptance/test_openapi_parity.py` passing. To a data-fixture question the answer is: allow exactly this entry.

**Error body convention.** Agent-facing error bodies (every answer of a `/v1/agent/` route and every MCP tool result an
agent receives) use the MCP server's existing convention `{"code": "mintkey:<name>", "title": "<text>", ...extra fields}`;
the MCP server writes `"code": "mintkey:..."` in 98 places, for example `mintkey:auth_required`. Operator routes under
`/v1/tenants/...` keep admin-api's flat `{"mintkey:code": "<name>", "title": "<text>", ...}`. Codes keep their names; only
the key and the `mintkey:` prefix placement follow the audience.

## Interfaces

Signatures, routes, tool schemas and error codes are in the two specs.

## Failure cases

- A refused call stores nothing: the functions never commit and the exception reaches the route's session (`get_db_session`
  rolls back on any exception), the call's sweep included; the next call that commits expires and audits those requests, and
  every function sweeps before it reads, so no answer shows an overdue request as `pending`. A decision on an
  expired request answers `request_not_pending` (status `expired`).
- A requester or service deleted: its requests go with it (no event). A grant revoked later keeps its approved request
  (`grant_id` null). admin-api unreachable from the MCP server: 502 `mintkey:admin_api_unavailable`.

## Relation to the other changes

Merges after `agent-granted-access`; `admin-ui-agent-governance` reads the operator API and the audit types.
