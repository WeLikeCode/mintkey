# Agent principal

## Purpose

An agent calls admin-api only with its own key. This capability turns a Bearer agent key into a principal (tenant, agent,
role), refuses a role that is too low and records the refusal, and shares the key check with the endpoint the MCP server
already uses.

## ADDED Requirements

### Requirement: The key check is one function
`admin_api.api.internal.check_agent_key(session: AsyncSession, api_key: str) -> tuple[Any | None, JSONResponse | None]` SHALL
run the lookup, the argon2 verify and the status and expiry branches that `validate_agent_key` runs, and return `(row,
None)` with a row that has `id`, `tenant_id`, `status` and `role`, or `(None, response)` with the 401 or 503 response
`validate-agent-key` answers. `validate_agent_key` SHALL call it and answer exactly as before: the same bodies and
statuses, the verify still going through `internal._verify_argon2`, and the 200 body `{"agent_id", "tenant_id", "status",
"role"}` with the role read as `normalize_role(getattr(row, "role", None))`.

#### Scenario: the check returns the row or the answer
- **WHEN** `check_agent_key` runs over a fake session for a valid active key (row with role `publisher`), an unknown key, an
  expired key and a verify that raises the capacity error
- **THEN** the first returns the row and None; the others return None and the 401, 401 and 503 responses with the bodies of
  `validate-agent-key`

#### Scenario: the endpoint is unchanged
- **WHEN** `validate_agent_key` runs for a valid key whose row has no `role` attribute, and
  `tests/unit/admin_api/test_validate_agent_key_errors.py` runs unchanged
- **THEN** the 200 body has `role` `consumer` with the other three keys, and the existing tests pass

### Requirement: An agent key yields a principal
`admin_api.auth.agent_principal` SHALL give:

```python
@dataclass(frozen=True)
class AgentPrincipal:
    tenant_id: UUID
    agent_id: UUID
    role: str
class AgentApiError(Exception):      # every error of a /v1/agent route; body is the JSON answer
    status_code: int
    body: dict[str, Any]
    headers: dict[str, str] | None
    def __init__(self, status_code: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> None
async def agent_api_error_handler(request: Request, exc: Exception) -> JSONResponse
async def require_agent_principal(request: Request) -> AgentPrincipal
```

`agent_api_error_handler` SHALL answer `exc.status_code` with the JSON `exc.body` and the headers of `exc`.
`require_agent_principal` SHALL read only `Authorization: Bearer mk_agent_...`, run `check_agent_key` in a session of its
own taken from `AsyncSessionLocal` (closed before it returns), and yield the principal with the role through
`normalize_role`. Without such a header it SHALL raise `AgentApiError` 401 `{"code": "mintkey:auth_required"}` and not call
`check_agent_key`; for a rejected key it SHALL raise `AgentApiError` with the status and body of the response
`check_agent_key` returned.

#### Scenario: a publisher key
- **WHEN** a request carries a valid publisher key (`check_agent_key` patched to return the row)
- **THEN** the dependency yields the principal (the agent's and tenant's UUIDs, role `publisher`), and the key check ran in
  the session of the patched `AsyncSessionLocal`, which was closed afterwards

#### Scenario: no usable credential
- **WHEN** the request has no header, `Authorization: Basic x`, `Bearer not_an_agent_key`, only `X-API-Key: mk_agent_x`, or
  only a `mintkey_session` cookie
- **THEN** each raises 401 `mintkey:auth_required` and `check_agent_key` was not called

#### Scenario: rejected keys
- **WHEN** `check_agent_key` answers the unknown-key 401, the expired-key 401 and the 503
- **THEN** the dependency raises `AgentApiError` with those statuses and bodies, and the handler turns each into the same
  HTTP answer (status, JSON body and headers)

#### Scenario: the route's transaction never sees the platform view
- **WHEN** a route runs behind `require_agent_principal` with its own `get_db_session` fake
- **THEN** no statement of that fake contains `platform_admin_view`

### Requirement: A role that is too low is refused and recorded
`admin_api.auth.agent_principal` SHALL also give:

```python
async def require_publisher_principal(request: Request,
    principal: AgentPrincipal = Depends(require_agent_principal)) -> AgentPrincipal
async def record_denied_operation(principal: AgentPrincipal, operation: str) -> None
```

`require_publisher_principal` SHALL return the principal when its role is `publisher`. For another role it SHALL call
`record_denied_operation(principal, f"{request.method} {request.url.path}")` (the operation string cut to 256 characters) and
raise `AgentApiError` 403 `{"code": "mintkey:role_forbidden", "role": <role>, "required_role": "publisher", "hint": <text>}`.
`record_denied_operation` SHALL write, in a session of its own from `AsyncSessionLocal` that it commits, the audit event
`agent.operation.denied` with `actor_type` `agent`, `actor_id` the agent, `target_type` `agent`, and the payload
`{"agent_id": <agent_ wire id>, "role": <role>, "operation": <operation>}`. When the write raises, it SHALL log the failure and
return, so the 403 is still answered.

#### Scenario: the wrong role is refused with a literal operation
- **WHEN** a consumer principal reaches `require_publisher_principal` for `POST /v1/agent/probe`, and a publisher reaches it
  for the same request
- **THEN** the consumer gets 403 `mintkey:role_forbidden` with `required_role` `publisher`, and one `agent.operation.denied`
  event whose payload is exactly `{"agent_id": "agent_...", "role": "consumer", "operation": "POST /v1/agent/probe"}` was written
  through the patched session factory and committed; the publisher gets its principal and no event

#### Scenario: the record itself fails
- **WHEN** `audit_emit` raises while a consumer is refused
- **THEN** the answer is still 403 `mintkey:role_forbidden` and the failure was logged

### Requirement: The contract lists the denied-operation event
`docs/architecture/contracts/events/audit-event.schema.json` SHALL define `ev_agent_operation_denied` (`event_type`
`agent.operation.denied`, `target_type` `agent`, payload with exactly `agent_id`, `role` and `operation`, all required,
`additionalProperties` false, `role` one of `consumer` and `publisher`, `operation` a string of at most 256 characters),
referenced from `oneOf` and from `discriminator.mapping`.

#### Scenario: the contract lists it
- **WHEN** the schema is loaded as JSON
- **THEN** the definition has the payload properties and constraints above, `agent.operation.denied` is a key of
  `discriminator.mapping`, and the `$ref` of the definition is in `oneOf`
