# A publisher agent registers and maintains its own services

## Why

Only an operator, in the admin UI, can register a service or store its credential today. An agent that stands up an API
for other agents must ask a person for every change. A trusted agent should do this itself, inside limits an operator can
see: it creates services and edits only its own, writes a credential but never reads one back, and cannot delete a
service, hand it over, change a role or reach an internal address. This is the first change that lets an agent write, so
the authentication of the new routes, the role check and the credential rules are its core.

## What Changes

- New admin-api routes `/v1/agent/services` (create, list own, update own, set the credential of an own service),
  authenticated only by the agent key through `require_agent_principal` (`admin_api/auth/agent_principal.py`). No
  `/v1/agent` route accepts an operator session and no operator route accepts an agent key; the tenant comes from the key.
- Four MCP tools over them, `mintkey_service_create`, `_update`, `_set_credential` and `mintkey_list_my_services`, for the
  `publisher` role. `mcp_server.policy.roles` is the one registry of which role may call which tool: `tools/list` shows a
  role only its tools, and a refused call answers 403 `mintkey:role_forbidden` (JSON-RPC error `-32003`) and writes
  `agent.operation.denied`.
- A credential is write-only (`{service_id, credential_set, updated_at}`) and bound to its target: an agent update of
  `base_url` or `auth_scheme` deletes it in the same transaction.
- `base_url` and `openapi_url` from an agent must be `https` and not internal (`mintkey_models.egress`); the credential's vault
  row is stored with `egress_scope` `public` (the put-time parameter of `proxy-public-egress`), so the proxy repeats the check at
  connect time.
- The audit contract gains `agent.operation.denied`, `service.credential.set` and `service.credential.cleared`.

## Capabilities

### New Capabilities
- `agent-service-publishing`: the agent principal, the `/v1/agent` route family, the publisher's service operations and
  credential rules.
- `agent-egress-policy`: the rule for URLs that agents supply.
- `agent-tool-roles`: the role registry of the MCP tools, the refusal, and the four publisher tools.

## Impact

- Changed: `apps/admin-api/src/admin_api/api/internal.py` (the key check becomes `check_agent_key`; answers unchanged),
  `apps/admin-api/src/admin_api/main.py`, `apps/mcp-server/src/mcp_server/tools/jsonrpc.py`,
  `apps/mcp-server/src/mcp_server/main.py`, `apps/mcp-server/src/mcp_server/admin_api_client.py`,
  `apps/mcp-server/src/mcp_server/auth/agent_key.py`, `docs/architecture/contracts/mcp/tools.yaml`,
  `docs/architecture/contracts/events/audit-event.schema.json`.
- New: `packages/python/mintkey-models/mintkey_models/egress.py`, `apps/admin-api/src/admin_api/auth/agent_principal.py`,
  `apps/admin-api/src/admin_api/api/agent.py`, `apps/admin-api/src/admin_api/api/agent_services.py`,
  `apps/admin-api/src/admin_api/services/agent_publishing.py`, `apps/mcp-server/src/mcp_server/policy/roles.py`,
  `apps/mcp-server/src/mcp_server/tools/service_publishing.py`; tests as listed per task in tasks.md.
- Data fixture: `tests/acceptance/openapi_snapshot.json` gains `"agent": "/v1/agent"` (the one router module `main.py`
  imports for every agent route, later changes' included): that edit needs a person's answer.
- Operators: nothing happens until an operator makes an agent a publisher. `MINTKEY_AGENT_EGRESS_DENY` (comma-separated
  names or `*.suffix`) extends the deny list; `MINTKEY_SSRF_ALLOW_PRIVATE` does not apply to agents.
- Out of scope: deleting or transferring a service, setting a role, reading or testing a credential, granting access,
  access requests, the admin UI, a fetch-time re-check of `openapi_url` by `get_openapi`, a quota of services per agent.
- Depends on: `agent-roles-and-ownership` (role and owner columns, `mintkey_models.roles`) and `proxy-public-egress`
  (the `vault.credentials.egress_scope` column and the `egress_scope` parameter of `VaultAdapterClient.put_credential`).
