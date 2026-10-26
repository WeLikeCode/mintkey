# Design: proxy-revocation-enforced

## Context

`main` in `apps/proxy-plugin/cmd/proxy-plugin/main.go` creates `revocation.NewAgentRevocationSet()` and
`revocation.NewJTIRevocationSet(10_000)` as locals and, when `DATABASE_URL` is set, passes them with the classical-key
handler to `changes.NewSubscriber(dsn, agentSet, jtiSet, ckHandler, subOpts...)`, which `LISTEN`s on `mintkey:agent`.
`Subscriber.HandleNotification` adds `agent_id` on `agent.revoked` and `jti` on `token.revoked`. `ServeHTTP` verifies
the JWT, reads `aud` (`serviceID`), `tnt` (`tenantID`) and `sub` (`agentID`), refuses a token without `aud` or `tnt`,
then runs the `read:atlas` gate, the audience check, the budget check and the vault `GetCredential`. Nothing reads the
sets. Wire ids follow ADR-0017.11: `<prefix>_<26 Crockford base32>` (canonical) or `<prefix>_<32 hex>` (legacy), the
encoding of `db_uuid_to_wire` in `apps/admin-api/src/admin_api/utils/wire_ids.py` (the 128-bit UUID value written as
26 base-32 digits, most significant first; decoding keeps the low 128 bits).

admin-api publishes every change through `notify_change(session, channel, payload)` in
`apps/admin-api/src/admin_api/changes/publisher.py`, which runs `SELECT pg_notify(:channel, :payload)` with
`json.dumps(payload)`. Its callers (all in `apps/admin-api/src/admin_api/api/`), with the event name and the key it is
under today:

| Module | Function | Channel | Event (key) |
|---|---|---|---|
| `agents.py` | `create_agent` | `mintkey:agent` | `agent.created` (`event`) |
| `agents.py` | `revoke_agent` | `mintkey:agent` | `agent.revoked` (`event`) |
| `agents.py` | `rotate_agent_key` | `mintkey:agent` | `agent.api_key_rotated` (`event`) |
| `agents.py` | `set_agent_ssh_pubkey` | `mintkey:agent` | `agent.ssh_pubkey.set` / `.rotated` (`event`) |
| `agents.py` | `delete_agent` | `mintkey:agent` | `agent.revoked` (`event`) |
| `api_keys.py` | `revoke_api_key` | `mintkey:agent` | `api_key.revoked` (`event`) |
| `agent_secrets.py` | `create_agent_secret`, `update_agent_secret`, `delete_agent_secret`, `create_agent_secret_grant`, `delete_agent_secret_grant` | `mintkey:agent` | `agent_secret.*`, `agent_secret_grant.*` (`event`) |
| `email_permission_grants.py` | `create_email_permission_grant`, `delete_email_permission_grant` | `mintkey:agent` | `email_permission_grant.*` (`event`) |
| `permissions.py` | `revoke_permission` | `mintkey:agent` | `agent.permission.revoked` (`event`) |
| `permissions.py` | `update_permission` (two calls) | `mintkey:agent` | `budget.config_updated` (`event_type`) |
| `budgets.py` | `reset_budget` | `mintkey:agent` | `budget.config_updated` (`event_type`) |
| `credentials.py` | `create_credential` | `mintkey:credential` | `credential.registered` / `credential.rotated` (`event`) |
| `credentials.py` | `rotate_credential` | `mintkey:credential` | `credential.rotated` (`event`) |
| `credentials.py` | `delete_credential_version` | `mintkey:credential` | `credential.revoked` (`event`) |
| `services.py` | `create_service`, `create_service_from_template`, `update_service`, `delete_service` | `mintkey:service` | `service.registered`, `.updated`, `.deleted` (`event`) |

The subscribers and the names they act on: the egress proxy (`mintkey:agent`: `agent.revoked`, `token.revoked`,
`api_key.revoked`, `budget.config_updated`, by `event_type`), the MCP server (`mintkey:agent`: `agent.revoked` by
`event_type`; `mintkey:service`: `tenant_id` only), the vault adapter (`mintkey:credential`: `credential.rotated` by
`event_type`), Kong-syncer (`mintkey:service`: any notification triggers a reconcile) and the SSH proxy (`agent.revoked`
by `event_type` and `target_id`, through `packages/go/changes.Client`, which does not open a `LISTEN` yet).
No admin-api code publishes `token.revoked`.

## Interfaces

admin-api, `changes/publisher.py` (signature unchanged):

