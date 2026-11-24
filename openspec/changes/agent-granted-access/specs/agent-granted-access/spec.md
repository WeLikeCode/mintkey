# Agent granted access

## Purpose

A publisher agent gives other agents of its tenant time-boxed access to the services it owns, lists who has it and takes
it back. The routes are agent routes (authenticated by the agent key only) and the grants are written through the shared
write path with the agent as grantor. The MCP tools are `agent-grant-tools`.

## ADDED Requirements

### Requirement: The grant routes are agent routes for publishers
`admin_api/api/agent_grants.py` SHALL give `router = APIRouter(prefix="/grants")`, included by `admin_api/api/agent.py`
(`router.include_router(agent_grants.router)`), with `POST /v1/agent/grants`, `GET /v1/agent/grants` and `POST
/v1/agent/grants/{grant_id}/revoke`. Each handler SHALL depend on `require_publisher_principal`, call
`set_tenant_context(session, principal.tenant_id)` before its first statement, and pin every statement to the principal's
tenant. `main.py` SHALL NOT import the module.

#### Scenario: the route table obeys the family rules
- **WHEN** the routes of `create_app()` are walked
- **THEN** the three paths and methods exist, each has `require_agent_principal` in its dependency tree and neither
  `require_tenant_session` nor `require_platform_admin_session`, no `/v1/agent/` route uses DELETE or has `transfer` or
  `role` in its path, and the text of `admin_api/main.py` does not contain `agent_grants`

#### Scenario: consumers and keyless calls are refused
- **WHEN** a consumer principal calls each route (through `require_agent_principal` overridden to return it), and a
  request has no `Authorization` header
- **THEN** the consumer gets 403 `mintkey:role_forbidden` with one `agent.operation.denied` event per call, whose operation
  is the request line sent (`POST /v1/agent/grants`, `GET /v1/agent/grants` and `POST /v1/agent/grants/<grant_id>/revoke`
  with the id used), and no statement for grants; the keyless request gets 401 `mintkey:auth_required`

### Requirement: Wire ids, the grantee and the grant view have one implementation
`admin_api.services.agent_grants` SHALL give:

```python
GRANT_ACTION_PATTERN: Final[str] = r"^[A-Za-z0-9_.:-]{1,64}$"
MIN_GRANT_TTL_SECONDS: Final[int] = 60
MAX_GRANT_TTL_SECONDS: Final[int] = 7_776_000
def decode_wire_id(value: object, prefix: str) -> str | None
async def require_grant_target(session: AsyncSession, principal: AgentPrincipal, agent_ref: object) -> Any
def grant_view(source: Any, now: datetime) -> dict[str, Any]
```
`decode_wire_id` SHALL return the dashed UUID text for a string `<prefix>_` plus 26 Crockford characters or 32 hex
characters, and None for anything else (a plain UUID, a wrong prefix, a wrong length, a non-string). `require_grant_target`
SHALL decode `agent_ref` with prefix `agent`, select `id, status` of that agent pinned to the principal's tenant, and
return the row; it SHALL raise `AgentApiError` 422 `mintkey:invalid_target` with `reason` `invalid_id` for an
undecodable value, 422 with `reason` `self` for the caller's own id, 404 `mintkey:not_found` when no row is found, and
422 with `reason` `agent_not_active` when the status is not `active`. `grant_view` SHALL return `{id, service_id,
agent_id, action, constraints, expires_at, expired, grantor_type, grantor_id, created_at}`: `id` is `source.wire_id` when
present, else `db_uuid_to_wire(source.id, "perm")`; `service_id` and `agent_id` are in `svc_` and `agent_` form;
`constraints` is the dict (a JSON text is parsed, None reads `{}`); the four fields of `grant_wire_fields(source, now)`
are merged in; `created_at` is ISO text or null.

#### Scenario: decoding wire ids
- **WHEN** `decode_wire_id` runs with a canonical `agent_` id, the 32-hex form of the same id, a plain UUID, `svc_` plus a
  valid body with prefix `agent`, a 25-character body and `None`
- **THEN** the first two return the same dashed UUID and the other four return None

#### Scenario: grantee checks
- **WHEN** `require_grant_target` runs for an active agent of the tenant, the caller's own id, `agent_xyz`, an id whose
  tenant-pinned lookup returns no row, and a revoked agent
