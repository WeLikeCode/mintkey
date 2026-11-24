# Agent service publishing

## Purpose

A publisher agent registers services, edits the ones it owns and stores their credentials through admin-api routes that
only an agent key opens. A credential is write-only and bound to its target. The egress rule is `agent-egress-policy`;
the MCP tools and their role registry are `agent-tool-roles`.

## ADDED Requirements

### Requirement: An agent key authenticates the /v1/agent routes
`admin_api.auth.agent_principal` SHALL give:

```python
@dataclass(frozen=True)
class AgentPrincipal:
    tenant_id: UUID
    agent_id: UUID
    role: str
class AgentApiError(Exception):      # every error of a /v1/agent route; body is the JSON answer
    def __init__(self, status_code: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> None
async def agent_api_error_handler(request: Request, exc: Exception) -> JSONResponse
async def require_agent_principal(request: Request) -> AgentPrincipal
async def require_publisher_principal(request: Request,
    principal: AgentPrincipal = Depends(require_agent_principal)) -> AgentPrincipal
async def record_denied_operation(principal: AgentPrincipal, operation: str) -> None
```

`internal.check_agent_key(session, api_key) -> tuple[Any | None, JSONResponse | None]` SHALL return the row (`id, tenant_id,
status, role`) or the 401/503 response `validate-agent-key` answers, which SHALL answer exactly as before.
`admin_api.services.agent_publishing` SHALL give `require_owned_service(session, principal, service_ref) -> Any` (the service
row, or `AgentApiError` 404 `mintkey:not_found` / 403 `mintkey:not_owner`; `service_ref` is an `svc_...` id, else a slug) and
`service_view(row) -> dict[str, Any]`. `admin_api/api/agent.py` SHALL hold `router = APIRouter(prefix="/v1/agent")`, which
later changes extend with `include_router`.

`require_agent_principal` SHALL read only `Authorization: Bearer mk_agent_...`, run `check_agent_key` in a session of its own
from `AsyncSessionLocal`, and yield the principal (role through `normalize_role`). Without such a header it SHALL raise 401
`{"code": "mintkey:auth_required"}`; for a rejected key, the status and body `validate-agent-key` answers.
`require_publisher_principal` SHALL raise 403 `mintkey:role_forbidden` for another role after `record_denied_operation`
wrote `agent.operation.denied` (`actor_type` `agent`, payload `{agent_id, role, operation}`) in a session of its own.

#### Scenario: a publisher key
- **WHEN** a request carries a valid publisher key
- **THEN** the dependency yields the principal (the agent's and tenant's UUIDs, role `publisher`), and the key check ran in
  the session of the patched `AsyncSessionLocal`

#### Scenario: no usable credential
- **WHEN** the request has no header, `Authorization: Basic x`, `Bearer not_an_agent_key`, only `X-API-Key: mk_agent_x`, or
  only a `mintkey_session` cookie
- **THEN** each raises 401 `mintkey:auth_required` and `check_agent_key` was not called

#### Scenario: rejected keys and the wrong role
- **WHEN** `check_agent_key` answers the unknown-key 401, the expired-key 401 and the 503; and `require_publisher_principal`
  receives a consumer
- **THEN** the dependency raises `AgentApiError` with those statuses and bodies; for the consumer 403 `mintkey:role_forbidden`
  with `required_role` `publisher`, after one `agent.operation.denied` event through the patched session factory

#### Scenario: the route's transaction never sees the platform view
- **WHEN** a route runs behind `require_agent_principal` with its own `get_db_session` fake
- **THEN** no statement of that fake contains `platform_admin_view`, and
  `tests/unit/admin_api/test_validate_agent_key_errors.py` passes unchanged

### Requirement: The agent routes are separate from the operator routes
Every route of `create_app()` under `/v1/agent/` SHALL have `require_agent_principal` in its dependency tree and neither
`require_tenant_session` nor `require_platform_admin_session`; no other route SHALL have `require_agent_principal`. No
`/v1/agent/` route SHALL use DELETE, have `transfer` or `role` in its path, or answer GET on a path containing `credential`.
`create_app()` SHALL register `agent_api_error_handler` for `AgentApiError`, make `/v1/agent` CSRF-exempt, and import only
`admin_api/api/agent.py` of the agent routers.

