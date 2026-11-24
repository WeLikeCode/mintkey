# Design: agent-principal-and-egress

## Context

Facts at the base (staging `2c4c814`) plus the changes merged before this one; the requirements name symbols.

- Agent keys are checked by `POST /v1/internal/validate-agent-key` in `admin_api/api/internal.py`, whose first statement sets
  `app.platform_admin_view` to `on` (with a sentinel `app.current_tenant`) for its transaction; `set_tenant_context` never
  turns it off. Its test patches `internal._verify_argon2` and feeds two `execute` results: that statement and the lookup.
- `CsrfMiddleware` refuses a cookie-less POST outside `csrf_exempt` paths; a later change exempts `/v1/agent`.
- The operator-side check `resolve_hostname_is_private` (`admin_api/services/credential_service.py`) takes no deny list and
  does not refuse a name that fails to resolve; agents use `mintkey_models.egress`, which does both.

## Relied on (given by the named change; not redefined here)

- `agent-roles-and-ownership`: `mintkey_models.roles.normalize_role(value: object) -> str` (always `consumer` or
  `publisher`), the column `agents.role`, and the key check selecting `role` with the agent and answering
  `{"agent_id", "tenant_id", "status", "role"}`. This change reads the role exactly as that change does:
  `normalize_role(getattr(row, "role", None))`.
- Delivered before it through that change: `tenant-session-routes` and `grant-expiry`; this change relies on nothing from them.

## Decisions

**D1. The key check is shared and runs outside the route's transaction.** It moves to `internal.check_agent_key`, which
issues the `set_config` statement (platform view on) as its own first statement and then the lookup, so the view is turned on
only in the session the check is given; `validate_agent_key` calls it and issues nothing itself, so its two statements and
its behaviour are unchanged. `require_agent_principal` opens a dedicated session from `AsyncSessionLocal`, runs the check,
commits and closes it before the route's session opens, so `platform_admin_view` is never on in a route's transaction; each
later route calls `set_tenant_context(session, principal.tenant_id)` and pins its statements to the tenant. The tenant
always comes from the principal, never from a path or a body. A database failure while checking is a 503
`mintkey:verify_unavailable`, never a principal.

**D2. Only the Bearer key.** `X-API-Key`, cookies and other schemes are not accepted, so an operator session can never
open an agent route and an agent key can never open an operator route.

**D3. One place refuses a role.** `require_publisher_principal` raises 403 `mintkey:role_forbidden` for a role other than
`publisher` after `record_denied_operation` wrote `agent.operation.denied` from a session of its own, so the event survives
the raised error; it binds the principal's tenant (never the platform view) before `audit_emit`. The `operation` it records on a REST route is the literal `"<METHOD> <path>"` of the request, for
example `POST /v1/agent/services`, taken from `request.method` and `request.url.path` (at most 256 characters). The MCP
server records the tool name instead (`agent-service-tools`). When the audit write fails the refusal is still answered
(403) and the failure is logged: a refusal never depends on its record.

**D4. Added: the event's `role` is the normalized role**, so an unknown stored value is recorded as `consumer`.

**D5. Added: egress edge cases.** A trailing dot is removed before the checks; a `*.suffix` entry never matches the bare
suffix; an unparsable address is not public.

**D6. Added: the egress rule is stricter than the proxy's.** `address_is_public` accepts global unicast addresses only; the
proxy's connect-time rule (`proxy-public-egress`) may accept a wider set. The difference is in the safe direction.

## Interfaces

Module signatures are in the requirements of the two specs, not repeated here. Given to `agent-service-routes`,
`agent-service-tools` and the later agent changes: `admin_api.auth.agent_principal` (`AgentPrincipal`, `AgentApiError`,
`agent_api_error_handler`, `require_agent_principal`, `require_publisher_principal`, `record_denied_operation`),
`admin_api.api.internal.check_agent_key`, `mintkey_models.egress` (`TargetNotAllowed`, `egress_deny_names`,
`address_is_public`, `resolve_host`, `check_agent_target_url`) and the audit type `agent.operation.denied`. Error bodies:
401 `{"code": "mintkey:auth_required"}`, the invalid-key and expired-key bodies of `validate-agent-key`, 503
`mintkey:verify_unavailable`, 403 `mintkey:role_forbidden` `{role, required_role, hint}`.

## Failure cases

- No usable credential: 401 before any database work. A rejected key: the status and body `validate-agent-key` answers. A
  database failure while checking: 503 `mintkey:verify_unavailable`, the dedicated session closed.
- A consumer on a publisher dependency: 403 and one event; the audit write failing: 403 and no event.
- A name that fails to resolve, resolves to nothing or to one non-public address: `unresolvable` or `non_public_address`.

## Relation to the other changes

`agent-service-routes` registers `agent_api_error_handler`, mounts routes behind these dependencies and calls
`check_agent_target_url`. `agent-service-tools` reads `role` from the key check through the MCP agent context.

## Follow-ups

Out of scope here: a fetch-time re-check of an agent-owned `openapi_url` by MCP `get_openapi`, and a configurable quota of
services per agent.
