# Tasks: proxy-data-plane-paths

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Go tests are
top-level functions without `t.Run` and use only API that exists before the change (design D5). Run
`go test ./... -short`, `go vet ./...` and `golangci-lint run` in `apps/proxy-plugin` and `apps/kong-syncer`, and the
acceptance suite as `.l4/gates/test.sh` runs it.

## 1. One path form, and the routing headers stay in the proxy

- [ ] 1.1 Tests first, new file `apps/proxy-plugin/cmd/proxy-plugin/data_plane_paths_test.go` (package `main`, using
  `testHandler()`, `testSvcUUIDA` of `proxy_test.go` and `buildScopeClaimsJWT` of `scope_claims_test.go`).
  `TestUpstreamPathStripsCallPrefixOfTheTokensService` calls `upstreamPath` with the five paths of the scenario "the
  call prefix is removed for the token's service only" and asserts the five results.
  `TestDigestDirectorForwardsBarePathWithoutRoutingHeaders` starts an `httptest.NewServer` that records the request
  path and both headers and answers 200, builds `credResp := &vault.GetCredentialResponse{AuthScheme:
  int32(credential.AuthSchemeHTTPDigest), Plaintext: []byte(`{"public_key":"pk-test","private_key":"sk-test"}`),
  TargetURL: upstream.URL + "/base"}`, and calls `h.handleHTTPDigest(rw, req, credResp, "tenant-test-uuid-0001",
  testSvcUUIDA, "agent_test", time.Now())` with the request of the scenario "the upstream receives the bare path under
  its base path, without routing headers"; it asserts 200, the path `/base/v1/messages` and two empty headers.
  `TestPathPrefixClaimMatchesCallForm` covers "a path_prefix claim matches the call form" with
  `buildScopeClaimsJWT(t, testSvcUUIDA, map[string]any{"path_prefix": "/v1/messages"})` and asserts 502. Each fails
  before the change (the prefix is kept, the headers reach the upstream, the claim check answers 403).
  Then in `apps/proxy-plugin/cmd/proxy-plugin/routing.go` extend `upstreamPath` as design.md gives it (import
  `internal/wireid`), and in `apps/proxy-plugin/cmd/proxy-plugin/main.go`, in the directors of `ServeHTTP`,
  `handleOAuth2ClientCredentials`, `handleHTTPDigest` and `handleOAuth2PasswordGrant`, move
  `req.URL.Path = upstreamPath(req.URL.Path, serviceID)` before `originalDirector(req)` and add
  `req.Header.Del("X-Mintkey-Service-ID")` and `req.Header.Del("X-Mintkey-Tenant-ID")` after
  `req.Header.Del("X-Mintkey-Target")`. `handleClassicalKey` is not changed.

## 2. Strict mode always has an address

- [ ] 2.1 Tests first, in the same file: `TestStrictModeRefusesUnaddressedRequest` covers "an unaddressed request is
  refused in strict mode only" with `testHandlerStrictWithAudit(mock)` (and `&mockAuditQueue{}`) and `testHandler()`
  of `proxy_test.go`, asserting the 403 JSON body's `error`, exactly one captured event with `EventType`
  `proxy.aud_mismatch_rejected`, `Payload["url_service_id"] == ""` and `Payload["mode"] == "strict"`, and 502 for the
  permissive handler. `TestStrictModeComparesHeaderAndWireFormWithAudience` covers "the header and the wire form are
  compared with the audience" with `testHandlerStrict()`. Tokens are `buildScopeClaimsJWT(t, testSvcUUIDA, nil)`. Both
  fail before the change (unaddressed and `svc_` requests skip the check and answer 502).
  Then add `addressedServiceID` to `apps/proxy-plugin/cmd/proxy-plugin/routing.go` and replace the audience check in
  `ServeHTTP` (`apps/proxy-plugin/cmd/proxy-plugin/main.go`) by the switch of design.md, keeping the existing
  mismatch branch's log line, audit event and 403 body with `addressed` in place of `urlSvcID`. `urlServiceID`,
  `isUUIDShape` and the existing tests (`TestAudEnforcement_*`, `TestAudMismatchRejected_*`, `TestURLServiceID`,
  `TestAudCheck_LogDoesNotContainSecret`) are unchanged and keep passing.

