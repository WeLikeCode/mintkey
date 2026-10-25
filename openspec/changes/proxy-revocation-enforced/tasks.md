# Tasks: proxy-revocation-enforced

Each task writes its tests first and sees them fail for the reason it names, then changes the code. The tests are
top-level Go test functions without `t.Run` and use only API that exists before the change (design D5): a missing
method is detected by a type assertion to an interface the test file declares, which fails with `t.Fatal`. Run
`go test ./... -short` in `apps/proxy-plugin`, `go vet ./...` and `golangci-lint run` there.

## 1. Agent ids in every form, and the event key

- [ ] 1.1 Tests first, new file `apps/proxy-plugin/internal/revocation/agent_set_id_forms_test.go` (package
  `revocation_test`): `TestAgentSetMatchesWireAndUUIDForms` and `TestAgentSetAddedUUIDMatchesWireFormAndIgnoresEmpty`
  cover the two scenarios of the requirement "The agent revocation set treats every form of an agent id as one id",
  with the ids exactly as written there. Both fail before the change because `Contains` compares strings exactly (and
  `Add("")` adds an entry). New file `apps/proxy-plugin/internal/changes/subscriber_event_key_test.go` (package
  `changes_test`, its own sets built with `revocation.NewAgentRevocationSet()` and
  `revocation.NewJTIRevocationSet(100_000)` and `changes.NewSubscriber("", agents, jtis, nil)`):
  `TestHandleNotificationAcceptsEventKey` sends the three payloads of the scenario "payloads keyed by event are
  applied, and event_type wins over event" in that order and asserts all four outcomes; it fails before the change
  because `agent_01ABC` is not added.
  Then create `apps/proxy-plugin/internal/wireid/wireid.go` with `ToUUID` and `Canonical` exactly as design.md gives
  them (`math/big` for the 26-character form); in `apps/proxy-plugin/internal/revocation/agent_set.go` make `Add` and
  `Contains` use `wireid.Canonical(agentID, "agent_")` as the key and make `Add("")` return without adding; in
  `apps/proxy-plugin/internal/changes/subscriber.go` `HandleNotification` add the field `Event string \`json:"event"\``
  to the decoded struct and switch on `evt.EventType`, or on `evt.Event` when `evt.EventType` is empty. Nothing else
  in these files changes; the existing tests in `agent_set_test.go` and `subscriber_test.go` keep passing.

## 2. admin-api publishes event_type

- [ ] 2.1 Tests first, new file `tests/unit/admin_api/test_notify_event_type.py`, which puts `apps/admin-api/src` and
  `packages/python/mintkey-models` on `sys.path` as `tests/unit/admin_api/test_validate_agent_key_errors.py` does,
  with `T = "11111111-2222-3333-4444-555555555555"` and `A = "agent_3C7JAGMBGR9EMRS2AVGXDHQXDX"`. Sync test functions
  run coroutines with `asyncio.run`. A file-local `RecordingSession` has `async def execute(self, stmt,
  params=None)` that appends
  `(str(stmt), params)` to `self.calls` and returns a `MagicMock` whose `fetchone()` returns
  `SimpleNamespace(id="00000000-0000-0000-0000-0000000000aa", cnt=0, key_fingerprint="abcd1234", service_id=None,
  revoked_at=None)`; a helper `published(session)` returns `[(params["channel"], json.loads(params["payload"]))]` for
  every recorded call whose params contain `"channel"`. `test_notify_change_adds_event_type_and_keeps_the_rest` calls
  `admin_api.changes.publisher.notify_change` with the three payloads of the scenario "notify_change adds event_type
  and keeps the rest" (keeping copies to compare the caller's dicts) and asserts the three published objects with
  `==`. `test_agent_revocation_publishers_carry_event_type` calls `admin_api.api.agents.revoke_agent(tenant_id=UUID(T),
  agent_id=A, session=s, _authz=None)` and `admin_api.api.agents.delete_agent(...)` with the same arguments, each with
  a fresh `RecordingSession`, under `patch("admin_api.api.agents.set_tenant_context", new=AsyncMock())` and
  `patch("admin_api.api.agents.audit_emit", new=AsyncMock())`, and asserts `published(s)` equals the one pair of the
  scenario "the agent revocation publishers carry event_type". `test_api_key_revocation_publisher_carries_event_type`
  calls `admin_api.api.api_keys.revoke_api_key(tenant_id=UUID(T), agent_id=A, api_key_id="svckey_x",
  body=RevokeRequest(reason="test"), session=s, _authz=None)` under the same two patches on `admin_api.api.api_keys`,
  and asserts the pair of the scenario "the API key revocation publisher carries event_type". All three fail before
  the change because the published JSON has no `event_type`.
  Then in `apps/admin-api/src/admin_api/changes/publisher.py` change `notify_change` as design.md gives it (a copy of
  the payload, `event_type` added when only `event` is present, the docstring updated); its signature, its bound
  parameters and every call site stay as they are. Run `ruff check src/` and `mypy --strict src/admin_api/` in
  `apps/admin-api`.

