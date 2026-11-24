# An agent asks the owner of a service for time-boxed access

## Why

An agent that needs a service another agent owns cannot ask, and the owner cannot say yes. A request names the service, the
time and a reason; the owner agent (an operator, for an operator-owned service) approves with a lifetime or denies; approval
creates the time-boxed grant of `agent-granted-access`, and an unanswered request ends by itself.

## What Changes

- Liquibase `032-service-access-requests.yaml`: table `service_access_requests`, mirrored in `mintkey_models/db.py`.
- `admin_api.services.access_requests` holds the rules once (create, cancel, decide, list, get, the 72-hour expiry evaluated
  on read or decision) and writes the five `access_request.*` audit events.
- Agent routes on the agent router of `agent-service-routes`: `POST` and `GET /v1/agent/access-requests` and
  `POST .../{request_id}/cancel` for every agent; `GET /v1/agent/incoming-access-requests` and `POST
  .../{request_id}/decision` for publishers, who decide only requests for services they own and never their own.
- Operator routes under `/v1/tenants/{tenant_id}/access-requests` (list, get, approve, deny), authenticated by the tenant
  session. Approval creates a grant with `expires_at = now + min(requested, approved, cap)` through `write_grant`.
- Five MCP tools: `mintkey_request_access`, `mintkey_list_my_access_requests`, `mintkey_cancel_access_request` (every
  agent), `mintkey_list_incoming_access_requests` and `mintkey_decide_access_request` (publishers).
- The audit contract gains the five events and the target type `access_request`.

## Capabilities

### New Capabilities
- `agent-access-requests`: the request table and states, the audit events and the shared rules.
- `agent-access-request-routes`: the agent and operator routes and the five MCP tools over those rules.

## Impact

- Changed: the master changelog, `agent.py`, `main.py`, `mintkey_models/db.py`, the audit schema, `tools.yaml`, `jsonrpc.py`, the MCP
  `main.py`, the set `TENANT_SCOPED` of `tests/architecture/test_rls_coverage.py` and `apps/mcp-server/tests/test_jsonrpc.py`
  (two tests expect thirteen tools instead of ten).
- New: the migration `032-service-access-requests.yaml`, `services/access_requests.py`, the two route modules and the MCP
  tools module (paths in tasks.md).
- Data fixture: `tests/acceptance/openapi_snapshot.json` gains one entry, authorised in task 4.3 (design D7).
- Operators: run the migration with the release. Requests expire after 72 hours; deleting a service or agent deletes its requests.
- Out of scope: more than one action per request, constraints at approval, owner notification, the admin UI, a scheduler.
- Depends on: `agent-granted-access`, `agent-service-tools`, `agent-service-routes`, `agent-principal-and-egress`,
  `grant-expiry` and `agent-roles-and-ownership` (the symbols each gives are listed in design.md).
