# Design: agent-roles-and-ownership

## Context

Facts at the base (staging `2c4c814`); the requirements name symbols, the anchors are for review only.

- `agents` has no role column; `agents.created_by` exists and is always NULL (`ADM/api/agents.py:271`). `services` has
  neither owner nor creator (`CL/004-services.yaml`, `CL/017`). `operator_tenant_memberships.role` is written and never
  read.
- Agent rows reach the wire through `_agent_row_to_dict` (`ADM/api/agents.py:166`); five statements select the agent
  columns (the four branches of `list_agents`, lines 398-463, and `get_agent`, line 506). There is no agent PATCH route.
- Service rows reach the wire through `_service_row_to_dict` (`ADM/api/services.py:358`); four statements select the
  service columns (`list_services` twice, `get_service`, the re-read at the end of `update_service`). `create_service`
  and `create_service_from_template` insert services and name no owner.
- `validate_agent_key` (`ADM/api/internal.py:135`) selects `id, tenant_id, api_key_hash, status, api_key_expires_at,
  api_key_fingerprint` and answers `{agent_id, tenant_id, status}`; `tests/unit/admin_api/test_validate_agent_key_errors.py`
  feeds it exactly two `execute` results and a row without `role`. The MCP server stores the answer as the agent
  context (`MCP/auth/agent_key.py:21`); `AdminApiClient.validate_agent_key` (`MCP/admin_api_client.py:36`) types it as
  `AgentContext(agent_id, tenant_id)`. Existing MCP tests build contexts with `{agent_id, tenant_id, status}` only.
- Operator identity: `require_tenant_session` (`ADM/auth/sessions.py:171`) returns nothing; the operator id comes from
  `get_session_context` (`sessions.py:156`), which returns an object with `operator_id` and `tenant_id`, or None.
- `tests/acceptance/test_sqlalchemy_mirror.py` collects columns only from `createTable` changesets; a model column that
  no `createTable` names fails `test_no_model_defines_column_not_in_changelogs`. `mintkey_models/db.py` is left alone.

## Decisions

**D1. Roles.** `agents.role` is TEXT NOT NULL DEFAULT `'consumer'` with a CHECK for `consumer` and `publisher`. Only an
operator sets it, through the tenant-session route below. Every existing agent is a consumer after the upgrade, so
nobody gains a power.

**D2. Ownership.** `services.owner_agent_id` (NULL = operator-owned) and `services.created_by_agent_id`, both UUID NULL,
foreign keys to `agents(id)` with `ON DELETE SET NULL`: deleting an agent leaves its services operator-owned. Existing
services stay operator-owned. Operators keep full control of every service: this change adds no owner check to any
operator route. Transfer is operator-only and changes nothing but `owner_agent_id` and `updated_at`: the credential
and the grants stay (the agent-publishing change binds a credential to its target, so that is safe).

