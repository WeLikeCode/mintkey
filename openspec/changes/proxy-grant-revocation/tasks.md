# Tasks: proxy-grant-revocation

Go task: the red step keeps only test files, so the tests use only identifiers that exist before the change
(`newProxyHandler` through `testHandler`, `changesSubscriber`, `Subscriber.HandleNotification`, `ServeHTTP`,
`changes.NewSubscriber`, `buildScopeClaimsJWT`, `scopeRequest`) and reach the new behaviour through the subscriber and the
handler. Run `go test ./... -short`, `go vet ./...` and `golangci-lint run` in `apps/proxy-plugin`.

## 1. The proxy refuses the tokens of a revoked grant

- [x] 1.1 Tests first. New file `apps/proxy-plugin/cmd/proxy-plugin/grant_revocation_test.go` (package `main`, using
  `testHandler`, `buildScopeClaimsJWT` (the `extra` map overrides `sub` and adds `iat`), `buildTestJWTWithClaims`,
  `scopeRequest` and `assertScopeReachesVault`; a token's public key goes to `h.pubKeys["testkey"]` before its request). A
  helper `applyRevocation(t, h, agentWire, svcWire string, revokedAt any)` builds the JSON of the scenario's payload
  (`event` and `event_type` both `agent.permission.revoked`, `tenant_id` `11111111-2222-3333-4444-555555555555`,
  `permission_id` `perm_01X`, `revoked_at` omitted when nil, else `time.Time.UTC().Format("2006-01-02T15:04:05.000000-07:00")`, which writes `+00:00`
  as `datetime.isoformat()` does) and passes it to
  `h.changesSubscriber("").HandleNotification`. `TestRevokedGrantRefusesEarlierTokens` covers "tokens issued before the
  revocation are refused, later ones and other pairs are not" (R is the Unix second of `time.Now().Add(-60*time.Second)`;
  401 asserts the body contains `token revoked`); `TestTokenWithoutUsableIatIsRefused` covers "a token without a usable iat is
  refused while an entry exists"; `TestOldRevocationAddsNothingAndFutureCountsAsNow` covers "an old revocation adds nothing
  and a future one counts as received now"; `TestRevocationWithoutRevokedAtCountsFromReceipt` covers "an event without
  revoked_at counts from its receipt"; `TestGrantSetKeepsLaterAndDropsExpired` covers "the set keeps the later revocation,
  counts its entries and drops expired ones" (it reaches the set with `reflect.ValueOf(h).Elem().FieldByName("revokedGrants")`
  and its methods `Add`, `Refuses` and `Len` with `MethodByName`, and `t.Fatal`s naming what is missing; the 1.5 s wait is
  the only sleep); the first test also reads `h.metrics.WriteMetricsTo` for the denial line; `TestUnusableEventsAreNotApplied` covers "an event that names no agent or no service is
  not applied". New file `apps/proxy-plugin/internal/changes/subscriber_grant_revoked_test.go` (package `changes_test`):
  `TestSubscriberWithoutGrantSetIgnoresPermissionRevoked` covers "a subscriber built without the set ignores the event" (it
  passes before the change and guards the nil case). The five handler tests stay red until the subscriber and the handler know the event.
  Then create `apps/proxy-plugin/internal/revocation/grant_set.go` with `GrantRevocationSet` as the delta spec gives it (a
  `sync.RWMutex` and a `map[string]time.Time` keyed `wireid.Canonical(agent,"agent_") + "|" + wireid.Canonical(service,"svc_")`;
  an entry expires at `revokedAt.Add(JTIRetention)`; `Refuses` uses `time.Now()`), add `WithGrantRevocations` and the field
  `grants *revocation.GrantRevocationSet` to `Subscriber`, the `agent.permission.revoked` case in `HandleNotification` as
  design.md gives it (new struct fields `ServiceID string \`json:"service_id"\`` and `RevokedAt string \`json:"revoked_at"\``),
  the field `revokedGrants` of `proxyHandler` set in `newProxyHandler`, the option in `changesSubscriber`, and the gate and
  `iatClaim` helper in `ServeHTTP`. Update the comment of the revocation gate to say it also covers revoked grants. Nothing
  else in these files changes.
