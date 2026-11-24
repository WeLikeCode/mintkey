# Design: agent-service-publishing

## Context

Facts at the base (staging `2c4c814`); the requirements name symbols, the anchors are for review only.

- Agent keys are checked by `POST /v1/internal/validate-agent-key` (`ADM/api/internal.py:135`), which first sets
  `app.platform_admin_view` to `on` for its transaction (line 159); `set_tenant_context` never turns it off. Its test
  patches `internal._verify_argon2` and counts two `execute` calls.
- `create_service` (`ADM/api/services.py:471`: slug `name.lower().replace(" ", "-")`, `UNIQUE (tenant_id, slug)`);
  `create_credential` (`ADM/api/credentials.py:629-690`) calls `vault.put_credential` (target = the service's `base_url`; the
  gRPC call commits on its own), supersedes the active `credentials` rows, inserts one, sets `services.current_key_version`.
  `update_service` edits `vault.credentials` with SQL (line 1473). No vault call deletes a credential.
- `CsrfMiddleware` refuses a cookie-less POST outside `csrf_exempt` paths (`ADM/main.py:124`). The existing
  `resolve_hostname_is_private` (`ADM/services/credential_service.py:50`) is the operator-side check: it takes no deny list and does not refuse a name that fails to resolve; agents use `mintkey_models.egress`, which does both.
- MCP: `TOOLS` (`MCP/tools/jsonrpc.py:96`), `_handle_tools_list` (456), `_handle_tools_call` (461), `_dispatch_tool` (511);
  existing tests build contexts without `role` and expect 10 tools. `tests/acceptance/test_openapi_parity.py` snapshots
  `module -> prefix` for every router `main.py` imports.

## Decisions

**D1. Agent surface.** Agents act through the MCP server with their key; each operation is a tool that forwards the key as
`Authorization: Bearer` to a route under `/v1/agent/`. All of them hang under one parent router (`admin_api/api/agent.py`,
the only module of the family `main.py` imports, so the parity snapshot changes once); each area is a sub-router whose only
authentication is `require_agent_principal` or `require_publisher_principal`. The tenant comes from the principal.

**D2. The key check is shared and runs outside the route's transaction.** It moves to `internal.check_agent_key`, which
`validate_agent_key` calls without a change of behaviour. `require_agent_principal` runs it in its own session from
`AsyncSessionLocal`, closed before the route's session opens, so `platform_admin_view` is never on in a route's transaction;
each route calls `set_tenant_context(session, principal.tenant_id)` and pins its statements to the tenant.

**D3. Roles.** The key check reads `agents.role` on every request, so a change applies at once; the MCP server reads it from
its agent context (default `consumer`). The registry (`agent-tool-roles`) already names the tools of the later changes; a name
in neither set is refused for every role. No agent tool deletes a service, transfers ownership, sets a role, or reads or
tests a credential.

**D4. One place refuses.** `enforce_tool_role` refuses a tool for a role and writes `agent.operation.denied`. REST: 403; JSON-RPC:
the error `-32003` (a refused call, not a failed tool). admin-api repeats the check for a consumer key that reaches a
publisher route, writing the event from a separate session so it survives the raised error.

**D5. Credentials.** Write-only, bound to their target: an update that changes `base_url` or `auth_scheme` deletes the
`vault.credentials` and `credentials` rows in the request's transaction (the vault holds the target with the credential;
there is no vault delete call, and `update_service` already edits that table with SQL). Agent services allow `bearer_token`,
`api_key_header`, `api_key_query` and `basic_auth` (opaque values; structured schemes keep their operator validators; `ssh_*`
needs a non-`https` target). The credential's scheme is the service's. The header and query-parameter names are set with the
value; no update field changes them. The credential route parses its own body, because the global 422 handler answers with
`str(exc)`, which carries the input.

**D6. Egress.** The URL check applies at create and, when the field changes, at update; a failed resolution refuses. The route
passes `egress_scope="public"` to `VaultAdapterClient.put_credential` (the put-time parameter of `proxy-public-egress`), so a
credential of an agent-owned service is never stored with the scope `any`; no SQL touches the column. The store-time rule
here (`address_is_public`, global unicast addresses only) is stricter than the proxy's connect-time rule, in the safe
direction (`proxy-public-egress` design D4).

**D7. Ownership and audit.** A created service has `owner_agent_id` and `created_by_agent_id` set to the caller. Another owner
or none gives 403 `mintkey:not_owner`; another tenant's service is not found. Every route writes `actor_type` `agent` and
`actor_id` the agent. The admin UI's audit filter list is `admin-ui-agent-governance`'s.

**D8. Added here.** Name pattern `^[A-Za-z0-9][A-Za-z0-9 ._-]{0,62}$`; update fields are set-only (no rename, no clearing, no
`status`); `extra="forbid"` on every body; a transport or 5xx failure of admin-api reaches the agent as 502
`mintkey:admin_api_unavailable`; the tools stay out of the unauthenticated landing listing.

## Interfaces

Module signatures, REST bodies and tool schemas are in the requirements of the three specs (`agent-service-publishing`,
`agent-egress-policy`, `agent-tool-roles`), not repeated here. Error bodies of the `/v1/agent` routes carry a `code`: 400 `mintkey:target_not_allowed` `{field, reason, hint}`;
401 `mintkey:auth_required`, the invalid-key body, 503 `mintkey:verify_unavailable`; 403 `mintkey:role_forbidden` `{role,
required_role, hint}`, `mintkey:not_owner`; 404 `mintkey:not_found`; 409 `mintkey:slug_conflict`; 422 `validation_failed` or
`mintkey:validation_failed`; 502 `mintkey:vault_unavailable`.

## Failure cases

- An egress refusal: 400, nothing written; a failed DNS lookup refuses until the name resolves.
- Vault unreachable at `set_credential`: 502, no metadata row, no event. A failure after `put_credential` returned leaves a vault row with scope `public` and no metadata row: the next
  `set_credential` supersedes it.
- An update that changes nothing: 200, no UPDATE, no event, `credential_cleared` false; a changed target on a service with no
  credential: no clear event. A consumer key on a publisher route or tool: 403 and an event; a bad key: 401.
- admin-api unreachable from the MCP server: 502 `mintkey:admin_api_unavailable`.

## Relation to the other changes

Assumes `agent-roles-and-ownership` (`agents.role`, the owner columns, `mintkey_models.roles`, `role` in the key check) and
`proxy-public-egress` (`vault.credentials.egress_scope` and the `egress_scope` parameter of `put_credential`). `agent-granted-access` and `agent-access-requests` attach
sub-routers to `admin_api/api/agent.py` (dependency `require_agent_principal` or `require_publisher_principal`) and use
`AgentApiError`, `require_owned_service`, `enforce_tool_role` and the role sets without editing `roles.py`.

## Follow-ups

Out of scope here: a fetch-time re-check of an agent-owned `openapi_url` by MCP `get_openapi`, and a configurable quota of
services per agent.
