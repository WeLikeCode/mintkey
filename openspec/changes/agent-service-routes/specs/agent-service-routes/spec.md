# Agent service routes

## Purpose

A publisher agent registers services and edits the ones it owns through admin-api routes that only an agent key opens. The
routes hang under one router, the service lookup refuses anything the caller does not own, and a target change clears the
stored credential. The credential route is `agent-service-credential`; the MCP tools are `agent-service-tools`.

## ADDED Requirements

### Requirement: The agent routes are separate from the operator routes
`admin_api/api/agent.py` SHALL hold `router = APIRouter(prefix="/v1/agent")` and include the router of
`admin_api/api/agent_services.py`; later changes extend it with `include_router`. Every route of `create_app()` under
`/v1/agent/` SHALL have `require_agent_principal` in its dependency tree and neither `require_tenant_session` nor
`require_platform_admin_session`; no other route SHALL have `require_agent_principal`. No `/v1/agent/` route SHALL use
DELETE, have `transfer` or `role` in its path, or answer GET on a path containing `credential`. `main.py` SHALL import
`router as agent_router` from `admin_api.api.agent` and no other agent router, include it once, register
`agent_api_error_handler` for `AgentApiError`, and make `/v1/agent` CSRF-exempt.

#### Scenario: the route table
- **WHEN** the routes of `create_app()` are walked, and `tests/acceptance/openapi_snapshot.json` is read
- **THEN** the rules hold; `/v1/agent/services` has POST and GET, `/v1/agent/services/{service_ref}` PATCH, and
  `/v1/agent/services/{service_ref}/credential` PUT only; and the snapshot maps `agent` to `/v1/agent`

#### Scenario: a cookie-less POST reaches authentication
- **WHEN** `POST /v1/agent/services` is sent to `create_app()` without cookies and without an `Authorization` header
- **THEN** the answer is 401 with the body `{"code": "mintkey:auth_required"}`, not `mintkey:csrf_missing`

#### Scenario: a consumer key is refused
- **WHEN** a consumer principal calls each of the four routes (`require_agent_principal` overridden to return it)
- **THEN** each answers 403 `mintkey:role_forbidden`, with one `agent.operation.denied` event per call whose operation is
  `POST /v1/agent/services`, `GET /v1/agent/services`, `PATCH /v1/agent/services/x` and `PUT /v1/agent/services/x/credential`
  for the requests sent, and no statement ran

### Requirement: The owned service lookup is one function
`admin_api.services.agent_publishing` SHALL give:

```python
def parse_service_ref(service_ref: str) -> tuple[Literal["id", "slug"], str]
async def require_owned_service(session: AsyncSession, principal: AgentPrincipal, service_ref: str, *,
                                for_update: bool = False) -> Any
def service_view(row: Any) -> dict[str, Any]
```

`parse_service_ref` SHALL return `("id", <dashed UUID>)` for a value starting with `svc_` that `wire_to_db_uuid` decodes,
raise `AgentApiError` 404 `{"code": "mintkey:not_found"}` for one that does not decode, and return `("slug", value)` for any
other value. `require_owned_service` SHALL select the service pinned to the principal's tenant by id or slug (with `FOR
UPDATE` when `for_update` is true) with `owner_agent_id` and `credential_set` (an active row of `credentials` exists), and
return it; no row gives 404 `mintkey:not_found`, a service whose `owner_agent_id` is not the caller's (another agent's or
none) gives 403 `{"code": "mintkey:not_owner"}`. `service_view` SHALL return `{id, name, slug, display_name, description,
base_url, auth_scheme, openapi_url, status, credential_set, created_at, updated_at}` with `id` in `svc_` form, timestamps as
ISO text or null, and `credential_set` a boolean.

#### Scenario: references
- **WHEN** `parse_service_ref` runs with a canonical `svc_` id, the 32-hex form of it, `svc_xyz`, `my-svc.v2` and an empty
  string
- **THEN** the first two return `("id", <the same dashed UUID>)`, `svc_xyz` raises 404 `mintkey:not_found`, and the last two
  return `("slug", ...)`

#### Scenario: ownership
- **WHEN** `require_owned_service` runs for an owned service by id and by slug, a service owned by another agent, one with no
  owner, one of another tenant (the pinned lookup finds no row) and an unknown slug; and once with `for_update=True`
- **THEN** the first two return the row, and the others raise 403 `mintkey:not_owner`, 403 `mintkey:not_owner`, 404
  `mintkey:not_found` and 404 `mintkey:not_found`; every SELECT binds the principal's tenant, and the statement of the run with
  `for_update=True` contains `FOR UPDATE` while the others do not

#### Scenario: the view
- **WHEN** `service_view` runs on a row with a credential flag true and a row with no timestamps
- **THEN** the first shows `credential_set` true and an `svc_` id, the second shows null timestamps; neither has a key beyond
  the twelve above

### Requirement: A publisher creates a service
`POST /v1/agent/services` SHALL accept `{name, base_url, auth_scheme, display_name?, description?, openapi_url?}` with no other
key, `name` matching `^[A-Za-z0-9][A-Za-z0-9 ._-]{0,62}$` whose slug (`name.lower().replace(" ", "-")`) does not start with
`svc_`, and `auth_scheme` one of `bearer_token`, `api_key_header`, `api_key_query`, `basic_auth`; check `base_url` and
`openapi_url` with `check_agent_target_url` (400 `mintkey:target_not_allowed` with `field` and `reason`); set the tenant
context from the principal; answer 409 `mintkey:slug_conflict` when the slug exists in the tenant; insert the service with
`owner_agent_id` and `created_by_agent_id` equal to the caller; write `service.registered` and a `mintkey:service` NOTIFY; and
answer 201 with `service_view`. The service id SHALL be derived as `create_service` of `admin_api/api/services.py` does.

#### Scenario: a service is created
- **WHEN** a publisher posts a valid body
- **THEN** the answer is 201 with `credential_set` false and `status` `active`; the INSERT binds the principal's tenant, the
  agent as owner and creator, and the derived slug; one `service.registered` event (actor the agent, payload `{service_id,
  name, base_url, auth_scheme, actions: [], display_name, owner_agent_id}` with `svc_` and `agent_` ids and `display_name`
  the given one or the name) and one NOTIFY were sent; the tenant context was set first

#### Scenario: refused bodies
- **WHEN** the body has `auth_scheme` `ssh_private_key` or `oauth2_client_credentials`, `name` `../x` or `svc_0 x`, an extra key
  `owner_agent_id` or `status`, or `base_url` `http://example.com` or a name that resolves to `10.0.0.1`
