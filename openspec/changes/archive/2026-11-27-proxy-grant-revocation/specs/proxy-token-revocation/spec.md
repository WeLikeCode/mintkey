## ADDED Requirements

### Requirement: A revoked grant's earlier tokens stop working at the proxy
The proxy SHALL handle the change event `agent.permission.revoked`, published by admin-api on `mintkey:agent` with the
payload `{event, event_type, tenant_id, agent_id, permission_id, service_id, revoked_at}` (`tenant_id` UUID text; ids in wire form `agent_...`
and `svc_...`; `revoked_at` an ISO-8601 UTC timestamp with an offset, as `2026-11-25T10:00:00+00:00`, parsed as RFC 3339), by recording that tokens of that agent for that service issued at or
before `revoked_at` are refused for 3630 seconds from `revoked_at`. `ServeHTTP` SHALL answer 401 with the body
`unauthorized: token revoked`, count `IncProxyDenied(serviceID, "revoked")` and contact neither the vault nor the upstream
for a JWT whose `sub` and `aud` match a recorded entry and whose `iat` is at or before the entry's `revoked_at`
(compared in whole seconds, `iat <= floor(revoked_at)`) or has no usable `iat` (missing, not a number, or a number that is
not finite and greater than zero). The check SHALL run directly after the
revoked-token and revoked-agent check. Agent and service ids SHALL match in every form `wireid.Canonical` treats as one
id. The event's `tenant_id` is carried and not compared with the token's `tnt` claim: the ids are globally unique, so the
pair alone decides. The new type in `apps/proxy-plugin/internal/revocation/grant_set.go` SHALL be:

```go
type GrantRevocationSet struct{ /* ... */ }
func NewGrantRevocationSet() *GrantRevocationSet
// Add records the revocation for (agentID, serviceID), each through wireid.Canonical with the prefixes "agent_" and
// "svc_". A later revokedAt replaces an earlier one, and an earlier one added afterwards changes nothing; an entry whose revokedAt is more than JTIRetention in the past is not
// added; every call removes the entries that have expired.
func (s *GrantRevocationSet) Add(agentID, serviceID string, revokedAt time.Time)
// Refuses reports whether a token of the pair with this iat (hasIAT false: no usable iat) must be refused now.
func (s *GrantRevocationSet) Refuses(agentID, serviceID string, iat int64, hasIAT bool) bool
func (s *GrantRevocationSet) Len() int
```

The subscriber SHALL be given the set by `func WithGrantRevocations(s *revocation.GrantRevocationSet) SubscriberOption`
(`apps/proxy-plugin/internal/changes/subscriber.go`), and `proxyHandler.changesSubscriber` SHALL always pass the handler's
own `revokedGrants` set (never nil after `newProxyHandler`).

#### Scenario: tokens issued before the revocation are refused, later ones and other pairs are not
- **WHEN** the handler's change subscriber receives `agent.permission.revoked` for the agent
  `agent_3C7JAGMBGR9EMRS2AVGXDHQXDX`, the service `svc_5ANANANANANANANANANANANANA` and a `revoked_at` 60 seconds ago (R is
  its Unix second), and requests carry valid tokens with `sub` `6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd`, `aud`
  `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` and `iat` equal to R-60, R-1, R and R+1; a token of the same agent for the service
  `bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb` with `iat` R-1; and a token of the agent `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`
  for the revoked service with `iat` R-1; the event's `tenant_id` is `11111111-2222-3333-4444-555555555555` and the tokens'
  `tnt` is `tenant-test-uuid-0001`
- **THEN** the first three answer 401 with a body containing `token revoked` (not the 502 of the unreachable test vault, so
  neither the vault nor an upstream was contacted), and the token with `iat` R+1 and the two tokens of the other pairs reach
  the credential fetch (502); the handler's metrics text (`h.metrics.WriteMetricsTo`) holds the line
  `mintkey_proxy_denied_total{service="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",reason="revoked"} 3`

#### Scenario: a token without a usable iat is refused while an entry exists
- **WHEN** the same event has been applied and tokens of the pair have no `iat` claim, `"iat": "123"` (a string), `"iat": 0`
  and `"iat": -5`
- **THEN** all four answer 401 with a body containing `token revoked`; and with no event applied, a token without `iat` reaches
  the credential fetch

#### Scenario: an old revocation adds nothing and a future one counts as received now
- **WHEN** one event has a `revoked_at` 3700 seconds ago and the pair's token has `iat` 3800 seconds ago; and, in a fresh
  handler, an event has a `revoked_at` one hour in the future and the pair's token has `iat` 5 seconds from now
- **THEN** both tokens reach the credential fetch; and a token of the second handler with `iat` 30 seconds ago answers 401

#### Scenario: an event without revoked_at counts from its receipt
- **WHEN** an event for the pair has no `revoked_at` and tokens have `iat` 30 seconds ago and 5 seconds from now
- **THEN** the first answers 401 with a body containing `token revoked` and the second reaches the credential fetch

#### Scenario: the set keeps the later revocation, counts its entries and drops expired ones
- **WHEN** on a fresh handler's `revokedGrants` set `Add` is called for a pair with a `revokedAt` 120 seconds ago and then,
  out of order, with 300 seconds ago; then for a second pair with a `revokedAt` 3629.2 seconds ago; then, after a real wait
  of 1.5 seconds (0.7 s tolerance over the 0.8 s the second entry has left), for a third pair with `revokedAt` now
- **THEN** after the first two calls `Len()` is 1, `Refuses` for the pair is true with an `iat` 130 seconds ago and false
  with an `iat` 100 seconds ago; after the third call `Len()` is 2 and `Refuses` for the second pair is false with an `iat`
  4000 seconds ago

#### Scenario: an event that names no agent or no service is not applied
- **WHEN** events with `agent_id` missing, with `service_id` missing and with both empty are applied to the handler's
  subscriber
- **THEN** each `HandleNotification` call returns a non-nil error, and a token of the pair with `iat` 120 seconds ago
  reaches the credential fetch

#### Scenario: a subscriber built without the set ignores the event
- **WHEN** `changes.NewSubscriber("", agents, jtis, nil)` receives `{"event_type":"agent.permission.revoked",
  "agent_id":"agent_3C7JAGMBGR9EMRS2AVGXDHQXDX","service_id":"svc_5ANANANANANANANANANANANANA","revoked_at":
  "2026-11-25T10:00:00+00:00"}` (both ids present) and then `{"event_type":"token.revoked",
  "jti":"jti_01DEF"}`
- **THEN** both calls return nil, and the token set contains `jti_01DEF`
