# Tasks: proxy-stored-target

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Go tasks: the red
step keeps only test files, so the Go tests use only identifiers that exist before the change (`ServeHTTP`, the
`handle*` methods, `scrubber.Scrub`, `config.Load`, `vault.GetCredentialResponse`, `credential.*`, `vaultv1.*`) and reach new behaviour
through those entry points; a test that needs a field or function the change adds goes through reflection or a request,
and `t.Fatal`s with a message that names what is missing. Run `go test ./... -short`, `go vet ./...` and
`golangci-lint run` in `apps/proxy-plugin`, and `ruff check src/` and `mypy --strict src/admin_api/` in `apps/admin-api`.

## 1. The backfill of stored targets

- [x] 1.1 Tests first, new file `tests/unit/admin_api/test_credential_target_backfill.py` (the `sys.path` header and
  `REPO_ROOT` of `tests/unit/admin_api/test_notify_event_type.py`; PyYAML is a dependency of the project):
  `test_backfill_changelog_fills_empty_targets_only` covers the scenario "the changelog fills empty targets only": it
  loads `apps/admin-api/db/changelog/033-credential-target-backfill.yaml` with `yaml.safe_load`, finds the one SQL change
  (`sql.sql` of the `changeSet`s), lower-cases and whitespace-normalises its text and asserts the substrings
  `update vault.credentials`, `set target_url`, `public.services`, `s.id = vc.service_id`, `s.tenant_id = vc.tenant_id`,
  `target_url = ''`, `~* '^https?://'` and `set_config('app.platform_admin_view', 'on', true)`; asserts the change set has
  a precondition `tableExists` on `vault.credentials` with `onFail: MARK_RAN` and a `rollback`; and loads
  `db.changelog-master.yaml` and asserts exactly one include has a `file` ending in `033-credential-target-backfill.yaml`
  (any position). It fails because the changelog file does not exist.
  Then create the changelog (one change set `033-credential-target-backfill-1`, author `mintkey`, `splitStatements: false`,
  the statement `SELECT set_config('app.platform_admin_view', 'on', true);` followed by an
  `UPDATE vault.credentials vc SET target_url = s.base_url FROM public.services s WHERE s.id = vc.service_id AND
  s.tenant_id = vc.tenant_id AND vc.target_url = '' AND s.base_url ~* '^https?://';`, rollback `SELECT 1`) and add its
  include to `apps/admin-api/db/changelog/db.changelog-master.yaml`; the number is a name, the include order is the merge
  order of the plan.

## 2. The scrubber keeps the whole body and a consistent length

- [ ] 2.1 Tests first, new file `apps/proxy-plugin/internal/scrubber/response_tail_test.go` (package `scrubber_test`):
  `TestScrubKeepsBodyPastScanBound` and `TestScrubUnchangedBodyKeepsLength` cover the scenario "Scrub keeps the tail of a
  large body and the length stays consistent" with the bodies as written there, where `<apikey>` and `<skey>` are the test
  values of the spec built in the test (`"api_key=" + <16 lowercase letters and digits>`, `"sk_live_" + <12 lowercase letters>`; no secret-shaped literal
  is written in the file) (build them with
  `bytes.Repeat([]byte(" "), 307200)` and `copy` at the two offsets; the response has `Header["Content-Length"]` and
  `ContentLength` set to 307200). The first asserts the body read to its end has 307194 bytes, contains
  `api_key=[REDACTED]` and the `<skey>` text, that `Content-Length` is absent from the header and `ContentLength` is
  -1; it stays red until `Scrub` passes the bytes past 256 KiB on. The second asserts a second 307200-byte response is returned
  byte for byte with header and `ContentLength` unchanged; it passes before the change and guards it.
  Then in `apps/proxy-plugin/internal/scrubber/response.go` add `ScrubWith(resp *http.Response, patterns bool, secrets
  ...[]byte) ScrubResult` and make `Scrub(resp)` call it with `true` and no secrets; add `ScrubHeaders(resp *http.Response, patterns
  bool, secrets ...[]byte) ScrubResult` (the header removals and the secret replacement in header values, no body read), which
  `ScrubWith` calls for its header part and `ModifyResponse` calls alone for an event stream; skip a nil or empty secret. `ScrubWith` reads the first 256 KiB;
  when `patterns` is true it applies the header removals and the three patterns as `Scrub` does today, and for every
  call it then applies the secrets (each secret of at least 8 bytes in its raw, `base64.StdEncoding` and
  `url.QueryEscape` forms, longest first, `bytes.ReplaceAll` with `[REDACTED]`), replaces
  each secret form inside each value of each header (only the matching text; the header keeps its name and its other
  values), stores the read error of the head in `ScrubResult.Err`, sets `resp.Body` to the scrubbed head
  followed by the unread rest (`io.MultiReader`, closing the original), and, only when the head changed, deletes
  `Content-Length` and sets `resp.ContentLength` to -1. The `Detected` and `Locations` results are as before, with
  `header:<Name>` for a redacted header value. Update the package comment (the scan bound, the tail, the secrets).

