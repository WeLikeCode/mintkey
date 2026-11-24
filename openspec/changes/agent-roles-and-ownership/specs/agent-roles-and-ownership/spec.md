# Agent roles and service ownership

## Purpose

An agent has a role that an operator sets, a service has an owner that is an agent or the operators, and only an
operator changes either. This capability is the data and the operator routes; the agent-side operations that read
them are specified where they are given.

## ADDED Requirements

### Requirement: One vocabulary for agent roles
`mintkey_models.roles` SHALL give `ROLE_CONSUMER` (`"consumer"`), `ROLE_PUBLISHER` (`"publisher"`), `AGENT_ROLES`
(`("consumer", "publisher")`) and `normalize_role(value: object) -> str`, which SHALL return a value that is one of
`AGENT_ROLES` unchanged and `"consumer"` for anything else.

#### Scenario: names and fallback
- **WHEN** `normalize_role` is called with `"publisher"`, `"consumer"`, `None`, `""`, `"admin"` and `5`
- **THEN** it returns `"publisher"`, `"consumer"`, `"consumer"`, `"consumer"`, `"consumer"` and `"consumer"`, and
  `AGENT_ROLES` equals `("consumer", "publisher")`

### Requirement: The schema stores an agent's role and a service's owner
The Liquibase changelog `apps/admin-api/db/changelog/031-agent-roles-and-ownership.yaml`, included once in
`db.changelog-master.yaml`, SHALL add `agents.role` (TEXT, not null, default `consumer`) with a CHECK that allows only
`consumer` and `publisher`, and `services.owner_agent_id` and `services.created_by_agent_id` (UUID, nullable), each with
a foreign key to `agents(id)` that is `ON DELETE SET NULL`, and an index on `services (tenant_id, owner_agent_id)`.
The columns SHALL NOT be added to `mintkey_models/db.py`.

#### Scenario: the changelog adds the three columns
- **WHEN** the changelog file is parsed as YAML
- **THEN** it holds an `addColumn` for `agents.role` with type TEXT, default value `consumer` and `nullable: false`,
  an SQL change whose text contains `CHECK (role IN ('consumer', 'publisher'))`, an `addColumn` for each of the two
  service columns without `nullable: false`, an `addForeignKeyConstraint` for each referencing `agents` with
  `onDelete: SET NULL`, and a `createIndex` on `services` for `tenant_id` and `owner_agent_id`

#### Scenario: the master changelog includes it once and the mirror stays unchanged
- **WHEN** `db.changelog-master.yaml` is parsed and `mintkey_models/db.py` is read as text
- **THEN** exactly one include names `031-agent-roles-and-ownership.yaml`, and the text of `db.py` contains none of
  `owner_agent_id`, `created_by_agent_id` and `role: Mapped` within the `Agent` class

### Requirement: Agent responses carry the role
Every agent object of the operator API (create 201, `GET .../agents`, `GET .../agents/{agent_id}`) SHALL carry `role`.
`_agent_row_to_dict` SHALL read it as `normalize_role(getattr(row, "role", None))`, and the five statements that select
agent columns SHALL select `a.role`. `GET /v1/tenants/{tenant_id}/agents` SHALL accept `role` (`consumer` or
`publisher`) and return only agents of that role, and answer 422 `validation_failed` for another value.

#### Scenario: a new agent is a consumer
- **WHEN** an operator creates an agent
- **THEN** the 201 body has `"role": "consumer"`

#### Scenario: list and get show the stored role
- **WHEN** the fake session returns one agent row with `role` `publisher` and one row without a `role` attribute, and
  the list and the get are called
- **THEN** the objects show `"publisher"` and `"consumer"`, and every executed agent SELECT contains `a.role`

#### Scenario: the role filter
- **WHEN** the list is called with `?role=publisher` over two rows of roles `publisher` and `consumer`, and with
  `?role=admin`
- **THEN** the first answers 200 with the one publisher, the second answers 422 `validation_failed`

### Requirement: An operator sets an agent's role
`PATCH /v1/tenants/{tenant_id}/agents/{agent_id}` SHALL carry `require_tenant_session` and accept the body
`{"role": "consumer" | "publisher"}` with no other key. For an agent whose role differs it SHALL run
`UPDATE agents SET role = :role, updated_at = :now` pinned to the agent and the tenant, write the audit event
`agent.role.changed` (`actor_type` `operator`, `actor_id` the operator id of `get_session_context`, `target_type`
`agent`, payload `{agent_id, from_role, to_role}`), and answer 200 with the agent object. For an agent that already has
the role it SHALL answer 200 and run no UPDATE and write no event.

#### Scenario: promote and demote
- **WHEN** an operator patches a consumer to `publisher`, and the same agent back to `consumer`
- **THEN** each answers 200 with the new role, runs one UPDATE with the role bound, and writes one
  `agent.role.changed` event whose payload has the old and the new role and whose `actor_id` is the operator's id

#### Scenario: the same role is nothing to do
- **WHEN** an operator patches a publisher to `publisher`
- **THEN** the answer is 200 with role `publisher`, and no UPDATE and no audit event ran

#### Scenario: invalid bodies and unknown agents
- **WHEN** the body is `{"role": "admin"}`, `{}`, or `{"role": "publisher", "status": "revoked"}`, and when the agent
  id is unknown or `agent_` followed by 26 characters that do not decode
- **THEN** the three bodies answer 422 `validation_failed` with no statement run for the agent, the unknown id answers
  404 `not_found`, and the undecodable id answers 422 `invalid_id`

#### Scenario: no session
- **WHEN** the PATCH carries no `mintkey_session` cookie
- **THEN** the answer is 401 and no statement ran

