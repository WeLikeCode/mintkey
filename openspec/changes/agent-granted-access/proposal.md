# A publisher agent gives other agents access to the services it owns

## Why

Access to a service is given by an operator in the admin UI today. An agent that publishes a service for other agents
must ask a person every time one of them needs it, and the access never ends on its own. A publisher should be able to
give another agent of its tenant time-boxed access to a service it owns, see who has it, and take it back, inside
limits an operator can read in the audit log: the grant carries an expiry no later than the configured cap, the grantor
is the calling agent, and nobody but the owner grants or revokes on a service.

## What Changes

- New admin-api routes under `/v1/agent/grants`, attached to the agent router of `agent-service-routes`, for the
  `publisher` role: `POST /v1/agent/grants` (give access), `GET /v1/agent/grants?service_id=` (list the live grants of an
  owned service) and `POST /v1/agent/grants/{grant_id}/revoke`. They use `write_grant` and `delete_grant` of
  `grant-expiry` with `Grantor("agent", <agent id>)`, so the grantor is the key's agent and the expiry cap is enforced in
  one place.
- A grant needs `ttl_seconds` (60 to 7776000), an active grantee of the same tenant other than the caller, and an owned
  service; a live grant with another expiry is a conflict (revoke it first). Revoking works on any grant of an owned
  service and reaches the proxy through the NOTIFY of `grant-expiry`.
- Three MCP tools, `mintkey_grant_access`, `mintkey_revoke_access` and `mintkey_list_service_grants`, for the publisher
  role, forwarding the caller's key through a shared helper `mcp_server.tools.agent_forward`. The tool names are in the
  registry of `agent-service-tools` already; a refused call records the tool name in `agent.operation.denied`.
- Audit: the events `agent.permission.granted` and `agent.permission.revoked` carry the agent as actor. No new event type.

## Capabilities

### New Capabilities
- `agent-granted-access`: the agent grant routes, the grantee check and the grant view.
- `agent-grant-tools`: the shared forwarding helpers and the three tools.

## Impact

- Changed: `apps/admin-api/src/admin_api/api/agent.py` (one `include_router`),
  `apps/mcp-server/src/mcp_server/tools/jsonrpc.py`, `apps/mcp-server/src/mcp_server/main.py`,
  `docs/architecture/contracts/mcp/tools.yaml`.
- New: `apps/admin-api/src/admin_api/api/agent_grants.py`, `apps/admin-api/src/admin_api/services/agent_grants.py`,
  `apps/mcp-server/src/mcp_server/tools/agent_forward.py`, `apps/mcp-server/src/mcp_server/tools/access_grants.py`; tests
  as listed per task in tasks.md.
- No migration, no change to `tests/acceptance/openapi_snapshot.json` (the routes hang under `admin_api/api/agent.py`).
- Operators: nothing changes until an operator makes an agent a publisher; `MINTKEY_AGENT_GRANT_MAX_TTL` (from
  `grant-expiry`) caps the lifetime of what an agent gives.
- Out of scope: access requests (`agent-access-requests`), a directory of agents, constraints edited on a live grant, an
  agent granting on an operator-owned service, the admin UI.
- Depends on: `agent-service-tools` (the role registry, `enforce_tool_role`, `agent_request`, which in turn build on
  `agent-service-routes`: the agent router, `require_owned_service`, and `agent-principal-and-egress`: the principal) and
  `grant-expiry` (write path, cap).