#### Scenario: the route table
- **WHEN** the routes of `create_app()` are walked, and `tests/acceptance/openapi_snapshot.json` is read
- **THEN** the rules hold; `/v1/agent/services` has POST and GET, `/v1/agent/services/{service_ref}` PATCH, and
  `/v1/agent/services/{service_ref}/credential` PUT only; and the snapshot maps `agent` to `/v1/agent`

#### Scenario: a cookie-less POST reaches authentication
- **WHEN** `POST /v1/agent/services` is sent to `create_app()` without cookies and without an `Authorization` header
- **THEN** the answer is 401 with the body `{"code": "mintkey:auth_required"}`, not `mintkey:csrf_missing`

### Requirement: A publisher creates a service
`POST /v1/agent/services` SHALL accept `{name, base_url, auth_scheme, display_name?, description?, openapi_url?}` with no other
key, `name` matching `^[A-Za-z0-9][A-Za-z0-9 ._-]{0,62}$` and `auth_scheme` one of `bearer_token`, `api_key_header`,
`api_key_query`, `basic_auth`; check `base_url` and `openapi_url` with `check_agent_target_url` (400
`mintkey:target_not_allowed` with `field` and `reason`); set the tenant context from the principal; answer 409
`mintkey:slug_conflict` when the slug (`name.lower().replace(" ", "-")`) exists in the tenant; insert the service with
`owner_agent_id` and `created_by_agent_id` equal to the caller; write `service.registered` and a `mintkey:service`
NOTIFY; and answer 201 with the service view `{id, name, slug, display_name, description, base_url, auth_scheme, openapi_url,
status, credential_set, created_at, updated_at}`.

#### Scenario: a service is created
- **WHEN** a publisher posts a valid body
- **THEN** the answer is 201 with `credential_set` false and `status` `active`; the INSERT binds the principal's tenant, the
  agent as owner and creator, and the derived slug; one `service.registered` event (actor the agent, payload `{service_id,
  name, base_url, auth_scheme, actions: [], display_name, owner_agent_id}` with `svc_` and `agent_` ids and `display_name`
  the given one or the name) and one NOTIFY were sent; the tenant context was set first

#### Scenario: refused bodies
- **WHEN** the body has `auth_scheme` `ssh_private_key` or `oauth2_client_credentials`, `name` `../x`, an extra key
  `owner_agent_id` or `status`, or `base_url` `http://example.com` or a name that resolves to `10.0.0.1`
- **THEN** the first five answer 422 `validation_failed`, the `http` URL 400 `target_not_allowed` reason `not_https`, the
  private name 400 reason `non_public_address` with `field` `base_url`; none ran an INSERT

#### Scenario: a taken slug
- **WHEN** the slug exists, and when the INSERT raises `IntegrityError`
- **THEN** both answer 409 `mintkey:slug_conflict`, and the first ran no INSERT

### Requirement: A publisher lists and updates only its own services
`GET /v1/agent/services` SHALL return `{"services": [...]}` of the tenant's services owned by the caller. `PATCH /v1/agent/services/{service_ref}` SHALL accept any of `base_url`, `auth_scheme`, `display_name`, `description`,
`openapi_url` (at least one, no other key); resolve `service_ref` through `require_owned_service`; check a changed
`base_url` or `openapi_url` with `check_agent_target_url`; and, for a changed value, update the row and write
`service.updated` with `fields_changed`. When `base_url` or `auth_scheme` changes it SHALL delete the service's
`vault.credentials` and `credentials` rows in the same transaction and, when a credential existed, write
`service.credential.cleared`; the answer is the view plus `credential_cleared`. A value equal to the stored one is no
change: no UPDATE, no event, no resolution.

#### Scenario: the list is the caller's
- **WHEN** a publisher lists services
- **THEN** the SELECT binds the principal's tenant and agent as owner; the objects hold the view keys

#### Scenario: a metadata edit keeps the credential, a changed target clears it
- **WHEN** a publisher patches `display_name`; then `base_url` to a public name; then `auth_scheme`, of an owned service with
  a credential
- **THEN** the first runs one UPDATE, `service.updated` lists `display_name`, no statement names `vault.credentials`, and
  `credential_cleared` is false; the other two answer `credential_cleared` true, delete from `vault.credentials` and
  `credentials` before the answer, and write `service.updated` and `service.credential.cleared` (reason `target_changed`),
  both with the agent as actor

#### Scenario: a changed target without a credential, nothing changed, refused
- **WHEN** a `base_url` patch runs on a service with no credential; the patch repeats the stored `base_url`; and it sets
  `base_url` to `https://10.0.0.1/`
