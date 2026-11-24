# Agent access requests

## Purpose

An agent asks for time-boxed access to a service of its tenant; the owner agent, or an operator for an operator-owned
service, approves with a lifetime or denies; an approval is a grant. The rules live in one module, used by the agent
routes, the operator routes and the MCP tools, and every state change is audited.

## ADDED Requirements

### Requirement: The schema stores access requests
`apps/admin-api/db/changelog/032-service-access-requests.yaml`, included once in `db.changelog-master.yaml`, SHALL create
`service_access_requests` with `id` (UUID primary key), `tenant_id` (UUID, foreign key to `tenants`), `service_id` (UUID,
foreign key to `services` `ON DELETE CASCADE`), `requester_agent_id` (UUID, foreign key to `agents` `ON DELETE CASCADE`),
`actions` (`TEXT[]`), `reason` (TEXT, null), `requested_ttl_seconds` (INTEGER), `status` (TEXT, default `pending`),
`decided_by_type` (TEXT, null), `decided_by_id` (UUID, null), `decided_at` (TIMESTAMPTZ, null), `decision_note` (TEXT, null),
`grant_id` (UUID, null, foreign key to `permission_grants` `ON DELETE SET NULL`), `created_at` (TIMESTAMPTZ, default
`now()`) and `pending_until` (TIMESTAMPTZ), every column not null except where stated. SQL changes SHALL add the checks
`cardinality(actions) = 1`, `char_length(reason) <= 500`, `char_length(decision_note) <= 500`, `requested_ttl_seconds
BETWEEN 60 AND 7776000`, `status IN ('pending', 'approved', 'denied', 'cancelled', 'expired')` and `decided_by_type IN
('operator', 'agent')`; the partial unique index `uq_service_access_requests_pending` on `(tenant_id, service_id,
requester_agent_id) WHERE status = 'pending'`; indexes on `(tenant_id, service_id, status)` and `(tenant_id,
requester_agent_id, status)`; row-level security with a `tenant_isolation` policy that has the text of the policy in
`004-services.yaml`; and a `GRANT SELECT, INSERT, UPDATE, DELETE ... TO mintkey_app`, each changeset with a rollback.
`mintkey_models/db.py` SHALL gain a model `ServiceAccessRequest` with exactly those columns (`actions` as
`ARRAY(Text)`), and `TENANT_SCOPED` in `tests/architecture/test_rls_coverage.py` SHALL list the table.

#### Scenario: the changelog creates the table
- **WHEN** the changelog is parsed as YAML and the master changelog is read
- **THEN** the `createTable` has the columns above with the types, defaults, nullability and the three foreign keys with their
  `onDelete`, the SQL text contains each check and the partial index, the RLS changeset text contains
  `tenant_id = current_setting('app.current_tenant', true)::uuid` and `app.platform_admin_view`, one SQL change contains
  `GRANT SELECT, INSERT, UPDATE, DELETE` and `mintkey_app`, every changeset has a `rollback`, and exactly one include in
  the master names `032-service-access-requests.yaml`

#### Scenario: the mirror and the RLS list know the table
- **WHEN** `mintkey_models.db` is imported and `tests/architecture/test_rls_coverage.py` is read as text
- **THEN** `ServiceAccessRequest.__tablename__` is `service_access_requests`, its column keys are those of the
  `createTable`, and the text of the RLS test lists `"service_access_requests"` in `TENANT_SCOPED`

### Requirement: The audit contract lists the request events
`docs/architecture/contracts/events/audit-event.schema.json` SHALL define `ev_access_request_created`, `_approved`, `_denied`,
`_cancelled` and `_expired` (event types `access_request.created` and so on, target type `access_request`), each in
`oneOf` and `discriminator.mapping`, and add `access_request` to the `target_type` enum. Payload keys (all required unless
marked): created `{request_id, service_id, requester_agent_id, action, requested_ttl_seconds}`; approved `{request_id,
service_id, requester_agent_id, action, grant_id, expires_at, decided_by_type, decided_by_id (nullable)}`; denied
`{request_id, service_id, requester_agent_id, action, decided_by_type, decided_by_id (nullable), decision_note (nullable)}`;
cancelled `{request_id, service_id, requester_agent_id, action}`; expired `{request_id, service_id, requester_agent_id,
action, pending_until}`.

#### Scenario: the contract lists them
- **WHEN** the schema is loaded as JSON
- **THEN** the five definitions exist with exactly those payload properties and `additionalProperties` false, each type is
  a key of `discriminator.mapping` and each `$ref` is in `oneOf`, and the `target_type` enum contains `access_request`

