# Design: agent-granted-access

## Context

Facts at the base (staging `2c4c814`); the requirements name symbols, the anchors are for review only.

- `grant_permission` (`ADM/api/permissions.py`) takes `action` as a free string (`PermissionGrantRequest.action: str`),
  checks that the agent exists in the tenant but not its status, and validates `constraints` with the closed model
  `Constraints` of the same module. `services` has no actions column (`CL/004-services.yaml`): an action is the string
  an agent passes to `mintkey_request_token` (default `call`, or `<verb>:<resource>`).
- `revoke_permission` deletes without reading. Service deletion removes a service's grants in application code
  (`delete_service`), and agent deletion is `DELETE FROM agents`.
- MCP tools reach their REST handler through the loopback in `_dispatch_tool` (`MCP/tools/jsonrpc.py`); the caller's
  context is `request.state.agent_context`, read by `get_agent_context` (`MCP/tools/discovery.py`).

## Relied on (given by the named change; not redefined here)

- `agent-principal-and-egress`: `AgentPrincipal(tenant_id, agent_id, role)`, `AgentApiError(status_code, body, headers)`,
  `require_agent_principal`, `require_publisher_principal` (403 `mintkey:role_forbidden`; the operation it records on a
  REST route is `"<METHOD> <path>"`).
- `agent-service-routes`: `admin_api.services.agent_publishing.require_owned_service(session, principal, service_ref)` (the
  owned service row, whose `id` is used here, or 404 `mintkey:not_found` / 403 `mintkey:not_owner`), `admin_api/api/agent.py`
  (`router`, prefix `/v1/agent`) and the route-family rules (no DELETE, no `transfer` or `role` in a path).
- `agent-service-tools`: `mcp_server.policy.roles` (`PUBLISHER_TOOLS` already names the three tools, `enforce_tool_role`,
  which records the tool name), `AdminApiClient.agent_request`, `agent_key_from_request`, the `-32003` mapping of a 403
  `mintkey:role_forbidden` answer, and the `x-mintkey-role` key of `tools.yaml`.
- Chain: `agent-service-tools` depends on `agent-service-routes`, which depends on `agent-principal-and-egress`; this change
  depends on `agent-service-tools` directly and reaches the other two through it.
- `grant-expiry`: `Grantor`, `GrantRecord`, `GrantConflict`, `write_grant`, `delete_grant`, `grant_granted_audit_payload`,
  `grant_revoked_audit_payload`, `grant_revoked_notify_payload`, `grant_wire_fields`, `GrantExpiryError` and
  `agent_grant_max_ttl_seconds`. `write_grant` checks the cap for an agent grantor, so this change never repeats it; it takes
  a transaction-scoped advisory lock on the (tenant, agent, service, action) key before it selects, so concurrent grants of
  one key run one after the other; and the flat 422 body `{"mintkey:code": "invalid_expires_at", "title", "reason"}` is the
  answer of its operator route for a bad expiry.
- `proxy-grant-revocation` consumes the NOTIFY that `grant_revoked_notify_payload` builds; this change only publishes it.

## Decisions

**D1. Agent surface**. Routes under `/v1/agent/grants` on a sub-router of `admin_api/api/agent.py`; the tenant
and the grantor come from the principal. The tools forward the caller's key; no tool takes a tenant or a grantor.

**D2. Only the owner grants and revokes**. Every route resolves the service through `require_owned_service`: a
service with another owner or with none gives 403 `mintkey:not_owner`, so grants on operator-owned services stay with
operators and a grantee (a publisher holding a grant) cannot grant onward.

**D3. The grantor and the cap**. The route computes `expires_at = now + ttl_seconds` once and passes the same
`now` to `write_grant`, so a TTL equal to the cap is accepted and one second more is refused with
`GrantExpiryError.reason == "expires_at_too_far"`.

**D4. Revocation reaches the proxy**. A revoke publishes `grant_revoked_notify_payload` on `mintkey:agent`, as
the operator route does.

**D5. Added: the action.** The body's `action` defaults to `call` and must match `^[A-Za-z0-9_.:-]{1,64}$`: the same
free string operators use, since a service has no action list.

**D6. Added: `ttl_seconds` instead of `expires_at`.** An integer from 60 to 7776000 (the ceiling of the cap). The route
answers the computed `expires_at`. A value above the configured cap answers the flat 422 body of `grant-expiry`
(`mintkey:code` `invalid_expires_at`, `reason` `expires_at_too_far`) with `max_ttl_seconds` (the current cap) added, so a
client reads one error shape on the operator and the agent surface.

