# Design: grant-expiry

## Context

Facts at the base (staging `2c4c814`); the requirements name symbols, the anchors are for review only.

- `permission_grants` (`CL/006`, `CL/011`) has `created_by` NOT NULL and no expiry; only the route keeps one row per
  (agent, service, action).
- `grant_permission` (`ADM/api/permissions.py:537`): steps 6 to 10 select an existing row (equal constraints: 200,
  other: 409 `permission_constraints_conflict`), insert with `created_by = body.granted_by or agent_uuid` (line 658),
  upsert the budget counter, emit `agent.permission.granted` with `actor_id=None`. `revoke_permission` (line 736)
  deletes without reading and emits `agent.permission.revoked` and a NOTIFY on `mintkey:agent` (`{event, tenant_id,
  agent_id, permission_id}`) whether or not a row existed.
- The operator id comes from `get_session_context` (`ADM/auth/sessions.py:156`), None without a session cookie.
- Readers of `permission_grants`: `request_token` (`MCP/tools/request_token.py:186`, `LIMIT 1`; `"ttl_seconds": 600` at
  line 298), the discovery statements (`MCP/tools/discovery.py:401, 485, 605`), `api_keys.py:317`, the grant counts and
  access filter of `agents.py` (lines 400-508), the budget routes and the proxy's `GrantBudgetSQL`.
- `tests/unit/admin_api/test_permissions.py` patches `admin_api.api.permissions.audit_emit` and `notify_change`; its
  idempotency test uses a `MagicMock` row. Existing MCP tests feed grant rows without `expires_at`.
- The ORM mirror ignores `addColumn` columns (`tests/acceptance/test_sqlalchemy_mirror.py`), so `mintkey_models/db.py`
  is unchanged; the Core table `ADM/db/tables.py` gains the columns.

## Decisions

**D1. Columns.** `expires_at` TIMESTAMPTZ NULL (null = no expiry; only operators may leave it null), `grantor_type`
TEXT NOT NULL DEFAULT `'operator'` with a CHECK, `grantor_id` UUID NULL. Existing rows keep `operator` and a null id:
`created_by` holds a body value or the grantee's id, so nothing is back-filled from it.

**D2. The grantor is the caller.** The operator route takes it from `get_session_context` (type `operator`, id the
operator, or None with no context); an agent route takes it from the agent key (type `agent`, the agent id).
`granted_by` in a body is accepted and ignored. `created_by` stays NOT NULL: it is the grantor id, or the grantee's
id when the grantor id is unknown (the value the code used before for a missing `granted_by`).

**D3. Expired means absent, decided at read time.** No job removes a row. Each reader treats a grant as absent when
`expires_at` is not null and not after "now". The clock: `request_token` and the operator responses compare in
Python with `datetime.now(timezone.utc)`; the list and lookup statements (discovery, `agents.py`, `api_keys.py`) put
`(pg.expires_at IS NULL OR pg.expires_at > now())` in the SQL, so the database clock decides. A stored
value of the wrong type reads as its default (`expires_at` None, `grantor_type` `operator`, `grantor_id` None, `created_at`
None), which keeps rows of tests and of older code working.

**D4. Token lifetime.** `grant_ttl_seconds(expires_at, now)`: no expiry gives 600; otherwise
`floor(seconds until expires_at)` capped at 600, and below 5 the result is None and no token is issued. An expired
grant and one with under 5 s left answer the same: 403, reason `grant_expired`. The grant check runs before the rate
limit and time-window checks, so an expired grant never counts against a limit.

**D5. Agent grants are capped.** `MINTKEY_AGENT_GRANT_MAX_TTL` is a decimal number of seconds. Unset, empty, not a
decimal integer, or below 1: 604800 (7 days). Above 7776000 (90 days): 7776000. An agent grantor must give an
`expires_at` after now and not after now plus that cap; an operator may give none or any later time. The cap is
checked inside `write_grant`, so no caller can skip it.

**D6. One write path, audit stays with the caller.** `write_grant` and `delete_grant` run the statements; the caller
emits the audit event and the NOTIFY with the payload builders (the operator route's tests patch its own emitters).

**D7. A live grant with another expiry is a conflict; an expired one is replaced.** The same (agent, service, action) with
equal constraints and expiry is idempotent (200 for the operator route); a live grant with other constraints or another
expiry is a conflict (409). An expired grant is absent (D3), so `write_grant` deletes it and inserts the new one in the same
call, with no event for the deletion: an expired grant is renewed by granting again, a live one by revoking it first (the
revoke is audited and reaches the proxy). There is no expiry PATCH.

**D8. Revoking a missing grant is nothing to do.** `delete_grant` returns None when no row matches; the operator route
still answers 204 but writes no audit event and sends no NOTIFY (before this change it did both). The revoke events now
name the service, the action and the grantor, and the NOTIFY adds `service_id` and `revoked_at` to its existing keys.
`revoked_at` is pinned as an ISO-8601 UTC timestamp with an offset (`2026-11-25T10:00:00+00:00`), the format
`datetime.isoformat()` gives, so `proxy-grant-revocation` can parse it with one rule.

**D9. Out of scope.** Service API keys already issued are separate credentials (creating one from an expired grant is
refused); the budget routes and the proxy's budget read are reached only after a token was issued.

## Interfaces

The module signatures, record fields, payload keys and wire shapes are in the requirements of `specs/grant-expiry/spec.md`
(not repeated here). Token denial: 403 `{"code": "mintkey:not_authorized", "reason_code": "grant_expired", agent_id,
service_id, action, "hint"}` plus a `token.denied` event with the same `reason_code`.

## Failure cases

- An invalid `expires_at` (past, no offset; for an agent also missing or beyond the cap): 422 or `GrantExpiryError`,
  no row, no event. A malformed `MINTKEY_AGENT_GRANT_MAX_TTL`: the default. Another expiry on an existing grant: 409,
  the stored grant unchanged. A row with no or a non-datetime `expires_at`: no expiry. Email grants: unchanged.

## Relation to the other changes

Assumes `tenant-session-routes` is merged: the grant routes, the lists and `get_permission` all carry the tenant
session. `agent-granted-access` and `agent-access-requests` call `write_grant`, `delete_grant`, the payload builders and
`grant_wire_fields` with `Grantor("agent", <agent uuid>)` or `Grantor("operator", <operator uuid>)`, and rely on
`check_grant_expiry` for the cap. `admin-ui-agent-governance` reads the four response fields and the
`grantor_agent_id` filter. `revoke_permission` is also on the path of the proxy's revocation change.

## Follow-ups

Out of scope here: service API keys created from a grant keep their own lifetime (a later change can end them at the
grant's expiry), and `mintkey_describe_service` does not show a grant's `expires_at` (a later change can add it with
`your_constraints` in `tools.yaml`).
