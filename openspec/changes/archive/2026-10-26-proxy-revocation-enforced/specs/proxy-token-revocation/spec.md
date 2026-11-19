# Proxy token revocation

## Purpose

How admin-api publishes change events under the contract's `event_type` key, how the egress proxy learns from the
change channel which agents and tokens are revoked, and how it refuses their requests before it fetches a credential.

## ADDED Requirements

### Requirement: The proxy refuses a revoked token before the credential fetch
The egress proxy SHALL answer a JWT request with status 401 and the body `unauthorized: token revoked`, without
calling the vault and without contacting the upstream, when the token's `jti` is in the proxy's token revocation set
or its `sub` is in the proxy's agent revocation set. The check SHALL run directly after the claims are read and before
every other gate. The change subscriber the proxy starts SHALL add to the same sets the handler checks: it is built by
`func (h *proxyHandler) changesSubscriber(dsn string, opts ...changes.SubscriberOption) *changes.Subscriber`, which
later proxy changes also use.

#### Scenario: a token revoked through the change channel is refused
- **WHEN** the handler's change subscriber receives `{"event_type":"token.revoked","jti":"jti_01REVOKED"}` and a
  request then carries a valid token with that `jti`
- **THEN** the response is 401 with a body containing `token revoked`, and a token of the same agent with the `jti`
  `jti_01OTHER` reaches the credential fetch (502 from the unreachable test vault)

#### Scenario: an agent revoked by its wire id is refused when the token carries its UUID
- **WHEN** the handler's change subscriber receives admin-api's payload
  `{"event":"agent.revoked","agent_id":"agent_3C7JAGMBGR9EMRS2AVGXDHQXDX"}` and a request then carries a valid token
  whose `sub` is `6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd`
- **THEN** the response is 401 with a body containing `token revoked`, and a token whose `sub` is
  `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` reaches the credential fetch (502)

### Requirement: admin-api's change notifications carry event_type
admin-api's `notify_change(session, channel, payload)` (`admin_api.changes.publisher`) SHALL publish, for a payload
that has the key `event` and no key `event_type`, the payload plus `event_type` with the value of `event`; it SHALL keep
`event` and every other key, SHALL publish a payload that already has `event_type` as given, and SHALL NOT modify the
caller's dict. The revocation publishers `revoke_agent` and `delete_agent` (`admin_api.api.agents`) and
`revoke_api_key` (`admin_api.api.api_keys`) SHALL publish through it. (No admin-api code publishes `token.revoked`;
an operator or an embedding application sends it.)

#### Scenario: notify_change adds event_type and keeps the rest
- **WHEN** `notify_change` publishes `{"event": "token.revoked", "tenant_id": "11111111-2222-3333-4444-555555555555",
  "jti": "jti_01REVOKED"}` on `mintkey:agent`, `{"event": "credential.rotated", "tenant_id":
  "11111111-2222-3333-4444-555555555555", "service_id": "svc_5ANANANANANANANANANANANANA", "credential_id": "cred_x"}`
  on `mintkey:credential`, and `{"event_type": "budget.config_updated", "target_id": "perm_x"}` on `mintkey:agent`
- **THEN** the published JSON objects are the first two payloads each with `event_type` equal to their `event`, and the
  third payload unchanged; each is sent on its channel, and the caller's dicts are unchanged

#### Scenario: the agent revocation publishers carry event_type
- **WHEN** `revoke_agent` and `delete_agent` run for the tenant `11111111-2222-3333-4444-555555555555` and the agent
  `agent_3C7JAGMBGR9EMRS2AVGXDHQXDX`
- **THEN** each publishes on `mintkey:agent` exactly `{"event": "agent.revoked", "event_type": "agent.revoked",
  "tenant_id": "11111111-2222-3333-4444-555555555555", "agent_id": "agent_3C7JAGMBGR9EMRS2AVGXDHQXDX"}`

#### Scenario: the API key revocation publisher carries event_type
- **WHEN** `revoke_api_key` revokes the key `svckey_x` (fingerprint `abcd1234`) of that agent with the reason `test`
- **THEN** it publishes on `mintkey:agent` exactly `{"event": "api_key.revoked", "event_type": "api_key.revoked",
  "tenant_id": "11111111-2222-3333-4444-555555555555", "api_key_id": "svckey_x", "key_fingerprint": "abcd1234",
  "reason": "test"}`

### Requirement: The change subscriber reads the event type from event_type or event
`Subscriber.HandleNotification` SHALL take the event type from the key `event_type` and, when that key is absent or
empty, from the key `event`. When both are present, `event_type` SHALL decide.

#### Scenario: payloads keyed by event are applied, and event_type wins over event
- **WHEN** `HandleNotification` receives `{"event":"agent.revoked","agent_id":"agent_01ABC"}`,
  `{"event":"token.revoked","jti":"jti_01DEF"}` and
  `{"event_type":"token.revoked","event":"agent.revoked","jti":"jti_01XYZ","agent_id":"agent_01XYZ"}`
- **THEN** the agent set contains `agent_01ABC`, the token set contains `jti_01DEF` and `jti_01XYZ`, and the agent set
  does not contain `agent_01XYZ`

### Requirement: The agent revocation set treats every form of an agent id as one id
The new package `apps/proxy-plugin/internal/wireid` SHALL provide `func ToUUID(id, prefix string) (string, bool)` and
`func Canonical(id, prefix string) string` as design.md defines them (later proxy changes use both).
`AgentRevocationSet.Add` and `Contains` SHALL compare agent ids by `wireid.Canonical(id, "agent_")`: the canonical
wire form, the legacy 32-hex wire form and the dashed UUID in either case denote the same agent. An id that is not
decodable SHALL be compared exactly. `Add("")` SHALL add nothing.

#### Scenario: the wire forms and the UUID form match
- **WHEN** the set holds `agent_3C7JAGMBGR9EMRS2AVGXDHQXDX`
- **THEN** `Contains` is true for `6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd`, `6C3C950A-2E18-4BA9-8C89-5B875B1BF5BD`,
  `agent_6c3c950a2e184ba98c895b875b1bf5bd` and `agent_3c7jagmbgr9emrs2avgxdhqxdx`, and false for
  `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`

#### Scenario: a UUID added matches its wire form, and an empty id is never added
- **WHEN** the set holds `6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd` and `Add("")` has been called
- **THEN** `Contains("agent_3C7JAGMBGR9EMRS2AVGXDHQXDX")` is true and `Len()` is 1

### Requirement: Revoked token ids are evicted after the longest token lifetime
`JTIRevocationSet.RunEviction(ctx, interval, retention)` SHALL call `Evict(retention)` every `interval` and return when
`ctx` is done. The proxy SHALL run it with an interval of one minute and `revocation.JTIRetention` (3630 s).

#### Scenario: entries older than the retention are evicted and the loop stops
- **WHEN** a set holds one id, `RunEviction` runs with an interval of 10 ms and a retention of 1 ns, and a second set
  holding one id runs it with a retention of one hour
- **THEN** within 2 s the first set is empty while the second still holds its id, and after the context is cancelled
  both calls return within 2 s
