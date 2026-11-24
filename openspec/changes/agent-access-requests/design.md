# Design: agent-access-requests

## Context

Facts at the base (staging `2c4c814`); the requirements name symbols.

- `tests/acceptance/test_sqlalchemy_mirror.py` needs a model for every `createTable` and reads `TENANT_SCOPED`;
  `tests/acceptance/test_openapi_parity.py` compares the router modules `main.py` imports with the snapshot.
- `delete_service` removes a service's children in application code and `DELETE FROM agents` deletes an agent, so rows
  that reference them need `ON DELETE CASCADE` (or `SET NULL`).
- The audit contract has one `ev_*` definition per type, an entry in `oneOf` and one in `discriminator.mapping`;
  `target_type` and `actor_type` are closed enums (`actor_type` has `system`; `target_type` has no request).
- Operator routes take the operator from `get_session_context` (None without a session cookie) and answer errors as
  `{"mintkey:code": <code>, "title": <text>}`. Wire ids are `<prefix>_<26 Crockford characters>` (`admin_api.utils.wire_ids`).

## Relied on (given by the named change; not redefined here)

- `agent-granted-access`: `admin_api.services.agent_grants` (`decode_wire_id`, `grant_view`, `GRANT_ACTION_PATTERN`,
  `MIN_GRANT_TTL_SECONDS`, `MAX_GRANT_TTL_SECONDS`) and `mcp_server.tools.agent_forward` (`guard_agent_tool`,
  `forward_agent_call`, `invalid_params`, `matches_pattern`).
- `agent-principal-and-egress`: `AgentPrincipal`, `AgentApiError`, `require_agent_principal`, `require_publisher_principal`.
- `agent-service-routes`: `admin_api/api/agent.py` (`router`, prefix `/v1/agent`, extended with `include_router`).
- `agent-service-tools`: `mcp_server.policy.roles` (`CONSUMER_TOOLS` and `PUBLISHER_TOOLS` already name the five tools),
  the `-32003` mapping, `AdminApiClient.agent_request`.
- `grant-expiry`: `Grantor`, `GrantRecord`, `GrantConflict`, `write_grant`, `grant_granted_audit_payload`,
  `agent_grant_max_ttl_seconds`. `agent-roles-and-ownership`: `services.owner_agent_id`. `tenant-session-routes`:
  `require_tenant_session` on every tenant route (delivered before `agent-roles-and-ownership`, which this change follows).

## Decisions

**D1. Surfaces and rules.** Agent routes sit under `/v1/agent` (tenant and caller from the principal), operator routes use the
tenant session, no route takes both credentials; the rules live once in `admin_api.services.access_requests`, whose public
functions sweep overdue requests first (no scheduler). An approval is a grant from `write_grant` with the decider as grantor
and `expires_at = now + min(requested, approved, cap)`; every state change writes its event with the real actor.

**D2. One action per request.** `actions` stays an array with `CHECK (cardinality(actions) = 1)`, so `grant_id` is
unambiguous; a later change may lift the check. The tools take `action` (default `call`).

**D3. The decider and what blocks a request.** An agent decides only requests for services it owns (`not_owner`, checked
before the status so a non-owner learns nothing) and never its own (`self_decision`, possible after an ownership transfer);
the decision selects `FOR UPDATE`, so the second of two deciders sees a non-pending status. Create refuses an own service, a
live grant for the same action and a pending request; approval refuses an inactive requester and a `GrantConflict`, leaving
the request pending. A refusal writes nothing.

**D4. TTLs.** The requester asks for `ttl_seconds` from 60 to 7776000; a value above the cap is accepted and clamped at
approval. The decider's `ttl_seconds` is an integer in the same bounds, checked by `check_decision_ttl` on both decision
routes with the flat 422 `invalid_ttl` body (as `grant-expiry` answers a bad expiry); a grant never outlasts the request's own
TTL or the cap.

**D5. Errors.** The rules raise `AccessRequestError(status_code, code, title, **detail)`; agent routes answer `{"code":
"mintkey:<code>", "title", ...}` through `AgentApiError`, operator routes `{"mintkey:code": <code>, "title", ...}`; the
exceptions `invalid_expires_at` and `invalid_ttl` have the flat body on both surfaces. A `GrantExpiryError` leaves the
request pending; any other failure, an audit write included, propagates and the route's session rolls back.

**D6. Shapes and the service filter.** Cancelling is a POST (the family has no DELETE). Agent lists answer
`{"access_requests": [view, ...]}`; `all` means no status filter; `decided_by_id` follows `decided_by_type`. A `service_id`
is a slug or a `svc_` wire id on every agent route and tool, resolved inside the caller's tenant (`list_access_requests`
takes it as `service_ref`): an unknown slug filters to an empty list, on create it is 404. The operator list takes `status`
(or `all`), `requester_agent_id`, `owner_agent_id` and a `svc_` wire id as `service_id`, no slug.

**D7. Tests of other changes.** A consumer sees thirteen tools after this change, so the two tests of
`apps/mcp-server/tests/test_jsonrpc.py` that expect ten change in task 5.1.

**D8. The snapshot edit is authorised.** Task 4.3 adds the one entry `"access_requests":
"/v1/tenants/{tenant_id}/access-requests"` to `tests/acceptance/openapi_snapshot.json` and nothing else; its end state is
`tests/acceptance/test_openapi_parity.py` passing. If L4 raises a data-fixture question, the answer is: allow exactly this entry.

## Interfaces

Signatures, the request object, the routes and the tool schemas are in the requirements of `agent-access-requests` and
`agent-access-request-routes`. Error codes: `not_found`, `not_owner`, `self_decision`, `invalid_request` (`reason`),
`invalid_id` (`field`), `request_pending` (`request_id`), `already_granted`, `request_not_pending` (`status`),
`requester_not_active`, `grant_conflict`, `invalid_expires_at` and `invalid_ttl` (`reason`); an invalid body or query answers
422 `validation_failed`.

## Failure cases

- A refused create, cancel or decision writes nothing except the expiry events of requests that were overdue anyway; a sweep
  that finds nothing writes nothing. A decision on an expired request answers `request_not_pending` (status `expired`).
- A requester or service deleted: its requests go with it (no event). A grant revoked later keeps the approved request
  (`grant_id` becomes null). admin-api unreachable from the MCP server: 502 `mintkey:admin_api_unavailable`.

## Relation to the other changes

Merges after `agent-granted-access`. `admin-ui-agent-governance` reads the operator API above and the audit types.