```python
async def notify_change(session: AsyncSession, channel: str, payload: dict[str, object]) -> None:
    """... When payload has "event" and no "event_type", the published JSON also carries "event_type" with the same
    value; the caller's dict is not modified; a payload with "event_type" is published as given."""
    body = dict(payload)
    if "event" in body and "event_type" not in body:
        body["event_type"] = body["event"]
    await session.execute(text("SELECT pg_notify(:channel, :payload)"), {"channel": channel, "payload": json.dumps(body)})
```

The call sites above are not edited: the one function covers all of them.

New package `apps/proxy-plugin/internal/wireid` (`wireid.go`):

```go
// ToUUID returns the lowercase dashed UUID that id denotes, and true; or "", false.
// prefix includes the underscore ("agent_", "svc_", "tenant_").
//   prefix + 26 Crockford characters (either case; alphabet 0123456789ABCDEFGHJKMNPQRSTVWXYZ, no I L O U)
//     -> the 130-bit big-endian base-32 value masked to its low 128 bits (math/big), as 8-4-4-4-12 hex
//   prefix + 32 hex digits (either case) -> those digits, dashed
//   a dashed UUID (36 characters, hex at every non-dash position) -> lowercased
//   32 hex digits, no prefix -> dashed, lowercased
//   anything else (including "") -> "", false
func ToUUID(id, prefix string) (string, bool)

// Canonical returns ToUUID(id, prefix) when it succeeds, else id unchanged.
func Canonical(id, prefix string) string
```

Vectors (computed with `db_uuid_to_wire` / `wire_to_db_uuid`): `agent_3C7JAGMBGR9EMRS2AVGXDHQXDX`,
`agent_3c7jagmbgr9emrs2avgxdhqxdx`, `agent_6c3c950a2e184ba98c895b875b1bf5bd` and `6C3C950A-2E18-4BA9-8C89-5B875B1BF5BD`
all give `6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd`; `svc_5ANANANANANANANANANANANANA` gives
`aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`; `agent_01ABC`, `agent_test` and `jti_01DEF` are not decodable.

`internal/revocation`:

```go
// AgentRevocationSet: Add and Contains key the set by wireid.Canonical(agentID, "agent_"). Add("") does nothing.
func (s *AgentRevocationSet) Add(agentID string)
func (s *AgentRevocationSet) Contains(agentID string) bool

// JTIRetention is the longest time a token can stay valid after it is revoked: the broker's 3600 s maximum TTL
// plus the proxy's 30 s clock skew.
const JTIRetention = 3630 * time.Second

// RunEviction calls s.Evict(retention) every interval until ctx is done, then returns.
func (s *JTIRevocationSet) RunEviction(ctx context.Context, interval, retention time.Duration)
```

`internal/changes`: `HandleNotification` decodes an extra field `Event string \`json:"event"\`` and switches on
`event_type`, or on `event` when `event_type` is empty. Nothing else in the subscriber changes.

`cmd/proxy-plugin` (`main.go`):

```go
type proxyHandler struct {
	// ... existing fields ...
	revokedAgents *revocation.AgentRevocationSet // never nil after newProxyHandler
	revokedJTIs   *revocation.JTIRevocationSet   // never nil after newProxyHandler
}

// newProxyHandler (signature unchanged) also sets
//   revokedAgents: revocation.NewAgentRevocationSet(), revokedJTIs: revocation.NewJTIRevocationSet(10_000)

// changesSubscriber returns changes.NewSubscriber(dsn, h.revokedAgents, h.revokedJTIs, h.ckHandler, opts...).
func (h *proxyHandler) changesSubscriber(dsn string, opts ...changes.SubscriberOption) *changes.Subscriber
```

`main` drops its local sets, builds the subscriber with `handler.changesSubscriber(dsn, subOpts...)` (the budget option
logic stays as it is), and starts `go handler.revokedJTIs.RunEviction(ctx, time.Minute, revocation.JTIRetention)`
after `ctx` is created, whether or not `DATABASE_URL` is set.

The gate in `ServeHTTP`, placed directly after the "missing aud or tnt claim" refusal and before the `read:atlas` gate:

```go
jti, _ := claims["jti"].(string)
if (jti != "" && h.revokedJTIs.Contains(jti)) || (agentID != "" && h.revokedAgents.Contains(agentID)) {
	h.metrics.IncProxyDenied(serviceID, "revoked")
	http.Error(w, "unauthorized: token revoked", http.StatusUnauthorized)
	return
}
```

## Decisions

**D1. One answer for both kinds of revocation.** `401` with the plain-text body `unauthorized: token revoked`, the
form the handler's other 401 answers use. The body does not say whether the token or the agent was revoked, and no
audit event is added (the audit event types are a closed contract; the `revoked` reason of
`mintkey_proxy_denied_total` already exists in `internal/metrics`).

