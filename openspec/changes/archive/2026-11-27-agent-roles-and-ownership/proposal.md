# Agents have a role, and services have an owner

## Why

Every agent holds the same power today and every service belongs to the tenant alone: there is no record of who
registered a service, and nothing tells one agent from another beyond its key. The next changes let a trusted agent
publish services, give other agents access and answer access requests. They need three facts to exist first: which
agents may publish (a role an operator sets), which agent owns a service (so that an agent edits only its own), and a
way for an operator to hand a service from one owner to another. This change adds those facts and nothing that acts on
them: no agent route, no agent tool and no permission check on an agent yet.

## What Changes

- Liquibase `031-agent-roles-and-ownership.yaml`: `agents.role` (`consumer` | `publisher`, default `consumer`, so every
  existing agent stays a consumer), `services.owner_agent_id` and `services.created_by_agent_id` (both nullable, foreign
  keys to `agents` with `ON DELETE SET NULL`; null owner means operator-owned, which every existing service is).
- Agent responses of the operator API carry `role`; `GET .../agents` takes an optional `role` filter. A new route
  `PATCH /v1/tenants/{tenant_id}/agents/{agent_id}` lets an operator change the role.
- `POST /v1/internal/validate-agent-key` answers with the agent's `role`, and the MCP server's agent context carries it
  (a context without a role is a consumer).
- Service responses of the operator API carry `owner_agent_id` and `created_by_agent_id`; `GET .../services` takes an
  optional `owner_agent_id` filter. A new route `POST /v1/tenants/{tenant_id}/services/{service_id}/transfer` lets an
  operator set the owner to an active publisher of the tenant, or back to operators; a changed owner also publishes
  `service.ownership_transferred` on `mintkey:service` (payload in design.md).
- The audit contract gains `agent.role.changed` and `service.ownership_transferred`, each written with the operator as
  the actor.
- Demoting a publisher changes nothing but its role: its services and their grants stay until an operator transfers them.
- A shared module `mintkey_models.roles` holds the two role names.

## Capabilities

### New Capabilities
- `agent-roles-and-ownership`: an agent's role, a service's owner, and the operator-only routes that change them.

## Impact

- Changed: `apps/admin-api/src/admin_api/api/agents.py`, `apps/admin-api/src/admin_api/api/services.py`,
  `apps/admin-api/src/admin_api/api/internal.py`, `apps/mcp-server/src/mcp_server/admin_api_client.py`,
  `docs/architecture/contracts/events/audit-event.schema.json`, `apps/admin-api/db/changelog/db.changelog-master.yaml`.
- New: `apps/admin-api/db/changelog/031-agent-roles-and-ownership.yaml`,
  `packages/python/mintkey-models/mintkey_models/roles.py`.
- New tests: `packages/python/mintkey-models/tests/test_roles.py`, `tests/unit/admin_api/test_agent_roles_migration.py`,
  `tests/unit/admin_api/test_agent_roles.py`, `tests/unit/admin_api/test_service_ownership.py`,
  `tests/unit/admin_api/test_audit_schema_roles.py`, `apps/mcp-server/tests/test_agent_context_role.py`.
- The new columns are not added to the ORM mirror `mintkey_models/db.py`: `tests/acceptance/test_sqlalchemy_mirror.py`
  recognises only `createTable` columns, and `Agent` and `Service` already leave their `addColumn` columns out. The
  code reads them with SQL.
- Operators: run the migration with the release; nothing changes for agents or services until a later change reads the
  new columns. No role is read for any decision in this change.
- Out of scope: any check of the role or the owner, agent-side routes and tools, the admin UI, deleting or reassigning
  services when an agent is deleted (the foreign key makes them operator-owned).
- Plan order: this change and `grant-expiry` both append an include to `db.changelog-master.yaml`, add events to
  `audit-event.schema.json` and edit the agent statements of `agents.py` (`grant-expiry` the grant subqueries, this change
  the selected columns); `grant-expiry` is first (changelog `030`), this change follows it (`031`).

## Issue Intake (remediation gate)

1. **Problem statement**: nothing records an agent's role or a service's owner.
2. **Expected behavior**: role and owner exist, default to consumer and operator, and only an operator changes them.
3. **Verification target**: the admin-api, mintkey-models and MCP pytest suites as `.l4/gates/test.sh` runs them.
4. **Owner decisions needed**: none; see design.md, Decisions (D8 settles what a demotion does).
