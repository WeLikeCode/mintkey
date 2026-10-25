# Revocation reaches its subscribers, and the egress proxy refuses revoked tokens

## Why

A credential broker's revocation is its fastest control: an operator revokes an agent or one token, and the next
proxied call with that token must fail. ADR-0006's verification flow requires it (step 7: the `jti` is not in the
local revocation set; step 8: the `sub` is not in the revoked-agent set). Today the egress proxy builds both sets,
and the change subscriber (`apps/proxy-plugin/internal/changes/subscriber.go`) fills them from
`NOTIFY "mintkey:agent"`, but the request handler never consults them: a revoked token keeps working until its
`exp` plus the 30 s clock skew.

Three more gaps sit on the same path and would keep revocation from taking effect even once the handler checks:

1. **The agent id has two forms.** The JWT `sub` is the agent's database UUID (the MCP server passes
   `agent_ctx["agent_id"]`, which admin-api's `validate-agent-key` returns as `str(row.id)`), while admin-api's
   `agent.revoked` notification carries the wire form `agent_<26 Crockford characters>` that the operator used in the
   URL. An exact string comparison never matches.
2. **The event key differs.** Every admin-api publisher except the budget ones sends the event name under the key
   `event` (for example `{"event": "agent.revoked", ...}` from `revoke_agent` and `delete_agent` in
   `apps/admin-api/src/admin_api/api/agents.py`), while the contract
   (`docs/architecture/contracts/events/change-event.schema.json`) and every subscriber that reads the name (the
   proxy, the MCP server, the vault adapter) use `event_type`. No such notification is acted on today.
3. **The token-id set fills up.** `JTIRevocationSet.Add` ignores new ids once the set holds 10,000 entries, and nothing
   calls `Evict`, so after 10,000 revocations no further token revocation is recorded.

## What Changes

- The proxy handler owns the two revocation sets and refuses, with `401 unauthorized: token revoked`, a JWT whose `jti`
  or whose `sub` is revoked. The check runs right after the claims are read, before any other gate and before the
  vault credential fetch. The change subscriber is built from the handler's sets.
- The agent revocation set treats the wire form and the UUID form of an agent id as one id.
- admin-api's `notify_change` (`apps/admin-api/src/admin_api/changes/publisher.py`), which every admin-api publisher
  calls, adds `event_type` equal to `event` when a payload has `event` and no `event_type`. `event` stays for
  compatibility; payloads that already carry `event_type` are sent unchanged.
- The proxy's change subscriber reads the event type from `event_type` and, when that key is absent, from `event`, so
  it also works with an admin-api deployed before this change.
- A revoked token id is kept for the longest token lifetime (3600 s maximum TTL plus 30 s skew) and then evicted by a
  loop the proxy runs every minute.

## Capabilities

### New Capabilities
- `proxy-token-revocation`: how the egress proxy learns of revoked agents and tokens and refuses them.

## Impact

- Changed: `apps/proxy-plugin/cmd/proxy-plugin/main.go` (`proxyHandler`, `newProxyHandler`, `ServeHTTP`, `main`),
  `apps/proxy-plugin/internal/revocation/agent_set.go`, `apps/proxy-plugin/internal/revocation/jti_set.go`,
  `apps/proxy-plugin/internal/changes/subscriber.go` (`HandleNotification`).
- Changed: `apps/admin-api/src/admin_api/changes/publisher.py` (`notify_change`; its callers are listed in design.md).
- New module: `apps/proxy-plugin/internal/wireid/wireid.go` (wire id to UUID; also used by later proxy changes).
- New tests: `apps/proxy-plugin/cmd/proxy-plugin/revocation_enforced_test.go`,
  `apps/proxy-plugin/internal/changes/subscriber_event_key_test.go`,
  `apps/proxy-plugin/internal/revocation/agent_set_id_forms_test.go`,
  `apps/proxy-plugin/internal/revocation/jti_eviction_test.go`, `tests/unit/admin_api/test_notify_event_type.py`.
- Callers: a token revoked through the change channel is refused within the channel's delivery time. Unrevoked
  tokens, the classical service API key path and the read-only gate behave as before. Subscribers that read
  `event_type` start acting on admin-api's notifications (the vault adapter on `credential.rotated`); subscribers
  that read `event` or only `tenant_id` see the same payload plus one key.
- Operators: no migration. Revocation needs the proxy's `DATABASE_URL` (the subscriber listens on that Postgres);
  without it the sets stay empty and tokens end at expiry, as today.
- Out of scope: a Mintkey endpoint that publishes `token.revoked` (no component publishes it today; an operator or an
  embedding application can `NOTIFY` it), and revocation in the SSH and email proxies (the SSH proxy's change client
  does not `LISTEN` yet; see design.md, Open questions).

## Issue Intake (remediation gate)

1. **Problem statement**: the egress proxy forwards requests made with revoked tokens until they expire.
2. **User-visible symptom**: after an operator revokes an agent, its calls through the proxy still succeed for up to
   the token TTL (10 minutes by default, 60 at most) plus 30 s.
3. **Expected behavior**: the next call with a revoked token or a token of a revoked agent answers 401 and never reaches
   the vault or the upstream.
4. **Evidence**: `ServeHTTP` in `apps/proxy-plugin/cmd/proxy-plugin/main.go` has no call to `Contains`; the sets'
   only uses are their construction in `main`. The id-form and event-key differences are cited under Why.
5. **Scope**: the proxy files and admin-api's publisher listed under Impact.
6. **Out of scope**: as listed under Impact.
7. **Risk level**: security (fail closed on a revoked token); availability is unchanged for unrevoked tokens.
8. **Verification target**: the gate's Go suite for `apps/proxy-plugin` (the four new Go test files) and the
   admin-api unit suite (`tests/unit/admin_api/test_notify_event_type.py`).
9. **Owner decisions needed**: none; the decisions are recorded in design.md.