**D2. Normalise ids inside the agent set.** The set is the one place both forms meet (the subscriber adds, the handler
asks). An id that is not decodable keeps its exact form, so every id that matched before still matches, and the
existing tests (`agent_01ABC`) keep passing.

**D3. Fix the key at the source and accept both in the proxy.** The contract names `event_type`; adding it in
`notify_change` makes every publisher conform at once (no call site can forget it, including future ones), and keeping
`event` leaves every existing reader and test of `event` working. The proxy additionally reads `event` when
`event_type` is absent, so a new proxy works with an admin-api deployed before this change. The pins are tests of the
published JSON, captured at `session.execute`, for `notify_change` itself (with the `token.revoked` and
`credential.rotated` shapes the subscribers read) and for the three revocation publishers (`revoke_agent`,
`delete_agent`, `revoke_api_key`). `budget.config_updated` already carries `event_type` and is not pinned again: a new
test of it would pass before the change.

**D4. Evict by age, not by count.** A revoked id is useless once every token that could carry it has expired:
`JTIRetention` covers the longest TTL the broker issues (`ttl_seconds` at most 3600 in
`apps/broker/internal/api/issue/issue.go`) plus the verifier's skew. The capacity stays 10,000 per retention window.

**D5. How the tests reach new code.** The harness's red step keeps only test files for non-Python code: it restores
every other production file, so a Go test may not name a function or field that does not exist yet. The new tests
use only existing API
(`Add`, `Contains`, `HandleNotification`, `testHandler`, `ServeHTTP`) and reach the two new methods through interfaces
they declare themselves, with a type assertion that fails the test (`t.Fatal`) when the method is missing. They are
top-level test functions without `t.Run`, so each is one case in the report. No red test names a symbol this change
adds (scaffold: none): the Go tests use only `NewAgentRevocationSet`, `NewJTIRevocationSet`, `Add`, `Contains`,
`Len`, `changes.NewSubscriber`, `HandleNotification`, `changes.SubscriberOption`, `changes.Subscriber`, `testHandler`,
`buildTestJWTWithClaims` and `ServeHTTP`, and the pytest calls `notify_change`, `revoke_agent`, `delete_agent` and
`revoke_api_key`, all of which exist before it. A failing Go test is reported by
`gotestsum` as `<failure message="Failed">`, which the gate counts as an assertion failure.

## Failure cases

- `DATABASE_URL` unset: no subscriber; the sets stay empty and every token is judged as before.
- A notification that is not JSON, or has neither key: ignored, as today.
- `agent.revoked` without `agent_id`: `Add("")` does nothing, so a token without `sub` is not refused by it.
- A token without `jti`: only the agent check applies.
- The set is full (10,000 ids revoked within one retention window): `Add` still ignores the newest id; the eviction
  loop frees space as entries age.
- A payload that already has `event_type`, or has neither key: `notify_change` publishes it as given.
- Tests that patch `notify_change` at a call site (`tests/unit/admin_api/test_revocation.py`, `test_api_keys.py`,
  `test_permissions.py`, `test_agent_secrets.py`) or assert `payload["event"]` keep passing: the key stays.
- Unchanged answers, covered by existing tests: an unrevoked token reaches the vault (`TestAudEnforcement_*`,
  `TestReadAtlasGate` in `cmd/proxy-plugin`); the classical-key path, which is dispatched before the JWT checks;
  the existing subscriber and set tests.

## What later changes rely on

`token-request-scope-claims`, `proxy-budget-check` and `proxy-data-plane-paths` assume this change is merged: the
`wireid` package, `proxyHandler.changesSubscriber`, and the revocation gate as the first check after the claims are
read.

## Open questions

- No Go unit has been implemented in this repository through the test gate's red step before; D5 is written for it.
- The SSH proxy acts on `agent.revoked` by `target_id`, which admin-api's payload does not carry, and its change
  client (`packages/go/changes.Client`, built with a nil connection) does not `LISTEN` yet ("T-1.2.2" in its comments).
  The key fix here is necessary for it but not sufficient; it needs its own change.
- The vault adapter will now act on `credential.rotated` (`InvalidateByService(tenant_id, service_id)`); the payload's
  `service_id` is the wire form the request used. Whether its cache is keyed by the same form is not verified here.
- A live check (revoke an agent in the admin UI, call the proxy within 2 s) needs the compose stack and is a person's
  check; the unit tests feed the subscriber the exact payloads admin-api publishes.