- **THEN** it returns the row, then raises 422 `self`, 422 `invalid_id`, 404 `mintkey:not_found` and 422
  `agent_not_active`, and the SELECT's parameters hold the principal's tenant

#### Scenario: the view
- **WHEN** `grant_view` runs on a `GrantRecord` with an agent grantor and a past expiry, and on a list row with
  `constraints` as JSON text and a null `expires_at`
- **THEN** the first has its `wire_id` as `id`, `expired` true and `grantor_type` `agent`; the second has the `perm_` form of
  its id, `constraints` as a dict, `expires_at` null and `expired` false; both show `svc_` and `agent_` ids

### Requirement: An owner gives time-boxed access
`POST /v1/agent/grants` SHALL accept `{service_id, agent_id, ttl_seconds, action?, constraints?}` with no other key,
`service_id` a `svc_` id or slug, `ttl_seconds` an integer from `MIN_GRANT_TTL_SECONDS` to `MAX_GRANT_TTL_SECONDS`,
`action` matching `GRANT_ACTION_PATTERN` (default `call`) and `constraints` the closed `Constraints` model of
`admin_api/api/permissions.py`. It SHALL resolve the service with `require_owned_service`, then the grantee with
`require_grant_target`, compute `expires_at = now + ttl_seconds`, and call `write_grant` with `Grantor("agent",
<principal agent id>)` and the same `now`. For a created grant it SHALL write `agent.permission.granted` (payload from
`grant_granted_audit_payload`, `actor_type` `agent`, `actor_id` the caller, `target_type` `permission`) and answer 201
with `grant_view`; for an identical live grant (`created` false) it SHALL answer 200 with the view and write nothing. A
`GrantExpiryError` SHALL answer 422 with the flat body `{"mintkey:code": "invalid_expires_at", "title": "Invalid
expires_at", "reason": <the error's reason>}` that `grant-expiry` answers on the operator route, plus `max_ttl_seconds`
(`agent_grant_max_ttl_seconds()`) when the reason is `expires_at_too_far`; a `GrantConflict` SHALL answer 409
`{"code": "mintkey:grant_conflict", "hint": ...}` with a hint to revoke first. The grantor and the tenant SHALL come from the
principal only. Concurrent requests for the same agent, service and action are serialised by `write_grant` (it takes a
transaction-scoped advisory lock on that key first, as `grant-expiry` specifies), so the second sees the row of the first
and answers 200 or 409, never a duplicate row or a server error.

#### Scenario: a grant is created
- **WHEN** a publisher that owns the service posts a valid body for an active agent, with `ttl_seconds` 3600 and a
  `rate_limit` constraint
- **THEN** the answer is 201; `write_grant` was called once with the principal's tenant, the grantee's and service's DB
  ids, the action `call`, the constraints dict, `Grantor("agent", <caller>)`, and `expires_at` equal to its `now` argument
  plus 3600 seconds, after `set_tenant_context` was called with the principal's tenant; one `agent.permission.granted`
  event names the caller as actor; the view shows `grantor_type` `agent` and the grantor's `agent_` id

#### Scenario: the cap
- **WHEN** `MINTKEY_AGENT_GRANT_MAX_TTL` is `3600` and the route runs with the real `write_grant` over a fake session, for
  `ttl_seconds` 3600 and 3601
- **THEN** the first answers 201; the second answers 422 with `{"mintkey:code": "invalid_expires_at", "title": "Invalid
  expires_at", "reason": "expires_at_too_far", "max_ttl_seconds": 3600}`, and the fake session saw no INSERT and no audit
  event

#### Scenario: an identical grant and a conflict
- **WHEN** `write_grant` (replaced) returns a record with `created` false, and then raises `GrantConflict`
- **THEN** the first answers 200 with the view and writes no event; the second answers 409 `mintkey:grant_conflict`
  and writes no event

#### Scenario: a live grant with another expiry, through the real write path
- **WHEN** the route runs with the real `write_grant` over a fake session whose SELECT of the (tenant, agent, service,
  action) row returns a live grant that expires an hour later than the requested one, and then returns no row
- **THEN** the first answers 409 `mintkey:grant_conflict` with no INSERT and no event, the second answers 201; in both the
  first statement `write_grant` ran holds the advisory lock call

