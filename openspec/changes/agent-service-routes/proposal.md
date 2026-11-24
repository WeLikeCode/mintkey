# A publisher agent registers and maintains its own services

## Why

Only an operator, in the admin UI, can register a service or store its credential today. An agent that stands up an API
for other agents must ask a person for every change. A trusted agent should do this itself, inside limits an operator can
see: it creates services and edits only its own, writes a credential but never reads one back, and cannot delete a
service, hand it over, change a role or point a target at an internal address. This change is the admin-api half: the
`/v1/agent/services` routes. The MCP tools over them are `agent-service-tools`.

## What Changes

- New admin-api routes `/v1/agent/services` (create, list own, update own) and `PUT /v1/agent/services/{service_ref}/credential`,
  all behind `require_publisher_principal` of `agent-principal-and-egress`. No `/v1/agent` route accepts an operator session
  and no operator route accepts an agent key; the tenant comes from the key.
- `admin_api/api/agent.py` holds the one `/v1/agent` router that `main.py` imports; later changes attach sub-routers to it.
  `main.py` registers `agent_api_error_handler` and exempts `/v1/agent` from the CSRF check.
- A credential is write-only (`{service_id, credential_set, updated_at}`), bound to its target (an agent update of
  `base_url` or `auth_scheme` deletes it in the same transaction) and stored with the vault `egress_scope` `public`.
- `base_url` and `openapi_url` from an agent pass `check_agent_target_url` (https, public addresses only).
- The audit contract gains `service.credential.set` and `service.credential.cleared`; `service.registered` may carry
  `owner_agent_id` and `service.updated` may list `auth_scheme`.

## Capabilities

### New Capabilities
- `agent-service-routes`: the route family, the owned-service lookup, create, list and update.
- `agent-service-credential`: the write-only credential route and the new audit events.

## Impact

- Changed: `apps/admin-api/src/admin_api/main.py`, `docs/architecture/contracts/events/audit-event.schema.json`,
  `tests/acceptance/openapi_snapshot.json` (see the data fixture below).
- New: `apps/admin-api/src/admin_api/api/agent.py`, `apps/admin-api/src/admin_api/api/agent_services.py`,
  `apps/admin-api/src/admin_api/services/agent_publishing.py`; tests as listed per task in tasks.md.
- Data fixture: `tests/acceptance/openapi_snapshot.json` gains exactly one entry, `"agent": "/v1/agent"` (the one router
  module `main.py` imports for every agent route, later changes' included). The edit is part of the reviewed text of task
  5.1 (see design D9), not a question for a person.
- Operators: nothing happens until an operator makes an agent a publisher.
- Out of scope: deleting or transferring a service, setting a role, reading or testing a credential, granting access,
  access requests, the MCP tools, the admin UI, a quota of services per agent.
- Depends on: `agent-principal-and-egress` (principal, `AgentApiError`, egress check), `agent-roles-and-ownership` (owner
  columns, `mintkey_models.roles`) and `proxy-public-egress` (the `egress_scope` parameter of
  `VaultAdapterClient.put_credential`).