## 3. The proxy uses the stored target only

- [ ] 3.1 Tests first, new file `apps/proxy-plugin/cmd/proxy-plugin/stored_target_test.go` (package `main`). Helpers:
  `startFakeVault(t, resp *vaultv1.GetCredentialResponse) *vault.Client` serves `GetCredential` on `127.0.0.1:0` from a
  struct that embeds `vaultv1.UnimplementedVaultAdapterServer` and returns `proto.Clone(resp)`, and returns
  `vault.NewClient(addr, "", "")`; `countingUpstream(t)` returns an `httptest.Server` and a function that gives its request
  count and last headers; `callFlows(t, h, targetFor, header)` runs the five flows against one stored-target value and
  returns the five recorders: generic (`h.vaultClient =
  startFakeVault(...)` with a bearer credential `<tokenA>`, a token from `buildScopeClaimsJWT(t,
  testSvcUUIDA, nil)` in `h.pubKeys["testkey"]`, `GET /v1/call/<testSvcUUIDA>/echo`), classical key (`h.ckHandler =
  classicalkey.NewHandler(classicalkey.Config{BrokerURL: <httptest broker answering {"api_key_id":"k1","agent_id":"agent_ck",
  "service_id":"<testSvcUUIDA>","allowed_actions":["call"]}>, CacheTTL: time.Minute})`, bearer `mk_svckey_test`, headers
  `X-Mintkey-Service-ID` and `X-Mintkey-Tenant-ID: tenant-test-uuid-0001`, the same fake vault), and the three direct
  calls `h.handleHTTPDigest`, `h.handleOAuth2ClientCredentials` (fake token endpoint, `credential.NewTokenExchangerAllowPrivate()`
  and `cache.NewTokenCache()` as in `oauth2_client_credentials_dispatch_test.go`) and `h.handleOAuth2PasswordGrant` (payload
  as in `proxy_test.go`'s password-grant test), each with a `vault.GetCredentialResponse` whose `TargetURL` is `targetFor`.
  Each request carries `X-Mintkey-Target: <upstream B URL>` and `h.cfg.DefaultTarget` is set to upstream C's URL.
  `TestStoredTargetWinsInEveryFlow` covers "the stored target wins over the header and the default" (A gets five
  requests, one per flow, B and C none, and no request A received has `X-Mintkey-Target`);
  `TestMissingStoredTargetIsRefusedInEveryFlow` covers "a credential with no stored target is refused" (five 502 answers with
  the body `bad gateway: no target URL stored for this credential`, no request at B or C);
  `TestNonHTTPStoredTargetIsRefused` covers "a stored target that is not an http or https URL is refused" for `ssh://host:22`,
  `/relative/path`, `http://` and `://x` through `handleHTTPDigest` and the generic flow (502, `bad gateway: invalid target
  URL`). The three stay red until `resolveTarget` exists and the flows use it.
  Then create `apps/proxy-plugin/cmd/proxy-plugin/target.go` with `resolveTarget` exactly as the spec gives it, and in
  `main.go` replace the target block of each of the five flows with a call to it (on a nil result: `IncProxyDenied(serviceID,
  "backend_error")` in the four flows that count denials today, none in `handleClassicalKey`,
  `http.Error(w, text, http.StatusBadGateway)`, return); remove every
  read of `X-Mintkey-Target` and `h.cfg.DefaultTarget`; keep the Directors' `req.Header.Del("X-Mintkey-Target")`. Change the
  comment of `config.Config.DefaultTarget` (`apps/proxy-plugin/internal/config/config.go`: kept for deployments that still
  set `DEFAULT_TARGET`; the proxy does not read it) and the comment of `GetCredentialResponse.TargetURL`
  (`apps/proxy-plugin/internal/vault/client.go`: the only source of the upstream).

## 4. Every proxied response is scrubbed

- [ ] 4.1 Tests first, new file `apps/proxy-plugin/cmd/proxy-plugin/response_scrubbing_test.go` (package `main`, using the
  helpers of `stored_target_test.go`). `TestUpstreamEchoDoesNotReachTheCaller` covers "a credential echoed by the upstream
  does not reach the caller" (generic and classical flows, the upstream builds the body from the request's `Authorization`
  header and sets `X-Echo` and `Set-Cookie`; each runs with `h.cfg` as `testHandler` builds it and again with `h.cfg =
  config.Load()` under `t.Setenv("MINTKEY_PROXY_SCRUB_PATTERNS", "true")`); `TestPatternRulesFollowTheSetting` covers
  "the pattern rules apply only when the setting is on" the same way (the test builds `<jwt>`, `<skey>` and `<apikey>` of the
  spec: the JWT as `base64.RawURLEncoding` of the two JSON texts and of `bytes.Repeat([]byte{1}, 32)` joined by dots); `TestExchangedTokenIsRedacted` covers "the exchanged token of the OAuth2 flows
  is redacted too"; `TestCleanResponsePassesThrough` covers "a clean response passes through unchanged" (all five flows);
  `TestEventStreamIsNotBuffered` serves the handler with `httptest.NewServer(h)` and covers "an event stream is not
  buffered" with a 5 s read tolerance and a release channel (it also asserts the `X-Echo` header is redacted and the event
  text is not); `TestEncodedBodiesAreDecodedOrRefused` covers "encoded bodies
  are decoded or refused" (the upstream uses `compress/gzip` when its request has `Accept-Encoding: gzip`);
  `TestUnreachableUpstreamAnswersWithText` covers "an unreachable upstream answers 502 with a text" (the target is the URL of
  a closed `httptest` server); `TestSecretInsideLongerValueAndMultiValueHeader` covers "a secret inside a longer value and
  in a multi-value header"; `TestUndecodableBodyIsRefused` covers "a body that fails to decode is refused"; `TestShortEncodedAndEmptySecrets` covers "short secrets, encoded forms and
  empty secrets" (bearer values `abc1234`, `<tokenC>` and empty). They stay red until `newUpstreamProxy` exists and the flows use it (the second run of the two
  setting tests reads `ScrubPatterns` of the loaded config by `reflect.ValueOf(cfg).Elem().FieldByName("ScrubPatterns")`
  and `t.Fatal`s naming the missing field).
  New file `apps/proxy-plugin/internal/config/scrub_patterns_test.go` (package `config_test`): `TestScrubPatternsFromEnvironment`
  covers "the setting is read from the environment" with `t.Setenv` and the reflected field; it stays red until the field
  exists.
  Then add `ScrubPatterns bool` to `config.Config` and read it in `Load` (`strconv.ParseBool` of
  `MINTKEY_PROXY_SCRUB_PATTERNS`, false on an empty or unparsable value; the field's comment says the pattern rules are
  off by default), then create `apps/proxy-plugin/cmd/proxy-plugin/upstream.go` with `newUpstreamProxy` as design.md gives it (a small
  `upstreamTransport` type whose `RoundTrip` clones the request, deletes `Accept-Encoding` and calls `base`, or
  `http.DefaultTransport` when `base` is nil; the unexported `errEncodedResponse` and `errBodyUnreadable`, which `ModifyResponse`
  returns after closing the body and `ErrorHandler` tells apart with `errors.Is`, as design.md gives it; the log line is
  `proxy-plugin: credential echo removed (svc=<safeID> locations=<names>)`), and replace the five
  `httputil.NewSingleHostReverseProxy(targetURL)` calls of `main.go` with it: the digest flow passes its digest transport as
  `base` and nothing as `injected`, the others pass `injected` as design.md lists it, and the Directors stay as they are.
  The same task updates the live-stack tests that read the credential back from the mock backend, which echoes what it
  receives (`apps/mock-backend/src/mock_backend/rest/main.py`: `received_key`, `received_token`): in
  `tests/acceptance/test_e2e_smoke.py` (step 10), `tests/acceptance/test_golden_path.py`,
  `tests/acceptance/test_data_plane_smoke.py` and `tests/acceptance/test_classical_key.py` every assertion that
  `received_key` equals the registered secret becomes `received_key == "[REDACTED]"` (the proxy replaces exactly the value
  it injected, so the text proves the mock backend received the stored secret), with a comment saying so. These tests need the compose stack and
  `MINTKEY_INTEGRATION_TEST=true`; neither the gate nor the unit jobs run them, and the repository's smoke and integration
  jobs do.