### Requirement: Pending requests end after 72 hours
`admin_api.services.access_requests` SHALL give `PENDING_WINDOW_SECONDS: Final[int] = 259_200` and `async def
expire_pending_requests(session: AsyncSession, tenant_id: UUID, now: datetime) -> int`, which SHALL run `UPDATE
service_access_requests SET status = 'expired' WHERE tenant_id = :tid AND status = 'pending' AND pending_until <= :now
RETURNING ...`, write one `access_request.expired` event per returned row (`actor_type` `system`, `actor_id` None,
`target_type` `access_request`) and return the count. Every public function below SHALL call it before any other
statement.

#### Scenario: overdue requests expire once
- **WHEN** the UPDATE returns two rows, and then none
- **THEN** the first call returns 2 and writes two events with `actor_type` `system` and the request, service and
  requester in wire form; the second returns 0 and writes nothing

#### Scenario: every function sweeps first
- **WHEN** `create_access_request`, `cancel_access_request`, `decide_access_request`, `list_access_requests` and
  `get_access_request` run over a fake session
- **THEN** the first statement of each contains `status = 'expired'`

### Requirement: An agent asks for access to a service
`create_access_request(session, *, tenant_id: UUID, requester_agent_id: str, service_ref: str, action: str, ttl_seconds:
int, reason: str | None, now: datetime) -> dict[str, Any]` SHALL resolve `service_ref` (a `svc_` id, else a slug) among
the tenant's services, then refuse in this order with `AccessRequestError`: 404 `not_found` (no service), 422 `invalid_id`
with `field` `service_id` (a `svc_` value that does not decode), 422 `invalid_request` with reason `own_service` (the
service is owned by the requester), 409 `already_granted` (a live grant of the requester for the service and action), 409
`request_pending` with the pending request's id. Otherwise it SHALL insert a request with a new UUID, `actions` `[action]`,
`reason` (stripped; empty is null), `requested_ttl_seconds`, status `pending` and `pending_until = now +
PENDING_WINDOW_SECONDS`, write `access_request.created` (actor the requester, `actor_type` `agent`), and return
`access_request_view`. An `IntegrityError` on the insert SHALL raise 409 `request_pending`.

`AccessRequestError(status_code: int, code: str, title: str, **detail: Any)` and `access_request_view(row) -> dict` SHALL
give the interface named in design: the view keys `{id, service_id, service_slug, service_name, requester_agent_id,
requester_agent_name, actions, reason, requested_ttl_seconds, status, decided_by_type, decided_by_id, decided_at,
decision_note, grant_id, created_at, pending_until}` with `areq_`, `svc_`, `agent_` and `perm_` ids, an agent decider as an
`agent_` id and an operator decider as UUID text, timestamps as ISO text or null, and a missing attribute read as null.

#### Scenario: a request is created
- **WHEN** an agent asks for a service by slug with `ttl_seconds` 3600, action `call` and a reason with surrounding spaces
- **THEN** one INSERT binds the tenant, the service, the requester, `["call"]`, the stripped reason, 3600, status
  `pending` and `pending_until` exactly `now` plus 259200 seconds; one `access_request.created` event names the requester;
  the view has status `pending` and null decision fields

#### Scenario: a request by service id, and refusals in order
- **WHEN** the reference is a decodable `svc_` id and the reason is blank; and then is `svc_xyz`, an unknown slug, a service owned by the requester,
  a service for which a live grant exists, and a service with a pending request
- **THEN** the first inserts with `reason` null; the others raise 422 `invalid_id`, 404 `not_found`, 422 `invalid_request` (`own_service`),
  409 `already_granted` and 409 `request_pending` (with `request_id`), and none of them ran an INSERT or wrote an event

#### Scenario: the one-pending rule at the database
- **WHEN** the INSERT raises `IntegrityError`
- **THEN** the function raises 409 `request_pending` and writes no event

#### Scenario: the view
- **WHEN** `access_request_view` runs on a row decided by an agent with a grant, a row decided by an operator, and a row
  with no decision attributes at all
- **THEN** the first shows `decided_by_id` in `agent_` form and `grant_id` in `perm_` form, the second shows the operator's
  UUID text, the third shows null for every decision field, and every row shows `id` in `areq_` form and ISO timestamps

### Requirement: A requester cancels its own pending request
`cancel_access_request(session, *, tenant_id: UUID, requester_agent_id: str, request_id: str, now: datetime) -> dict` SHALL
select the request pinned to the tenant and the requester (404 `not_found` otherwise, also for another agent's
request), raise 409 `request_not_pending` with `status` unless it is pending, then set `status` `cancelled`, `decided_by_type`
`agent`, `decided_by_id` the requester and `decided_at` `now`, write `access_request.cancelled` and return the view.

#### Scenario: cancel, and what cannot be cancelled
- **WHEN** a requester cancels its pending request; another agent cancels it; the request is approved; the id is unknown
- **THEN** the first updates the row (status `cancelled`) and writes one event; the others raise 404 `not_found`, 409
  `request_not_pending` (status `approved`) and 404 `not_found`, with no UPDATE and no event

