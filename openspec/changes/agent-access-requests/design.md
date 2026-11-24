# Design: agent-access-requests

## Context

Facts at the base (staging `2c4c814`); the requirements name symbols, the anchors are for review only.

- `tests/acceptance/test_sqlalchemy_mirror.py::test_liquibase_tables_have_sqlalchemy_models` requires a model in
  `mintkey_models/db.py` for every `createTable`, and `test_tenant_scoped_models_match_rls_test_table_list` reads
  `TENANT_SCOPED` of `tests/architecture/test_rls_coverage.py`; `tests/acceptance/test_openapi_parity.py` compares the
  router modules `main.py` imports with `tests/acceptance/openapi_snapshot.json`.
- `delete_service` removes a service's children in application code and `DELETE FROM agents` deletes an agent, so rows
  that reference them need `ON DELETE CASCADE` (or `SET NULL`) to keep both routes working.
- The audit contract has one `ev_*` definition per type, an entry in `oneOf` and one in `discriminator.mapping`; its
  `$defs.target_type` and `actor_type` are closed enums (`actor_type` already has `system`; `target_type` has no request).
- Operator routes take the operator from `get_session_context` (None without a session cookie) and answer errors as
  `{"mintkey:code": <code>, "title": <text>}`. Wire ids are `<prefix>_<26 Crockford characters>`
  (`admin_api.utils.wire_ids`, any prefix).

## Relied on (given by the named change; not redefined here)

- `agent-granted-access`: `admin_api.services.agent_grants` (`decode_wire_id`, `grant_view`, `GRANT_ACTION_PATTERN`,
  `MIN_GRANT_TTL_SECONDS`, `MAX_GRANT_TTL_SECONDS`) and `mcp_server.tools.agent_forward` (`guard_agent_tool`,
  `forward_agent_call`, `invalid_params`, `matches_pattern`).
- `agent-service-publishing`: `AgentPrincipal`, `AgentApiError`, `require_agent_principal`, `require_publisher_principal`,
  `admin_api/api/agent.py` and its route-family rules, `mcp_server.policy.roles` (`CONSUMER_TOOLS` and `PUBLISHER_TOOLS`
  already name the five tools), the `-32003` mapping, `AdminApiClient.agent_request`.
- `grant-expiry`: `Grantor`, `GrantRecord`, `GrantConflict`, `write_grant`, `grant_granted_audit_payload`,
  `agent_grant_max_ttl_seconds`. `agent-roles-and-ownership`: `services.owner_agent_id`. `tenant-session-routes`:
  `require_tenant_session` on every tenant route.

## Decisions

**D1. Agent surface**. Agent routes under `/v1/agent`, tenant and caller from the principal. Operators use
tenant-session routes; no agent route takes a session and no operator route takes an agent key.

**D2. Requests**. One row per request; status `pending`, `approved`, `denied`, `cancelled` or `expired`; one
pending request per requester and service (a partial unique index); pending requests end 72 hours after creation.
Requests for services of the caller's tenant only; the owner agent decides requests for its services, operators decide any
request, and a request for an operator-owned service is decided by operators only.

**D3. Expiry without a scheduler**. `expire_pending_requests` flips every overdue pending row of the tenant
and writes `access_request.expired` once per row (`actor_type` `system`); each public function calls it first, so a
read or a decision never sees a stale `pending`, and a create is never blocked by an overdue request.

**D4. Approval**. `expires_at = now + min(requested_ttl_seconds, approved ttl, cap)`; the grant is written
by `write_grant` with the decider as grantor (an operator grants as `operator`, the owner as `agent`), no constraints.

**D5. Audit**. Every state change writes its event with the real actor; an approval also writes
`agent.permission.granted`. The note a decider writes is stored and audited; credentials are never involved.

**D6. Added: one action per request.** `actions` stays an array with `CHECK (cardinality(actions) = 1)`, so
`grant_id` is unambiguous; a later change may lift the check. The tools take `action` (default `call`).

**D7. Added: the decider.** An agent decides only requests for services it owns (`not_owner` otherwise, `not_found` for an
unknown request) and never its own request (`self_decision`, which an ownership transfer can make possible). The
owner check comes before the status check, so a non-owner learns nothing about a request.

**D8. Added: what blocks a request.** At create: an own service (`invalid_request`, reason `own_service`), a live grant
for the same action (`already_granted`), a pending request (`request_pending`, with its id). At approval: a requester
that is no longer active (`requester_not_active`) and a `GrantConflict` (`grant_conflict`, the request stays pending, so
the decider can deny it or the requester cancel it). Nothing is written in any of these cases.

**D9. Added: concurrency.** A decision selects the request `FOR UPDATE`, so two deciders serialize and the second sees a
non-pending status (`request_not_pending` with the status).

**D10. Added: TTLs.** The requester asks for `ttl_seconds` from 60 to 7776000; a value above the current cap is accepted and
clamped at approval (`approved_ttl_seconds`). The decider's `ttl_seconds` has the same bounds.

**D11. Added: the service and its error mapping.** The rules raise `AccessRequestError(status_code, code, title, **detail)`
with a bare `code`; the agent routes answer `{"code": "mintkey:<code>", "title", ...}` through `AgentApiError`, the operator
routes `{"mintkey:code": <code>, "title", ...}`.

**D12. Added: cancel and operator filters.** Cancelling is a POST (the family has no DELETE). The operator list accepts
`status`, `service_id`, `requester_agent_id` and `owner_agent_id` (the admin UI uses them).

**D13. Added: tests of other changes.** Thirteen tools are listed to a consumer after this change, so the two tests of
`apps/mcp-server/tests/test_jsonrpc.py` that expect ten, and the lists in
`apps/mcp-server/tests/test_service_publishing_tools.py`, change in task 5.1.

## Interfaces

The module signatures, the request object, the routes and the tool schemas are in the requirements of
`agent-access-requests` and `agent-access-request-routes`, not repeated here. Agent error bodies carry `code`
`mintkey:<code>` and operator bodies `mintkey:code` `<code>`, with `title`: `not_found`, `not_owner`, `self_decision`,
`invalid_request` (`reason`), `invalid_id` (`field`), `request_pending` (`request_id`), `already_granted`,
`request_not_pending` (`status`), `requester_not_active`, `grant_conflict`; request bodies that fail validation answer 422
`validation_failed`.

## Failure cases

- Any refused create, cancel or decision writes nothing except the expiry events of requests that were overdue anyway.
- An expiry sweep that finds nothing writes nothing. A decision on an expired request answers `request_not_pending` with
  status `expired`.
- A requester or service deleted: its requests are deleted with it (no event). A grant revoked later keeps the approved
  request (`grant_id` becomes null).
- admin-api unreachable from the MCP server: 502 `mintkey:admin_api_unavailable`.

## Relation to the other changes

Merges after `agent-granted-access`. `admin-ui-agent-governance` reads the operator API above and the audit types.

## Follow-ups

Out of scope here: service API keys that outlive the grant an approval created, and showing a grant's `expires_at` in
`mintkey_describe_service`.

## Open questions

1. Should the owner be told when a request arrives? Recommendation: not here; a later change can add a notification, since
   today the owner polls `mintkey_list_incoming_access_requests`.
2. Should an approval accept constraints (rate limit, path prefix)? Recommendation: yes, later, with the same closed schema
   as `agent-granted-access`.