**D3. The role travels with the key check.** `validate-agent-key` adds `role` to its 200 body; the MCP server keeps
the body as the agent context. A context with no `role` (an older admin-api, a test) is a `consumer`: the reader
defaults to the less powerful role. The row's `role` is read with `getattr(row, "role", "consumer")` so a row without
the attribute (the existing test's) still answers 200.

**D4. One vocabulary.** `mintkey_models.roles` (standard library only) gives both services the same names and the
same fallback; admin-api and the MCP server import it.

**D5. Role and owner filters run after the query.** The agent and service list statements are explicit string
branches (a convention of the two modules); a filter that adds a branch per combination would double them. Both
filters are applied to the fetched rows, so no statement changes except the added columns. Neither list has a `LIMIT`, an
offset or a page at the base (`list_agents` and `list_services` return every row of the tenant), so the filtered result is
exact; a later change that adds paging must move the filter into SQL.

**D6. Audit and wire ids.** `agent.role.changed` and `service.ownership_transferred` write `actor_type` `operator` and
`actor_id` = the operator id from `get_session_context` (None when there is no context, as in tests that skip the
session). Agents appear on the wire in their `agent_...` form (`db_uuid_to_wire(value, "agent")`), a missing owner
as null. The audit contract has one definition per event type under `$defs` (`ev_<type with dots as underscores>`),
one `oneOf` entry and one `discriminator.mapping` entry; there is no single enum, so each new type adds those three.
Adding the types to the admin UI's audit filter list (`apps/admin-ui/src/resources/audit.ts`) belongs to
`admin-ui-agent-governance`, not to this change.

**D7. Numbering and plan order.** This change's changelog is `031`; `grant-expiry` takes `030`. Both append to
`db.changelog-master.yaml`, so `grant-expiry` merges first.

**D8. Demotion changes nothing else.** The role PATCH writes the agent's role and `updated_at` and nothing more: a demoted
publisher keeps the services it owns and the grants on them, and the operator hands the services back with the transfer
route when it wants to. An automatic hand-back would silently change what other agents' grants point at. No owner decision remains.

**D9. Transfer checks run in a fixed order.** Body, ids, the service (read `FOR UPDATE`, so two transfers of one service
serialise and `from_agent_id` is the owner they found), a target equal to the current owner (200, nothing written, even if
that agent has since been demoted or revoked: the owner does not change), the target agent, its status, its role. A revoked
consumer is therefore `agent_not_active`. The UPDATE, the audit event and the NOTIFY run in the request's transaction; a
failing statement answers 500 and none is committed.

## Interfaces

`mintkey_models/roles.py` (given to `agent-service-publishing`, `agent-granted-access`, `agent-access-requests` and the
admin UI):

```python
ROLE_CONSUMER: Final[str] = "consumer"
ROLE_PUBLISHER: Final[str] = "publisher"
AGENT_ROLES: Final[tuple[str, ...]] = ("consumer", "publisher")
def normalize_role(value: object) -> str  # a value in AGENT_ROLES unchanged, anything else (None, "", "admin", 5) "consumer"
```

Wire shapes (operator API, tenant session):

- Agent object gains `"role": "consumer" | "publisher"`. `GET /v1/tenants/{tenant_id}/agents?role=publisher` filters.
- Error bodies are flat JSON (keys at the top level, as the routes' existing answers; the spec's error requirement lists
  them): `validation_failed` and `invalid_id` carry a `title`, `invalid_transfer_target` a `title` and a `reason`.
- `PATCH /v1/tenants/{tenant_id}/agents/{agent_id}`, body `{"role": "consumer" | "publisher"}` (no other key), answers
  200 with the agent object. 404 `{"mintkey:code": "not_found", "title": "Agent not found"}` for an unknown id; 422
  `validation_failed` for any other body.
- Service object gains `"owner_agent_id": "agent_..." | null` and `"created_by_agent_id": "agent_..." | null`.
  `GET /v1/tenants/{tenant_id}/services?owner_agent_id=agent_...` lists that agent's services; the value `operators`
  lists the operator-owned ones; any other value answers 422 `invalid_id`.
- `POST /v1/tenants/{tenant_id}/services/{service_id}/transfer`, body `{"to_agent_id": "agent_..." | null}` (the key is
  required), answers 200 with the service object. Errors: 404 `not_found` (service, or an agent of another tenant),
  422 `invalid_id`, 422 `{"mintkey:code": "invalid_transfer_target", "title": "Transfer target not allowed", "reason":
  "agent_not_active" | "agent_not_publisher"}`. A transfer that changes the owner publishes `notify_change(session,
  "mintkey:service", {"event": "service.ownership_transferred", "tenant_id": <UUID text>, "service_id": "svc_...",
  "from_agent_id": "agent_..." | null, "to_agent_id": "agent_..." | null})`; the proxy and the UI do not read it yet.
- `POST /v1/internal/validate-agent-key` 200 body: `{"agent_id", "tenant_id", "status", "role"}`.
- `AdminApiClient.validate_agent_key` returns `AgentContext(agent_id, tenant_id, role="consumer")`.
- Audit payloads: `agent.role.changed` `{agent_id, from_role, to_role}`, target type `agent`;
  `service.ownership_transferred` `{service_id, from_agent_id, to_agent_id}`, target type `service`.

## Failure cases

- A role value outside the two names, an extra key, or no body: 422, nothing written.
- The agent or service of another tenant: 404 (the statements are tenant-pinned and row-level security applies).
- The target of a transfer is a revoked agent or a consumer: 422, nothing written; a revoked consumer is `agent_not_active`.
- A transfer to the current owner: 200, nothing written, even when that agent is now a consumer or revoked.
- A failing statement or database: 500, and the UPDATE, the audit event and the NOTIFY of the request are not committed.
- Setting the role or the owner a row already has: 200, no UPDATE, no audit event, no NOTIFY.
- No session cookie on either route: 401 from `require_tenant_session`, before any statement (the tests keep the real
  dependency and a recording `get_db_session`, so the absence of statements is observed).
- The migration on a database with agents and services: they keep working; `role` is `consumer`, owners are NULL.

## Relation to the other changes

Assumes `tenant-session-routes` is merged: both new routes carry `require_tenant_session`, which is the route-level
authentication rule it establishes. `agent-service-publishing` reads `agents.role` through the key check and the
owner columns through its own statements; `admin-ui-agent-governance` reads the fields and filters above. The
agent-side tools check `role` themselves; no operator route reads it.
