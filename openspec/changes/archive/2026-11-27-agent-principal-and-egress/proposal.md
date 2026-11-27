# Agents get an authenticated identity on admin-api and a rule for the URLs they supply

## Why

Agents act through the MCP server today and never call admin-api. The agent governance plan lets a trusted agent
register and share services, so admin-api needs a way to know which agent is calling, with which role, and to refuse a
caller whose role is too low, writing a record of the refusal. A second building block is the rule for URLs an agent
supplies as service targets: a URL an agent chooses must lead to a public https address, never to an internal one. Both
are shared by the changes that follow, so they come first and carry no route of their own.

## What Changes

- `admin_api.auth.agent_principal` gives `AgentPrincipal`, `AgentApiError` with its handler and `agent_error_body` (agent error bodies are `{"code", "title", ...}`), `require_agent_principal`
  (reads only `Authorization: Bearer mk_agent_...`, validates the key in a session of its own, yields the principal with
  tenant, agent and role), `require_publisher_principal` and `record_denied_operation`.
- `admin_api.api.internal.check_agent_key(session, api_key)` is the key check that `POST /v1/internal/validate-agent-key`
  already runs (its first statement turns the platform view on in the session it is given), extracted so the principal
  dependency uses the same code in a dedicated session; the endpoint answers exactly as before.
- `mintkey_models.egress` gives `check_agent_target_url` and its helpers: https only, no IP literal, no internal name, every
  resolved address public. Nothing else calls it in this change.
- The audit contract gains the event `agent.operation.denied`, written when a role refuses an operation.

## Capabilities

### New Capabilities
- `agent-principal`: the agent principal, the shared key check, the role refusal and its audit event.
- `agent-egress-policy`: the rule for URLs that agents supply.

## Impact

- Changed: `apps/admin-api/src/admin_api/api/internal.py` (key check extracted),
  `docs/architecture/contracts/events/audit-event.schema.json`.
- New: `apps/admin-api/src/admin_api/auth/agent_principal.py`, `packages/python/mintkey-models/mintkey_models/egress.py`;
  tests as listed per task in tasks.md.
- No route, no migration, no change to `main.py`, no change to `tests/acceptance/openapi_snapshot.json`: the routes that use
  these modules are `agent-service-routes`.
- Operators: `MINTKEY_AGENT_EGRESS_DENY` (comma-separated names or `*.suffix`) extends the deny list;
  `MINTKEY_SSRF_ALLOW_PRIVATE` does not apply to agents. Nothing happens until a later change uses the modules.
- Out of scope: the `/v1/agent` routes, the MCP role registry and tools, a fetch-time re-check of an agent-owned
  `openapi_url`.
- Depends on: `agent-roles-and-ownership` (`mintkey_models.roles.normalize_role`; `agents.role` and the `role` the key
  check selects).
