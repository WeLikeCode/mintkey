# Design: agent-service-routes

## Context

Facts at the base (staging `2c4c814`); the requirements name symbols, the anchors are for review only.

- `create_service` (`ADM/api/services.py:471`: slug `name.lower().replace(" ", "-")`, `UNIQUE (tenant_id, slug)`, id from
  `_new_svc_id`); `create_credential` (`ADM/api/credentials.py:629-690`) calls `vault.put_credential` (target = the service's
  `base_url`; the gRPC call commits on its own), supersedes the active `credentials` rows, inserts one, sets
  `services.current_key_version`. `update_service` edits `vault.credentials` with SQL (line 1473). No vault call deletes a
  credential.
- `CsrfMiddleware` refuses a cookie-less POST outside `csrf_exempt` paths (`ADM/main.py:124`). The global 422 handler
  answers with `str(exc)`, which carries the input.
- `tests/acceptance/test_openapi_parity.py` snapshots `module -> prefix` for every `router` that `main.py` imports
  (`from admin_api.api.<module> import router`), reading the first `APIRouter(... prefix=...)` of the module.
- Wire ids (`admin_api.utils.wire_ids`): `svc_` plus 26 Crockford characters, or 32 hex characters, decoded by
  `wire_to_db_uuid`.

## Relied on (given by the named change; not redefined here)

- `agent-principal-and-egress`: `AgentPrincipal(tenant_id, agent_id, role)`, `AgentApiError(status_code, body, headers)`,
  `agent_api_error_handler`, `require_agent_principal`, `require_publisher_principal` (403 `mintkey:role_forbidden` and the
  event `agent.operation.denied` for a consumer), and `mintkey_models.egress` (`check_agent_target_url(url)`, which raises
  `TargetNotAllowed` with `.reason`).
- `agent-roles-and-ownership`: the columns `services.owner_agent_id` and `services.created_by_agent_id` (UUID, null =
  operator-owned) and `mintkey_models.roles`. Services carry no owner column before it.
- `proxy-public-egress`: `VaultAdapterClient.put_credential(..., egress_scope: str = "")` and the vault column
  `egress_scope` (`any` or `public`; a credential stored with `public` is connect-checked by the proxy).
- Delivered before them: `tenant-session-routes`, `grant-expiry`, `proxy-stored-target`.

## Decisions

**D1. Agent surface.** All routes hang under one parent router (`admin_api/api/agent.py`, the only module of the family
`main.py` imports, so the parity snapshot changes once); each area is a sub-router whose authentication is
`require_publisher_principal`. The tenant comes from the principal.

**D2. A service reference.** `service_ref` is an id when it starts with `svc_` and a slug otherwise. An id that does not
decode answers 404 `mintkey:not_found`. A publisher cannot create a service whose slug starts with `svc_` (422), so a
reference is never both; an operator-made service with such a slug is reachable by its id only.

**D3. Credentials are write-only and bound to their target.** An update that changes `base_url` or `auth_scheme` deletes the
`vault.credentials` and `credentials` rows in the request's transaction (the vault holds the target with the credential;
there is no vault delete call, and `update_service` already edits that table with SQL). Agent services allow `bearer_token`,
`api_key_header`, `api_key_query` and `basic_auth` (opaque values); a PATCH may only choose among these four, and a service
that has another scheme (one an operator made and transferred) cannot receive an agent credential until its scheme is
changed to one of the four. The header and query-parameter names are set with the value; no update field changes them.
The credential route parses its own body, because the global 422 handler carries the input.

**D4. Egress.** The URL check applies at create and, when the field changes, at update; a failed resolution refuses. The
credential route passes `egress_scope="public"` to `put_credential`, so a credential of an agent-owned service is never
stored with the scope `any`; no SQL touches the column.

**D5. Ownership and audit.** A created service has `owner_agent_id` and `created_by_agent_id` set to the caller. Another
owner or none gives 403 `mintkey:not_owner`; another tenant's service is not found. Every route writes `actor_type`
`agent` and `actor_id` the agent. The admin UI's audit filter list is `admin-ui-agent-governance`'s.

**D6. Added: validation.** Name pattern `^[A-Za-z0-9][A-Za-z0-9 ._-]{0,62}$`; update fields are set-only (no rename, no
clearing, no `status`); `extra="forbid"` on every body.

**D7. Added: one writer at a time per service.** The credential route and the update route both select the service row
`FOR UPDATE` as their first service statement (`require_owned_service(..., for_update=True)`). A credential write and a
target change on one service therefore run one after the other: the vault write of a credential happens while the row is
locked, so it always carries the target the metadata transaction commits with, and a target change that follows clears it.
Create needs no lock (a new row).

**D8. Added: audit schema.** `owner_agent_id` is an optional property of `ev_service_registered` (operator-made events have
none, so it is not in `required`); the `fields_changed` enum of `ev_service_updated` keeps its six values (`display_name`,
`description`, `base_url`, `actions`, `openapi_url`, `status`) and gains `auth_scheme`.

**D9. Added: the snapshot edit is authorised.** `tests/acceptance/openapi_snapshot.json` is edited in task 5.1 and the
reviewed task text says exactly which entry: `"agent": "/v1/agent"`, inserted in key order, nothing else changed. The end
state of that task is `tests/acceptance/test_openapi_parity.py` passing. If L4 holds the file as a data fixture and raises a
question, the expected answer is: allow exactly this entry.

## Interfaces

Given to `agent-service-tools`, `agent-granted-access` and `agent-access-requests`:

- `admin_api/api/agent.py`: `router = APIRouter(prefix="/v1/agent")`, extended by later changes with `include_router`.
- `admin_api.services.agent_publishing`: `parse_service_ref`, `require_owned_service`, `service_view` (signatures in the
  spec).
- Routes: `POST` and `GET /v1/agent/services`, `PATCH /v1/agent/services/{service_ref}`, `PUT
  /v1/agent/services/{service_ref}/credential`; bodies and answers are in the requirements.
- Error bodies carry `code`: 400 `mintkey:target_not_allowed` `{field, reason, hint}`; 401 and 503 from the principal; 403
  `mintkey:role_forbidden`, `mintkey:not_owner`; 404 `mintkey:not_found`; 409 `mintkey:slug_conflict`; 422
  `validation_failed` or `mintkey:validation_failed`; 502 `mintkey:vault_unavailable`.

## Failure cases

- An egress refusal: 400, nothing written; a failed DNS lookup refuses until the name resolves.
- Vault unreachable at the credential write: 502, no metadata row, no event. A failure after `put_credential` returned
  leaves a vault row with scope `public` and no metadata row: the next credential write supersedes it.
- An update that changes nothing: 200, no UPDATE, no event, `credential_cleared` false; a changed target on a service with
  no credential: no clear event. A consumer key: 403 and an event (from the principal); a bad key: 401.
- A race between a credential write and a target change: serialised by the row lock (D7); whichever commits second sees
  the first.

## Relation to the other changes

`agent-service-tools` calls these routes with the caller's key. `agent-granted-access` and `agent-access-requests` attach
sub-routers to `admin_api/api/agent.py` and use `AgentApiError` and `require_owned_service`. `admin-ui-agent-governance`
lists the two credential event names.

## Follow-ups

Out of scope here: a fetch-time re-check of an agent-owned `openapi_url` by MCP `get_openapi`, and a configurable quota of
services per agent.