## 3. Kong-syncer adds the headers to the virtual-host route

- [ ] 3.1 Tests first, new file `apps/kong-syncer/internal/kong/yaml_vhost_headers_test.go` (package `kong_test`):
  `TestVirtualHostRouteCarriesRoutingHeaders` generates the YAML for the service of the scenario "the virtual-host
  route carries the headers" (`TenantSlug` `t_default`, `Slug` `openai`, `BaseURL` `https://api.openai.com`, proxy URL
  `http://proxy-plugin:8086`), parses it with `gopkg.in/yaml.v3` into `map[string]any`, and for each of the two routes
  of `services[0]` asserts one plugin named `request-transformer` whose `config.add.headers` equals the two header
  strings. It fails before the change because the virtual-host route has no plugins.
  Then in `apps/kong-syncer/internal/kong/yaml.go` add `routingHeaderPlugins(svc ServiceEntry) []kongPlugin` (the
  existing path-route plugin value) and use it for both routes; update the comment of the path route to say both
  routes carry the headers. The existing tests in `yaml_test.go` keep passing.

## 4. The data-plane-only guide

- [ ] 4.1 Tests first, new file `tests/acceptance/test_data_plane_only_doc.py` (no project import; `ROOT =
  Path(__file__).resolve().parents[2]`, `DOC = ROOT / "docs" / "guides" / "data-plane-only.md"`).
  `test_data_plane_doc_names_every_setting` asserts `DOC.is_file()` and then that the text contains each of:
  `broker`, `proxy-plugin`, `vault-adapter`, `MINTKEY_VAULT_BACKEND=sqlite`, `MINTKEY_VAULT_FILE_PATH`, `admin-api`,
  `Kong`, `kong-syncer`, `mcp-server`, `Keycloak`, `MINTKEY_VAULT_KEK_FILE`, `MINTKEY_BROKER_SIGNING_KEY_FILE`,
  `MINTKEY_VAULT_PROXY_IDENTITY_ID`, `MINTKEY_VAULT_PROXY_TOKEN`, `PutCredential`, `MINTKEY_VAULT_ADMIN_IDENTITY_ID`,
  `MINTKEY_VAULT_ADMIN_TOKEN`, `BROKER_ADDR`, `VAULT_GRPC_ADDR`, `PLUGIN_PORT`, `POST /v1/issue`,
  `X-Mintkey-Service-Token`, `MINTKEY_MCP_SERVICE_TOKEN`, `ttl_seconds`, `methods`, `path_prefix`, `/v1/call/`, `svc_`,
  `MINTKEY_ENV=production`, `MINTKEY_AUD_ENFORCEMENT`, `service not addressed`, `MINTKEY_ADMIN_API_URL`,
  `POST /v1/internal/audit/emit`, `MINTKEY_BROKER_SERVICE_TOKEN`, `MINTKEY_PROXY_SERVICE_TOKEN`, `event_type`,
  `DATABASE_URL`, `NOTIFY`, `mintkey:agent`, `token.revoked`, `agent.revoked` (one assertion message listing every
  missing name). `test_data_plane_doc_has_no_mermaid_and_no_credential_values` asserts `DOC.is_file()`, that
  ```` ```mermaid ```` does not occur, and that none of the values of `services["proxy-plugin"]["environment"]` in
  `infra/compose/docker-compose.yml` (read with `yaml.safe_load`) whose key ends in `_TOKEN` occurs, counting only
  string values of at least 16 characters with no `${` (empty values, interpolations and short placeholders are
  skipped; the environment may be a mapping or a list of `KEY=VALUE`). Both fail before
  the change because the file does not exist.
  Then write `docs/guides/data-plane-only.md` with the seven sections of design.md, in that order, stating each fact
  listed there.