- **THEN** the first runs the deletions with `credential_cleared` false and no `service.credential.cleared` event; the
  second answers 200 with no UPDATE, no event and no resolver call; the third answers 400 `target_not_allowed` with no
  UPDATE and no DELETE

#### Scenario: not the owner
- **WHEN** a publisher patches a service owned by another agent, one with no owner, one of another tenant (the pinned
  lookup finds no row) and an unknown slug
- **THEN** the answers are 403 `mintkey:not_owner`, 403 `mintkey:not_owner`, 404 `mintkey:not_found` and 404 `mintkey:not_found`,
  and no UPDATE ran

#### Scenario: refused bodies
- **WHEN** the body is `{}`, `{"name": "x"}` or `{"status": "disabled"}`
- **THEN** each answers 422 `validation_failed` and runs no statement for the service

### Requirement: A credential is written, never read, and bound to its target
`PUT /v1/agent/services/{service_ref}/credential` SHALL read its JSON body itself, not through request-model validation, so
that no refusal echoes the input: it SHALL answer 422 `{"code": "mintkey:validation_failed", "field": <name>, "title": <fixed
text>}` for a body that is not a JSON object, has a key other than `value`, `header_name` and `query_param`, or has a bad
field. It accepts `{value, header_name?, query_param?}`, `value` 1 to 8192 characters without CR, LF or NUL, for an owned
service only. `api_key_header` needs `header_name` (`^[A-Za-z0-9-]{1,64}$`, not `host`, `content-length`,
`transfer-encoding`, `connection` or `x-mintkey-*`, any case), `api_key_query` needs `query_param`
(`^[A-Za-z0-9_.-]{1,64}$`), the other schemes take neither. The route SHALL call `VaultAdapterClient.put_credential` once
with the service's `auth_scheme`, `base_url` as `target_url` and `egress_scope="public"` (the parameter added by
`proxy-public-egress`); in the request's transaction supersede
the active `credentials` rows of the service, insert the new metadata row and set `services.current_key_version`; write
`service.credential.set`; and answer 200 with exactly `{service_id, credential_set: true, updated_at}`. Neither the response,
an audit payload, nor any statement parameter SHALL contain the value, a hash, a prefix, a length or a fingerprint of it.
A vault failure SHALL answer 502 `mintkey:vault_unavailable` before any statement or event.

#### Scenario: a bearer credential
- **WHEN** a publisher puts the value `s3cret-value-123` on an owned `bearer_token` service
- **THEN** `put_credential` was called once with that value as `plaintext`, the base URL as `target_url` and `egress_scope`
  `public`, and no statement names `egress_scope`; the answer has exactly the three keys; and the text of the
  response, of every `audit_emit` call and of every statement and its parameters does not contain `s3cret-value-123`

#### Scenario: header and query names
- **WHEN** an `api_key_header` service gets no `header_name`, `Host`, `X-Mintkey-Test`, then `X-Api-Key`; a `bearer_token`
  service gets a `header_name`; an `api_key_query` service gets no `query_param`
- **THEN** all but the fourth answer 422 `mintkey:validation_failed`; the fourth answers 200 with `X-Api-Key` passed to
  `put_credential`

#### Scenario: bad values, other owners, a failing vault
- **WHEN** the value is empty, 8193 characters long or `s3cret-value-123` plus a line feed; the service belongs to another
  agent; or `put_credential` raises
- **THEN** the answers are 422 `mintkey:validation_failed` three times (no body contains `s3cret-value-123`), 403
  `mintkey:not_owner` and 502 `mintkey:vault_unavailable`; no metadata statement and no event ran

### Requirement: The new events are in the audit contract
`audit-event.schema.json` SHALL define `ev_agent_operation_denied` (payload `{agent_id, role, operation}`),
`ev_service_credential_set` (`{service_id, key_version, auth_scheme}`) and `ev_service_credential_cleared` (`{service_id, reason,
fields_changed}`), none holding a credential, each in `oneOf` and `discriminator.mapping`; add `owner_agent_id` to the payload
properties of `ev_service_registered`; and add `auth_scheme` to the `fields_changed` enum of `ev_service_updated`.

#### Scenario: the contract lists them
- **WHEN** the schema is loaded as JSON
- **THEN** the three definitions, their mapping and `oneOf` entries, and the two additions exist
