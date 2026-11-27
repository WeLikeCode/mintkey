# Design: proxy-grant-revocation

## Context

`Subscriber.HandleNotification` (`apps/proxy-plugin/internal/changes/subscriber.go`) decodes the event type from
`event_type` (or `event`) and acts on `agent.revoked`, `token.revoked`, `api_key.revoked` and `budget.config_updated`; a type
it has no case for does nothing, which keeps newer publishers compatible. `proxyHandler.ServeHTTP` verifies the JWT, reads `aud`, `tnt`, `sub`, runs the revoked-token and
revoked-agent check (the `proxy-token-revocation` capability), then the scope claims and the other gates. The sets are
created in `newProxyHandler` and handed to the subscriber by `changesSubscriber`; the agent set compares ids through
`wireid.Canonical` (`internal/wireid`).

`grant-expiry` changes `revoke_permission` (and the new grant write path) to publish through `notify_change` the payload
`{event: "agent.permission.revoked", tenant_id, agent_id, permission_id, service_id, revoked_at}` on `mintkey:agent`;
`notify_change` adds `event_type`. The ids are in wire form, while the broker signs the agent's database UUID as `sub` and
the service id as `aud` in whichever form the MCP server asked for. The broker's `Issue` signs `iat` as Unix seconds next to
`exp`; the proxy's verifier reads claims into a `map[string]any`, so `iat` is a `float64`. The proxy's retention of revoked
token ids is `revocation.JTIRetention` (3630 s: the broker's 3600 s maximum token lifetime plus the proxy's 30 s skew).

## Interfaces

Taken from `grant-expiry`: the NOTIFY payload above (`tenant_id` UUID text, wire ids, `revoked_at` the ISO-8601 UTC timestamp
with an offset that `grant-expiry` pins, for example `2026-11-25T10:00:00+00:00`, with microseconds as
`2026-11-25T10:00:00.123456+00:00` when it has them; `time.RFC3339Nano` parses both). Given to later changes: none; the set and the option are internal to the
proxy. The `GrantRevocationSet`, `Add`, `Refuses` and `WithGrantRevocations` signatures are in the delta spec.

```go
// changes.HandleNotification, new case:
case "agent.permission.revoked":
	// both ids are required: otherwise return an error naming the missing field and add nothing. This check runs before the
	// nil check below, so an event without an id is an error whatever the subscriber holds; an event with both ids and no set
	// returns nil.
	// revoked_at: time.Parse(time.RFC3339Nano, v) (fractional seconds are accepted); absent or unparsable -> receipt time;
	// later than receipt + 30 s -> receipt time (a clock that runs ahead cannot refuse tokens issued after the receipt).
	s.grants.Add(evt.AgentID, evt.ServiceID, revokedAt) // s.grants nil: nothing
// ServeHTTP, directly after the revoked-token/agent check:
iat, hasIAT := iatClaim(claims["iat"]) // float64, finite and > 0 -> int64(math.Floor(v)); anything else: false
if agentID != "" && h.revokedGrants.Refuses(agentID, serviceID, iat, hasIAT) { /* same 401 as the revoked token */ }
```

## Decisions

**D1. The pair, not the action.** The event names the agent and the service and no action, so every token of the pair
issued before the revocation is refused, including one issued under another grant of the same agent and service (for
example the `write` token when the `read` grant is revoked). The agent asks for a new token, which the broker issues only
for grants that still exist. Per-action revocation would need the action in the payload.

**D2. Whole seconds, conservative on ties.** `iat` has second resolution and `revoked_at` has more, so a token issued
within the revocation second cannot be told from one issued just before it. The rule `iat <= floor(revoked_at)` refuses
both. A new grant made in the same second as the revocation therefore yields tokens that work from the next second on; the
agent retries. The alternative (`iat < floor(revoked_at)`) would let a token issued under the revoked grant live on.

**D3. A token without a usable `iat` is refused while an entry for its pair exists.** Every broker token has `iat`, so a
token without one is not the broker's normal output; when the pair has a revocation, the proxy cannot show the token
postdates it. Tokens of pairs without an entry are not asked for `iat`.

**D4. Retention keyed on `revoked_at`.** An entry stops counting at `revoked_at + 3630 s` (every token issued before it has
expired by then), so it is not added when that moment has passed, and `Refuses` ignores an expired entry even before it is
removed. A `revoked_at` later than the receipt time plus 30 s is replaced by the receipt time, so a wrong clock cannot
keep an entry alive or revoke tokens issued after the event arrived. Removal is lazy: `Add` deletes expired entries, and
the set holds one small entry per revoked pair within the last hour. There is no background loop.

**D5. Unusable events fail visibly.** An event without both ids returns an error from `HandleNotification`; `Start` ignores
errors as it does for malformed payloads, so nothing is added. The proxy cannot revoke what the event does not name.

**D6. Reuse of the handler's sets.** The handler owns the set (`revokedGrants`) and `changesSubscriber` passes it with the
existing sets, as `proxy-token-revocation` does; `NewSubscriber`'s signature is unchanged and the option keeps its four-argument
callers (the existing subscriber tests) working.

**D7. The tenant is not compared.** The event carries `tenant_id` for the audit trail and for other consumers; the proxy
matches on (agent, service) only, because both ids are globally unique UUIDs, and a token of a pair in another tenant cannot
exist.

## Relation to the other changes

Assumes `grant-expiry` (the payload and its `revoked_at` format). It follows `proxy-public-egress`: both change
`newProxyHandler` and `ServeHTTP` in `apps/proxy-plugin/cmd/proxy-plugin/main.go`, and this change's tests use the
handler as that change leaves it.

## Risks and edge cases

- The set is in memory: a proxy that starts after a revocation does not learn of it, as for the revoked-agent and token sets
  today. The tokens concerned expire within an hour.
- The check needs the proxy's `DATABASE_URL` for the subscriber, like the other revocation events.
- An agent with several grants on one service sees all its earlier tokens for the service refused after one revocation (D1).
- Clock skew: `revoked_at` comes from admin-api's clock and `iat` from the broker's. The rule compares them as they are, so
  with the broker's clock `s` seconds behind admin-api's, a token issued just after a revocation can be refused for up to `s`
  seconds (the agent asks again), and with it `s` seconds ahead, a token issued just before the revocation can carry an `iat`
  later than `revoked_at` and pass. The services share one host or one NTP-synchronised cluster, and no tolerance is added
  (a tolerance would refuse fresh tokens); this is a documented risk of the design, not a tested behaviour.
- A token with `sub` not in either id form compares by exact string, as the agent set does.

## Follow-ups

- Revoke per action when the event carries it.
- Revocation in the SSH and email proxies.
- API keys that outlive their grant (classical service keys resolved through the broker) are outside this change.
