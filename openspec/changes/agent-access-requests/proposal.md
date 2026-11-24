# An agent asks the owner of a service for time-boxed access

## Why

An agent that needs a service another agent owns has no way to ask: it waits for an operator to notice, and the owner has
no way to say yes. Requests belong in the system, with a state everyone can read: the requester says which service,
for how long and why; the owner agent (or an operator, for an operator-owned service) approves with a lifetime or
denies; approval creates the same time-boxed grant `agent-granted-access` gives, and an unanswered request ends by
itself. Operators see and decide every request.

## What Changes

- Liquibase `032-service-access-requests.yaml`: table `service_access_requests` (row-level security by tenant, one pending
  request per requester and service, one action per request) and its mirror in `mintkey_models/db.py`.
- `admin_api.services.access_requests` holds the rules once: create, cancel, decide, list and get, the 72-hour expiry
  evaluated when a request is read or decided (no scheduler), and the five audit events (`access_request.created`,
  `.approved`, `.denied`, `.cancelled`, `.expired`).
- Agent routes on the agent router of `agent-service-publishing`: `POST` and `GET /v1/agent/access-requests` and
  `POST .../{request_id}/cancel` for every agent; `GET /v1/agent/incoming-access-requests` and `POST
  .../{request_id}/decision` for publishers, who decide only requests for services they own and never their own.
- Operator routes under `/v1/tenants/{tenant_id}/access-requests` (list, get, approve, deny), authenticated by the tenant
  session. Approval creates a grant with `expires_at = now + min(requested, approved, cap)` through `write_grant`.
- Five MCP tools: `mintkey_request_access`, `mintkey_list_my_access_requests`, `mintkey_cancel_access_request` (every
  agent) and `mintkey_list_incoming_access_requests`, `mintkey_decide_access_request` (publishers). With them
  `tools/list` equals the role registry of `agent-service-publishing`.
- The audit contract gains the five events and the target type `access_request`.

## Capabilities

### New Capabilities
- `agent-access-requests`: the request table and states, the audit events and the shared rules.
- `agent-access-request-routes`: the agent and operator routes and the five MCP tools over those rules.

## Impact

- Changed: `apps/admin-api/db/changelog/db.changelog-master.yaml`, `apps/admin-api/src/admin_api/api/agent.py`,
  `apps/admin-api/src/admin_api/main.py`, `packages/python/mintkey-models/mintkey_models/db.py`,
  `docs/architecture/contracts/events/audit-event.schema.json`, `docs/architecture/contracts/mcp/tools.yaml`,
  `apps/mcp-server/src/mcp_server/tools/jsonrpc.py`, `apps/mcp-server/src/mcp_server/main.py`.
- New: `apps/admin-api/db/changelog/032-service-access-requests.yaml`,
  `apps/admin-api/src/admin_api/services/access_requests.py`, `apps/admin-api/src/admin_api/api/agent_access_requests.py`,
  `apps/admin-api/src/admin_api/api/access_requests.py`, `apps/mcp-server/src/mcp_server/tools/access_requests.py`; tests
  as listed per task in tasks.md.
- Changed existing tests: `tests/architecture/test_rls_coverage.py` (`TENANT_SCOPED` gains the table; it needs Docker and
  stays out of the L4 gate), `apps/mcp-server/tests/test_jsonrpc.py` (the two tests that expect ten tools for a context
  without a role now expect thirteen) and `apps/mcp-server/tests/test_service_publishing_tools.py` (the expected lists).
- Data fixture: `tests/acceptance/openapi_snapshot.json` gains `"access_requests":
  "/v1/tenants/{tenant_id}/access-requests"` (a new router module imported by `main.py`): that edit needs a person's answer.
- Operators: run the migration with the release. Requests expire after 72 hours; deleting a service or an agent deletes its
  requests without an event.
- Out of scope: more than one action per request, constraints chosen at approval, notification of the owner, the admin UI
  (`admin-ui-agent-governance`), a scheduler for expiry.
- Depends on: `agent-granted-access` (wire id helper, forwarding helpers, `grant_view`), `agent-service-publishing`,
  `grant-expiry` (`write_grant`, the cap).