- **THEN** the first six answer 422 `validation_failed`, the `http` URL 400 `target_not_allowed` reason `not_https`, the
  private name 400 reason `non_public_address` with `field` `base_url`; none ran an INSERT

#### Scenario: a taken slug
- **WHEN** the slug exists, and when the INSERT raises `IntegrityError`
- **THEN** both answer 409 `mintkey:slug_conflict`, and the first ran no INSERT

### Requirement: A publisher lists its own services
`GET /v1/agent/services` SHALL return `{"services": [...]}` with the `service_view` of every service of the principal's
tenant whose `owner_agent_id` is the caller, ordered by `created_at`.

#### Scenario: the list is the caller's
- **WHEN** a publisher lists services, and then lists with no owned service
- **THEN** the SELECT binds the principal's tenant and agent as owner; the first answer holds objects with the view keys, the
  second `{"services": []}`

### Requirement: A publisher updates only its own services
`PATCH /v1/agent/services/{service_ref}` SHALL accept any of `base_url`, `auth_scheme`, `display_name`, `description`,
`openapi_url` (at least one, no other key), `auth_scheme` one of `bearer_token`, `api_key_header`, `api_key_query`,
`basic_auth` (any other value, `ssh_private_key` included, answers 422 `validation_failed`). It SHALL resolve the service
through `require_owned_service(..., for_update=True)`; check a changed `base_url` or `openapi_url` with
`check_agent_target_url`; and, for a changed value, update the row and write `service.updated` with `fields_changed`. When
`base_url` or `auth_scheme` changes it SHALL delete the service's `vault.credentials` and `credentials` rows in the same
transaction and, when a credential existed, write `service.credential.cleared` (reason `target_changed`); the answer is the
view plus `credential_cleared`. A value equal to the stored one is no change: no UPDATE, no event, no resolution.

#### Scenario: a metadata edit keeps the credential, a changed target clears it
- **WHEN** a publisher patches `display_name`; then `base_url` to a public name; then `auth_scheme` from `bearer_token` to
  `basic_auth`, of an owned service with a credential
- **THEN** the first runs one UPDATE, `service.updated` lists `display_name`, no statement names `vault.credentials`, and
  `credential_cleared` is false; the other two answer `credential_cleared` true, delete from `vault.credentials` and
  `credentials` before the answer, and write `service.updated` (listing `base_url`, then `auth_scheme`) and
  `service.credential.cleared`, both with the agent as actor

#### Scenario: a changed target without a credential, nothing changed, refused
- **WHEN** a `base_url` patch runs on a service with no credential; the patch repeats the stored `base_url`; and it sets
  `base_url` to `https://10.0.0.1/`
- **THEN** the first runs the deletions with `credential_cleared` false and no `service.credential.cleared` event; the
  second answers 200 with no UPDATE, no event and no resolver call; the third answers 400 `target_not_allowed` with no
  UPDATE and no DELETE

#### Scenario: not the owner
- **WHEN** a publisher patches a service owned by another agent, one with no owner, one of another tenant and an unknown slug
- **THEN** the answers are 403 `mintkey:not_owner`, 403 `mintkey:not_owner`, 404 `mintkey:not_found` and 404
  `mintkey:not_found`, and no UPDATE ran

#### Scenario: refused bodies
- **WHEN** the body is `{}`, `{"name": "x"}`, `{"status": "disabled"}`, `{"auth_scheme": "ssh_private_key"}`, `{"auth_scheme":
  "oauth2_client_credentials"}` or `{"auth_scheme": "none"}`
- **THEN** each answers 422 `validation_failed` and runs no statement for the service

#### Scenario: the row is locked first
- **WHEN** a patch runs on an owned service
- **THEN** the first statement that names `services` after the tenant context contains `FOR UPDATE`, and every UPDATE and
  DELETE comes after it
