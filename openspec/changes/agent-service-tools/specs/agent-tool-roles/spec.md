# Agent tool roles

## Purpose

Which MCP tools an agent sees and may call depends on its role. One registry decides, one function refuses and records the
refusal, and `tools/list` shows a role only what it may call.

## ADDED Requirements

### Requirement: The role registry decides which tools an agent sees and may call
`mcp_server.policy.roles` SHALL give:

```python
ROLE_FORBIDDEN_RPC_CODE: Final[int] = -32003
CONSUMER_TOOLS: Final[frozenset[str]]   # the ten tools now in TOOLS (mintkey_bootstrap, mintkey_list_services,
    # mintkey_discover, mintkey_describe_service, mintkey_get_openapi, mintkey_request_token, secret_put, secret_get,
    # secret_list, secret_delete), plus mintkey_request_access, mintkey_list_my_access_requests,
    # mintkey_cancel_access_request: 13 names
PUBLISHER_TOOLS: Final[frozenset[str]]  # CONSUMER_TOOLS plus mintkey_service_create, mintkey_service_update,
    # mintkey_service_set_credential, mintkey_list_my_services, mintkey_grant_access, mintkey_revoke_access,
    # mintkey_list_service_grants, mintkey_list_incoming_access_requests, mintkey_decide_access_request: 22 names
def agent_role(agent_ctx: dict[str, Any] | None) -> str           # normalize_role(ctx.get("role")); None reads {}
def tool_allowed(role: str, tool_name: str) -> bool
async def enforce_tool_role(session: AsyncSession, agent_ctx: dict[str, Any], tool_name: str) -> JSONResponse | None
```

`tool_allowed` SHALL be false for a name in neither set, and an unknown role SHALL use the consumer set. `tools/list` SHALL
return the entries of `TOOLS` for which `tool_allowed` is true for the caller's role, so a name that is in a set but not yet
in `TOOLS` is not listed. A later change adds its tool to `TOOLS`, a router and a REST path without editing the sets.
`enforce_tool_role` SHALL return None for an allowed tool, and otherwise write the audit event `agent.operation.denied`
(`actor_type` `agent`, payload `{agent_id, role, operation}` with `operation` equal to `tool_name`) and return 403
`{"code": "mintkey:role_forbidden", "tool", "role", "required_role": "publisher", "hint"}`; when the event write raises it
SHALL log the failure and still return the 403.

#### Scenario: the sets
- **WHEN** the sets are read
- **THEN** `CONSUMER_TOOLS` has the 13 names above and `PUBLISHER_TOOLS` the 22, the first is a subset of the second, no name contains
  `transfer` or `role`, the only name containing `delete` is `secret_delete` (an agent's own secret), and the only name
  containing `credential` is `mintkey_service_set_credential`

#### Scenario: allowed, refused and unknown
- **WHEN** `enforce_tool_role` runs for a publisher on `mintkey_service_create`, a consumer on it, a consumer on
  `mintkey_request_token` and a publisher on `mintkey_made_up`; and `agent_role` runs on a context with no role, one with
  `"admin"` and `None`
- **THEN** the results are None, a 403, None, and a 403; the two refusals each wrote one `agent.operation.denied` event whose
  `operation` is `mintkey_service_create` and `mintkey_made_up`; the three roles read `consumer`

#### Scenario: the record fails
- **WHEN** `audit_emit` raises while a consumer is refused `mintkey_service_create`
- **THEN** the result is still the 403 `mintkey:role_forbidden`, and the failure was logged