### Requirement: The agent-key check reports the role
`POST /v1/internal/validate-agent-key` SHALL select `role` with the agent and answer 200 with
`{"agent_id", "tenant_id", "status", "role"}`, the role read as `normalize_role(getattr(row, "role", None))`; its failure
answers and its two-statement shape SHALL NOT change. `AdminApiClient.validate_agent_key` SHALL return an
`AgentContext` with `agent_id`, `tenant_id` and `role` (default `consumer`).

#### Scenario: the answer names the role
- **WHEN** the key of an active publisher is validated, and again for a row without a `role` attribute
- **THEN** the bodies hold `"role": "publisher"` and `"role": "consumer"`, and each run executed exactly two statements

#### Scenario: the MCP client keeps the role
- **WHEN** `AdminApiClient.validate_agent_key` receives a 200 with `"role": "publisher"`, and one without `role`
- **THEN** the contexts have role `publisher` and `consumer`

### Requirement: Service responses carry the owner
Every service object of the operator API SHALL carry `owner_agent_id` and `created_by_agent_id`, each an `agent_...`
wire id or null, read with `getattr(row, name, None)`; the four statements that select service columns SHALL select
`s.owner_agent_id` and `s.created_by_agent_id`. A service created by an operator SHALL have both null.
`GET /v1/tenants/{tenant_id}/services` SHALL accept `owner_agent_id` (an `agent_...` id, or `operators`) and return only
services with that owner; any other value SHALL answer 422 `invalid_id`.

#### Scenario: owner fields on the wire
- **WHEN** the list returns a row with `owner_agent_id` set and a row without the attribute
- **THEN** the first object shows the agent's `agent_...` id and the second shows null for both fields, and the
  executed SELECT texts contain both column names

#### Scenario: the owner filter
- **WHEN** the list runs over rows owned by agent A, by agent B and by nobody, with `?owner_agent_id=<A>`, with
  `?owner_agent_id=operators` and with `?owner_agent_id=not-an-id`
- **THEN** the answers are A's row only, the operator-owned row only, and 422 `invalid_id`

#### Scenario: an operator-created service has no owner
- **WHEN** an operator creates a service
- **THEN** the INSERT statement text does not name `owner_agent_id` or `created_by_agent_id`

### Requirement: An operator transfers a service's ownership
`POST /v1/tenants/{tenant_id}/services/{service_id}/transfer` SHALL carry `require_tenant_session` and require the body
`{"to_agent_id": "agent_..." | null}`. A target SHALL be an agent of the same tenant whose status is `active` and whose
role is `publisher`; `null` makes the service operator-owned. A transfer that changes the owner SHALL run one
`UPDATE services SET owner_agent_id = :owner, updated_at = :now` pinned to the service and the tenant, write
`service.ownership_transferred` (actor the operator, payload `{service_id, from_agent_id, to_agent_id}`), publish a
`service.ownership_transferred` change on `mintkey:service`, and answer 200 with the service object. It SHALL run no
statement on `credentials`, `vault.credentials` or `permission_grants`. A target that is not a publisher or not active
SHALL answer 422 `invalid_transfer_target` with `reason` `agent_not_publisher` or `agent_not_active`, and an agent of
another tenant or an unknown service or agent SHALL answer 404 `not_found`, each with nothing written. A transfer to the
current owner SHALL answer 200 and run no UPDATE and write no event.

#### Scenario: to a publisher and back to operators
- **WHEN** an operator transfers an operator-owned service to an active publisher, then transfers it to `null`
- **THEN** each answers 200 and runs one UPDATE with the new owner bound (the agent's id, then NULL); the two events
  hold `from_agent_id` null then the agent, and `to_agent_id` the agent then null; and no executed statement text
  contains `credentials` or `permission_grants`

#### Scenario: unsuitable targets
- **WHEN** the target is a consumer, a revoked publisher, an agent whose row the tenant-pinned lookup does not return,
  and the service id is unknown
- **THEN** the answers are 422 `agent_not_publisher`, 422 `agent_not_active`, 404 `not_found` and 404 `not_found`, and no
  UPDATE and no audit event ran

#### Scenario: the same owner is nothing to do
- **WHEN** a service owned by agent A is transferred to A, and an operator-owned one to `null`
- **THEN** both answer 200 with no UPDATE and no audit event

#### Scenario: a missing key is refused
- **WHEN** the body is `{}` or `{"to_agent_id": 7}`, and when the request has no session cookie
- **THEN** the bodies answer 422 and the cookie-less request answers 401, with no statement run

### Requirement: Operators keep full control of every service
No operator service route SHALL read `owner_agent_id` for a decision, and `PATCH /v1/tenants/{tenant_id}/services/{service_id}`
SHALL NOT write it.

#### Scenario: an operator edits an agent-owned service
- **WHEN** an operator patches the `description` of a service whose row has `owner_agent_id` set
- **THEN** the answer is 200, and the UPDATE statement text does not name `owner_agent_id`

### Requirement: The new events are in the audit contract
`docs/architecture/contracts/events/audit-event.schema.json` SHALL define `ev_agent_role_changed`
(`agent.role.changed`, target type `agent`, payload properties `agent_id`, `from_role`, `to_role`, all required) and
`ev_service_ownership_transferred` (`service.ownership_transferred`, target type `service`, payload properties
`service_id`, `from_agent_id`, `to_agent_id`, all required, the two agent ids nullable), each listed in the top-level
`oneOf` and in `discriminator.mapping`.

#### Scenario: the contract lists both events
- **WHEN** the schema file is loaded as JSON
- **THEN** both definitions exist with exactly those payload property names, the two types are keys of
  `discriminator.mapping` pointing at their definitions, and both `$ref`s are in `oneOf`