## 3. Token ids are evicted after the longest token lifetime

- [ ] 3.1 Tests first, new file `apps/proxy-plugin/internal/revocation/jti_eviction_test.go` (package
  `revocation_test`): declare `type evictionRunner interface { RunEviction(ctx context.Context, interval, retention
  time.Duration) }`. `TestJTIRunEvictionDropsEntriesPastRetention` builds two sets with
  `revocation.NewJTIRevocationSet(10)`, adds `jti_old` to the first and `jti_new` to the second, asserts
  `any(set).(evictionRunner)` succeeds for both (else `t.Fatal`), starts `RunEviction(ctx, 10*time.Millisecond,
  time.Nanosecond)` on the first and `RunEviction(ctx, 10*time.Millisecond, time.Hour)` on the second in goroutines
  that close a `done` channel each when they return, polls every 10 ms for at most 2 s until the first set's `Len()` is
  0 (else `t.Fatal`), asserts the second set still `Contains("jti_new")`, cancels `ctx` and waits at most 2 s for both
  `done` channels (else `t.Fatal`). It fails before the change because the type assertion fails.
  Then in `apps/proxy-plugin/internal/revocation/jti_set.go` add `const JTIRetention = 3630 * time.Second` and
  `func (s *JTIRevocationSet) RunEviction(ctx context.Context, interval, retention time.Duration)` (a
  `time.NewTicker(interval)` loop that calls `s.Evict(retention)` on each tick, stops the ticker and returns when
  `ctx.Done()` is closed), with doc comments as in design.md.

## 4. The handler refuses revoked tokens

- [ ] 4.1 Tests first, new file `apps/proxy-plugin/cmd/proxy-plugin/revocation_enforced_test.go` (package `main`,
  using `testHandler()`, `buildTestJWTWithClaims` and `testSvcUUIDA` of `proxy_test.go`): declare
  `type changesSubscriberSource interface { changesSubscriber(dsn string, opts ...changes.SubscriberOption)
  *changes.Subscriber }`. Each test builds `h := testHandler()`, asserts `any(h).(changesSubscriberSource)` succeeds
  (else `t.Fatal` saying the handler cannot build a change subscriber over its own sets), gets `sub :=
  src.changesSubscriber("")`, calls `sub.HandleNotification` with the scenario's payload, builds the tokens with
  `buildTestJWTWithClaims(t, testSvcUUIDA, <sub>, <jti>)`, puts each token's public key at `h.pubKeys["testkey"]`
  before its request, and sends `GET /` with `Authorization: Bearer <token>`. `TestRevokedJTIIsRefusedBeforeVault`
  covers the scenario "a token revoked through the change channel is refused" (sub `agent_test` for both tokens);
  `TestRevokedAgentIsRefusedAcrossIDForms` covers "an agent revoked by its wire id is refused when the token carries
  its UUID" (jti `jti_01AAA` and `jti_01BBB`). A refusal asserts status 401 and a body containing `token revoked`;
  "reaches the credential fetch" asserts status 502. Both fail before the change because the type assertion fails.
  Then in `apps/proxy-plugin/cmd/proxy-plugin/main.go`: add the fields `revokedAgents` and `revokedJTIs` to
  `proxyHandler` and set them in `newProxyHandler` (its signature unchanged); add the method `changesSubscriber`;
  insert the gate of design.md directly after the "missing aud or tnt claim" refusal in `ServeHTTP`; in `main` remove
  the local `agentSet` and `jtiSet`, build the subscriber with `handler.changesSubscriber(dsn, subOpts...)` (the
  budget option block stays as it is), and after `ctx` is created start
  `go handler.revokedJTIs.RunEviction(ctx, time.Minute, revocation.JTIRetention)`. Update the comment above the
  subscriber block to say the sets are the handler's. Nothing else in `main.go` changes.