#### Scenario: not the owner
- **WHEN** a publisher grants on a service owned by another agent, on an operator-owned service, on a service of another
  tenant, and on an unknown slug (the fake `require_owned_service` lookups answer as in `agent-service-routes`)
- **THEN** the answers are 403 `mintkey:not_owner`, 403 `mintkey:not_owner`, 404 `mintkey:not_found` and 404
  `mintkey:not_found`; `write_grant` was not called and no event was written; a publisher that only holds a grant on the
  service gets the first answer too

#### Scenario: refused bodies and grantees
- **WHEN** the body has `ttl_seconds` 59, 7776001, `"3600"` or `true`, an `action` of `a b`, a `constraints` key
  `unknown`, an extra key `granted_by` or `tenant_id`, no `agent_id`; or the grantee is the caller, a revoked agent, an
  agent of another tenant, or `agent_xyz`
- **THEN** the bodies answer 422 `validation_failed` with no statement for grants; the grantees answer 422
  `mintkey:invalid_target` (`self`, `agent_not_active`), 404 `mintkey:not_found` and 422 `mintkey:invalid_target`
  (`invalid_id`); `write_grant` was not called

### Requirement: An owner revokes any grant of its service
`POST /v1/agent/grants/{grant_id}/revoke` SHALL decode `grant_id` with `decode_wire_id` (prefix `perm`; 422
`mintkey:invalid_id` with `field` `grant_id` otherwise), select the grant's service pinned to the tenant (404
`mintkey:not_found` when there is no row), resolve that service with `require_owned_service` using its `svc_` id, then
call `delete_grant(session, tenant_id=..., grant_id=<DB id>)`. For the deleted record it SHALL write
`agent.permission.revoked` (payload from `grant_revoked_audit_payload` with `Grantor("agent", <caller>)`, `actor_type`
`agent`), publish `grant_revoked_notify_payload(tenant_id, record, <now>)` on `mintkey:agent` with `notify_change`, and
answer 200 `{"id": <perm wire id>, "revoked": true}`. When `delete_grant` returns None it SHALL answer 404
`mintkey:not_found` and write nothing.

#### Scenario: an owner revokes a grant
- **WHEN** the owner revokes a grant that an operator gave on its service, and then one it gave itself
- **THEN** each answers 200, after `set_tenant_context` was called with the principal's tenant; `delete_grant` ran once
  with the DB id of the grant; each event names the caller as
  `revoked_by` and the original grantor; each NOTIFY payload has `event` `agent.permission.revoked`, `service_id` and
  `revoked_at`

#### Scenario: not the owner, no grant, bad id
- **WHEN** a publisher revokes a grant on another agent's service, on an operator-owned service, a grant id with no row,
  a grant whose `delete_grant` returns None, and `perm_xyz`
- **THEN** the answers are 403 `mintkey:not_owner`, 403 `mintkey:not_owner`, 404 `mintkey:not_found`, 404
  `mintkey:not_found` and 422 `mintkey:invalid_id`; `delete_grant` was called only in the fourth case, and no event and no
  NOTIFY were written in any of them

### Requirement: An owner lists the live grants of its service
`GET /v1/agent/grants?service_id=<svc id or slug>` SHALL resolve the service with `require_owned_service` and answer
`{"service_id": <svc wire id>, "grants": [...]}` with one `grant_view` (plus `agent_name`) per grant of that service whose
`expires_at` is null or in the future, ordered by `created_at`. The SELECT SHALL contain `expires_at IS NULL OR
expires_at > now()` and be pinned to the tenant and the service. A missing `service_id` SHALL answer 422
`validation_failed`.

#### Scenario: the owner's list
- **WHEN** the owner lists a service whose fake SELECT returns two rows
- **THEN** the answer holds two views with `agent_name`, `set_tenant_context` was called first with the principal's
  tenant, the SELECT text contains the live-grant condition, and its parameters hold the tenant and the service's DB id

#### Scenario: not the owner, and no service
- **WHEN** a publisher lists another agent's service, an operator-owned service, an unknown slug, and no `service_id`
- **THEN** the answers are 403 `mintkey:not_owner` twice, 404 `mintkey:not_found` and 422 `validation_failed`, and no
  grant SELECT ran