**D7. Added: the grantee.** `agent_id` is an `agent_...` wire id of an active agent of the caller's tenant other than the
caller (`require_grant_target`); any role may be a grantee. There is no tool that lists agents: a publisher learns ids
from access requests (`agent-access-requests`) or from an operator (open question 1).

**D8. Added: revoking.** The owner may revoke any grant of its service, whoever gave it (an operator, a previous
owner or itself): after a transfer the grants stay, and the new owner answers for them. A grant that does not exist
is 404 with nothing written.

**D9. Added: one live grant per agent, service and action.** A repeat with another TTL while the grant is live answers
409 `mintkey:grant_conflict` (`grant-expiry` D7); the owner revokes first. The identical case (`created` false, 200, no
event) is a defensive branch that `ttl_seconds` cannot reach, since each call computes a new `expires_at`; its scenario
replaces `write_grant`, and the real write path is tested by the conflict scenario. Two concurrent requests for one key are
serialised by the advisory lock of `write_grant`: the second sees the first's row and answers 409, never a duplicate.

**D10. Added: the list shows live grants.** An expired grant is absent (`grant-expiry` D3), so the list selects only rows
with `expires_at IS NULL OR expires_at > now()`.

**D11. Added: shared forwarding helpers.** `mcp_server.tools.agent_forward` holds the steps every agent tool repeats (the
context and role check, then the forward with the 502 mapping); `agent-access-requests` uses it too. `service_publishing.py` is left as it is.

**D13. Added: the recorded operation.** The role refusal records the operation as the request line on a route (`POST
/v1/agent/grants`, `GET /v1/agent/grants`, `POST /v1/agent/grants/<grant id>/revoke`) and as the tool name on a tool
(`mintkey_grant_access`, `mintkey_revoke_access`, `mintkey_list_service_grants`).

**D14. Added: the tool's `constraints` schema.** An object with the five keys of the closed `Constraints` model, each an
object; the inner shapes stay with the route, so a change of the model never needs a tool schema change.

**D12. Audit actors.** Every event of these routes has `actor_type` `agent` and `actor_id` the caller (`agent.permission.granted`
and `.revoked` with the grantor and the revoker in the payload), never the request body.

## Interfaces

Given to `agent-access-requests` and `admin-ui-agent-governance`:

- `admin_api.services.agent_grants`: `decode_wire_id`, `require_grant_target`, `grant_view`, `GRANT_ACTION_PATTERN`
  (signatures in the spec).
- `mcp_server.tools.agent_forward`: `guard_agent_tool`, `forward_agent_call`, `invalid_params`, `matches_pattern`
  (signatures in the spec).
- Error bodies of the new routes carry `code`: 401 `mintkey:auth_required`; 403 `mintkey:role_forbidden`,
  `mintkey:not_owner`; 404 `mintkey:not_found`; 409 `mintkey:grant_conflict`; 422 `validation_failed`,
  `mintkey:invalid_id` (`field`), `mintkey:invalid_target` (`reason`: `invalid_id`, `self`, `agent_not_active`), and the
  flat body `mintkey:code` `invalid_expires_at` (`reason`, plus `max_ttl_seconds` for `expires_at_too_far`).

## Failure cases

- A refused body, target, TTL or ownership: nothing written, no event, no NOTIFY.
- `write_grant` raises `GrantConflict`: 409, nothing written. It raises `GrantExpiryError`: 422 as above.
- Revoking a grant that is already gone: 404, no event, no NOTIFY (the operator route answers 204 for the same case; the
  agent surface reports it).
- admin-api unreachable from the MCP server: 502 `mintkey:admin_api_unavailable`.
- A grantee deleted or revoked after the grant: the grant stays until it expires or is revoked; token issuance already
  requires an active agent.

## Relation to the other changes

Merges after `agent-service-tools` and `grant-expiry`. `agent-access-requests` creates its grants with the same
`write_grant` and uses `decode_wire_id` and `agent_forward`. `admin-ui-agent-governance` shows what these routes write
(`grantor_type` `agent`) through the operator API of `grant-expiry`.

## Follow-ups

Out of scope here: service API keys that outlive the grant they were created from, and showing a grant's `expires_at` in
`mintkey_describe_service`.

## Open questions

1. Should a publisher be able to look up agents of its tenant by name? Recommendation: no in this change; the access
   request flow gives the requester's id, and a directory would show every agent of the tenant to every publisher.
2. Should an owner be able to shorten or extend a live grant without revoking it? Recommendation: no; revoke and grant again
   keeps every change audited and reaching the proxy.
