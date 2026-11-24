# Agent principal

## Purpose

An agent calls admin-api only with its own key. This capability turns a Bearer agent key into a principal (tenant, agent,
role), refuses a role that is too low and records the refusal, and shares the key check with the endpoint the MCP server
already uses.

## ADDED Requirements

### Requirement: The key check is one function
`admin_api.api.internal.check_agent_key(session: AsyncSession, api_key: str) -> tuple[Any | None, JSONResponse | None]` SHALL
run, in the session it is given and in this order, the statement `validate_agent_key` issues first at the base (a single
`SELECT set_config('app.current_tenant', '00000000-0000-0000-0000-000000000000', true), set_config('app.platform_admin_view',
'on', true)`), the lookup of `agents` by key fingerprint, the argon2 verify and the status and expiry branches, and return
`(row, None)` with a row that has `id`, `tenant_id`, `status` and `role`, or `(None, response)` with the 401 or 503 response
`validate-agent-key` answers. It is the only function that turns the platform view on for a key check, and only in the
session it is given: the caller owns that session and closes it. `validate_agent_key` SHALL call it, issue no statement of
its own, and answer exactly as before this change (bodies and statuses, the verify still going through
`internal._verify_argon2`; the 200 body and its `role` are those of `agent-roles-and-ownership`).

#### Scenario: the check returns the row or the answer
- **WHEN** `check_agent_key` runs over a recording fake session for a valid active key (row with role `publisher`), an
  unknown key, an expired key and a verify that raises the capacity error
- **THEN** the first returns the row and None, and for every call the first recorded statement contains
  `set_config('app.platform_admin_view', 'on', true)` and the second contains `FROM agents`; the other three return None and
  the 401, 401 and 503 responses with the bodies of `validate-agent-key`

#### Scenario: the endpoint is unchanged
- **WHEN** `validate_agent_key` runs over a recording fake session for a valid key, and
  `tests/unit/admin_api/test_validate_agent_key_errors.py` runs unchanged
- **THEN** the session recorded exactly the two statements above and `validate_agent_key` issued none of them itself, and
  the existing tests pass

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
`require_agent_principal` SHALL read only `Authorization: Bearer mk_agent_...`, open a dedicated session from
`AsyncSessionLocal`, run `check_agent_key` in it, commit it (so an expiry audit event the check writes is stored) and close
it before the dependency returns, whatever the outcome, and yield the principal with the role through `normalize_role`. Only
that dedicated session may have `app.platform_admin_view` set to `on`: the session a `/v1/agent/` route gets from
`get_db_session` is a different object, opened after the dedicated one is closed, and never has that setting turned on. Without
a Bearer `mk_agent_` header it SHALL raise `AgentApiError` 401 `{"code": "mintkey:auth_required"}` and open no session; for a
rejected key it SHALL raise `AgentApiError` with the status and body of the response `check_agent_key` returned; when opening
the session, `check_agent_key` or the commit raises, it SHALL raise `AgentApiError` 503 with the body
`{"mintkey:code": "mintkey:verify_unavailable"}`, the session closed and no principal.

#### Scenario: a publisher key
- **WHEN** a request carries a valid publisher key (`check_agent_key` patched to return the row)
- **THEN** the dependency yields the principal (the agent's and tenant's UUIDs, role `publisher`), and the key check ran in
  the session of the patched `AsyncSessionLocal`, which was closed afterwards

#### Scenario: no usable credential
- **WHEN** the request has no header, `Authorization: Basic x`, `Bearer not_an_agent_key`, only `X-API-Key: mk_agent_x`, or
  only a `mintkey_session` cookie
- **THEN** each raises 401 `mintkey:auth_required`, `check_agent_key` was not called and no session was opened

#### Scenario: rejected keys
- **WHEN** `check_agent_key` answers the unknown-key 401, the expired-key 401 and the 503
- **THEN** the dependency raises `AgentApiError` with those statuses and bodies, and the handler turns each into the same
  HTTP answer (status, JSON body and headers)

#### Scenario: the database fails while the key is checked
- **WHEN** `AsyncSessionLocal()` raises `RuntimeError`, and then `check_agent_key` raises `RuntimeError` inside a session
- **THEN** both calls raise `AgentApiError` 503 with `{"mintkey:code": "mintkey:verify_unavailable"}`, and in the second the
  session was closed

#### Scenario: the route's session never sees the platform view
- **WHEN** a probe route with `require_agent_principal` and the route session from `get_db_session` runs `set_tenant_context`
  and one SELECT; the real `check_agent_key` runs with `internal._verify_argon2` patched; `AsyncSessionLocal` is a factory of
  recording fake sessions and `get_db_session` is overridden with another recording fake, both appending to one event list
- **THEN** the key session recorded the `set_config('app.platform_admin_view', 'on', true)` statement first and then closed;
  the route session is another object, recorded its first statement after that close, and none of its statements or
  parameters contains `platform_admin_view` or the text `'on'`

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
`record_denied_operation` SHALL, in a session of its own from `AsyncSessionLocal`, call `set_tenant_context(session,
principal.tenant_id)` (never the platform view), then `audit_emit` for the event `agent.operation.denied` with `tenant_id`
the principal's, `actor_type` `agent`, `actor_id` and `target_id` the agent's UUID, `target_type` `agent`, and the payload
`{"agent_id": <agent_ wire id>, "role": <normalized role>, "operation": <operation>}`, and commit. When any of that raises, it
SHALL log the failure and return, so the 403 is still answered.

#### Scenario: the wrong role is refused with a literal operation
- **WHEN** a consumer principal reaches `require_publisher_principal` for `POST /v1/agent/probe`, and a publisher reaches it
  for the same request
- **THEN** the consumer gets 403 `mintkey:role_forbidden` with `required_role` `publisher`, and one `agent.operation.denied`
  event was written through the patched session factory and committed, after a first statement that binds the principal's
  tenant and with no statement containing `platform_admin_view`; its `audit_emit` call has `actor_id` and `target_id` equal to
  the agent's UUID, `actor_type` and `target_type` `agent`, and the payload exactly `{"agent_id": "agent_...", "role":
  "consumer", "operation": "POST /v1/agent/probe"}`; the publisher gets its principal and no event

#### Scenario: the record itself fails
- **WHEN** `audit_emit` raises while a consumer is refused, and then `AsyncSessionLocal()` raises
- **THEN** both answers are still 403 `mintkey:role_forbidden` and each failure was logged

### Requirement: The contract lists the denied-operation event
`docs/architecture/contracts/events/audit-event.schema.json` SHALL define `ev_agent_operation_denied` (`event_type`
`agent.operation.denied`, `target_type` `agent`, payload with exactly `agent_id`, `role` and `operation`, all required,
`additionalProperties` false, `role` one of `consumer` and `publisher`, `operation` a string of at most 256 characters),
referenced from `oneOf` and from `discriminator.mapping`; the envelope's `actor_type` enum already lists `agent` and the
definition adds no enum value.

#### Scenario: the contract lists it
- **WHEN** the schema is loaded as JSON
- **THEN** the definition has the payload properties and constraints above, `agent.operation.denied` is a key of
  `discriminator.mapping`, the `$ref` of the definition is in `oneOf`, and `actor_type` of the envelope allows `agent`