### Requirement: The owner or an operator decides a request
`decide_access_request(session, *, tenant_id: UUID, request_id: str, decision: str, decider: Grantor, ttl_seconds: int |
None, note: str | None, now: datetime) -> dict` SHALL select the request with its service's owner `FOR UPDATE` (404
`not_found` without a row), and for an agent decider raise 403 `not_owner` unless the service's `owner_agent_id` is the
decider, then 403 `self_decision` when the requester is the decider; raise 409 `request_not_pending` unless the status is
`pending`. A `deny` SHALL set `status` `denied` with the decider, `decided_at` and `decision_note`, write
`access_request.denied` and return the view. An `approve` SHALL raise 409 `requester_not_active` unless the requester's agent
row (tenant-pinned) has status `active`; compute `ttl = approved_ttl_seconds(requested_ttl_seconds, ttl_seconds,
agent_grant_max_ttl_seconds())`; call `write_grant` for the requester, the service, the action, `{}` constraints,
`expires_at = now + ttl`, the decider and `now` (a `GrantConflict` raises 409 `grant_conflict`); set `status` `approved`, the
decider, `decided_at`, `decision_note` and `grant_id`; write `agent.permission.granted` (when the grant was created; payload
from `grant_granted_audit_payload`) and `access_request.approved`; and return the view plus `grant: {id, action,
expires_at}`. `approved_ttl_seconds(requested: int, approved: int | None, cap: int) -> int` SHALL return the smallest of
`requested`, `approved` (ignored when None) and `cap`. Events name the decider as actor (`operator` or `agent`).

#### Scenario: ttl arithmetic
- **WHEN** `approved_ttl_seconds` runs with (3600, None, 604800), (3600, 600, 604800), (3600, 7200, 604800) and (7776000,
  None, 604800)
- **THEN** it returns 3600, 600, 3600 and 604800

#### Scenario: the owner approves
- **WHEN** the owner agent approves a pending request for 3600 seconds requested and 1800 approved, with `MINTKEY_AGENT_GRANT_MAX_TTL`
  unset
- **THEN** `write_grant` was called once with the requester as grantee, the service, the action, `{}`, `Grantor("agent",
  <owner>)`, `expires_at` equal to `now` plus 1800 seconds and that `now`; the request row is set to `approved` with the
  owner, `decided_at` and the grant id; the events are `agent.permission.granted` and `access_request.approved`, both
  with the owner as actor; the result has `grant.expires_at`

#### Scenario: an operator approves and the cap applies
- **WHEN** an operator approves a request for 7776000 seconds with `MINTKEY_AGENT_GRANT_MAX_TTL` `3600` and no approved
  TTL, for a service with no owner
- **THEN** `write_grant` received `Grantor("operator", <id>)` and `expires_at` `now` plus 3600; the events name the
  operator as actor

#### Scenario: a denial
- **WHEN** the owner denies with the note `not now`
- **THEN** the row is set to `denied` with the note, one `access_request.denied` event is written, `write_grant` was not
  called, and the view has no `grant` key

#### Scenario: who may decide, and when
- **WHEN** an agent that does not own the service decides; an agent decides on an operator-owned service; the owner decides a
  request that it made itself (ownership moved after the request); an operator decides on an agent-owned service; the
  request is `denied`; the id is unknown
- **THEN** the answers are 403 `not_owner`, 403 `not_owner`, 403 `self_decision`, success, 409 `request_not_pending`
  (status `denied`) and 404 `not_found`; every refusal ran no UPDATE, no `write_grant` and wrote no event

#### Scenario: approval blocked
- **WHEN** the requester's agent row is `revoked`; and `write_grant` raises `GrantConflict`
- **THEN** the answers are 409 `requester_not_active` and 409 `grant_conflict`; the request row was not updated, no event was
  written and the status stays `pending`

#### Scenario: an overdue request cannot be decided
- **WHEN** the sweep flips the request to `expired` before the decision
- **THEN** the decision raises 409 `request_not_pending` with status `expired`

### Requirement: Requests are listed by their audience
`list_access_requests(session, *, tenant_id: UUID, now: datetime, requester_agent_id: str | None = None, owner_agent_id: str |
None = None, service_id: str | None = None, status: str | None = None) -> list[dict]` SHALL select the tenant's requests
(joined with `services` and `agents` for the names), apply each given filter in SQL, order by `created_at` descending, limit
200, and return views. `get_access_request(session, *, tenant_id: UUID, request_id: str, now: datetime) -> dict` SHALL return
the view or raise 404 `not_found`.

#### Scenario: get
- **WHEN** `get_access_request` runs for a stored request and for an id with no row
- **THEN** the first returns the view and the second raises 404 `not_found`

#### Scenario: filters reach the statement
- **WHEN** the list runs with no filter, with the requester, with the owner and a status, and with a service
- **THEN** the statements pin the tenant, the filtered ones bind the given ids and status, and the order and the limit are
  in every statement
