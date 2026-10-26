# Tasks: token-request-scope-claims

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Go tests are
top-level functions without `t.Run` and use only API that exists before the change (design D5). Run the touched
suites: `go test ./... -short`, `go vet ./...` and `golangci-lint run` in `apps/broker` and `apps/proxy-plugin`;
`uv run pytest apps/mcp-server/tests` and `uv run ruff check src/` in `apps/mcp-server`.

## 1. The broker accepts, checks and signs the limits

- [x] 1.1 Tests first, new file `apps/broker/internal/api/issue/issue_scope_claims_test.go` (package `issue_test`,
  using `newTestHandler(t)` and `testMCPToken` of `issue_test.go`). Add two file-local helpers: `postScopeIssue(t, h
  http.Handler, extra map[string]any) *httptest.ResponseRecorder` posts to `/v1/issue` with `X-Mintkey-Service-Token:
  testMCPToken` the JSON of `agent_id` `agent_01HZ0000000000000000000001`, `service_id`
  `svc_01HZ0000000000000000000002`, `tenant_id` `tenant_01HZ0000000000000000000003`, `scope` `call`, `ttl_seconds`
  300, merged with `extra`; `scopeTokenClaims(t, token string) map[string]any` base64url-decodes the token's middle
  segment and unmarshals it. `TestIssueSignsMethodsAndPathPrefixClaims` covers the scenario "the limits are signed as claims";
  it fails before the change because the token has no `methods` claim. `TestIssueRefusesInvalidScopeClaims` loops
  over the nine bodies of the scenario "each invalid limit is refused" (a slice of `map[string]any`, no `t.Run`) and
  asserts 400 and `mintkey:code` `validation_failed` for each, naming the body in the message; it fails before the
  change because each answers 200.
  Then in `apps/broker/internal/api/issue/issue.go` add the two `issueRequest` fields and `scopeClaims` exactly as
  design.md gives them, call it after the `ttl_seconds` check, answer a problem with `writeErr(w,
  http.StatusBadRequest, "validation_failed", title)`, and pass `Methods` and `PathPrefix` to `issuer.TokenRequest`;
  in `apps/broker/internal/issuer/issuer.go` add the two `TokenRequest` fields and set the claims only when non-empty,
  next to `service_kind`, and add both claims to the package comment. The audit event and everything else stay.

## 2. The proxy enforces the limits before the credential fetch

- [ ] 2.1 Tests first, new file `apps/proxy-plugin/cmd/proxy-plugin/scope_claims_test.go` (package `main`, using
  `testHandler()`, `mustMarshalJSON` and `testSvcUUIDA` of `proxy_test.go`). Add a file-local helper
  `buildScopeClaimsJWT(t *testing.T, aud string, extra map[string]any) (string, ed25519.PublicKey)` that signs, with
  `kid` `testkey`, the claims `iss` `mintkey/broker`, `sub` `agent_test`, `aud` `[aud]`, `tnt`
  `tenant-test-uuid-0001`, `scope` `call`, `jti` `jti_scope_test`, `exp` now + 600, merged with `extra` (a key of
  `extra` replaces the default; later changes reuse this helper), signed as `buildTestJWTWithClaims` does. Each
  request uses a fresh `httptest.NewRecorder()`, `Authorization: Bearer <token>`,
  and the token's key at `h.pubKeys["testkey"]`; a refusal asserts 403 and that the JSON body's `error` is the
  scenario's text; "reach the credential fetch" asserts 502. `TestScopeClaimsRefuseOtherMethodAndPathBeforeVault`
  covers the scenario "other methods and paths are refused, the permitted call goes through" (with `<aud>` =
  `testSvcUUIDA`); `TestScopeClaimsRefuseDotSegmentsAndMalformedClaims` covers "dot segments and malformed claims are
  refused". Both fail before the change because every request answers 502.
  Then create `apps/proxy-plugin/cmd/proxy-plugin/routing.go` with `upstreamPath` and
  `apps/proxy-plugin/cmd/proxy-plugin/scope_claims.go` with the two constants and `checkScopeClaims`, exactly as
  design.md gives them; in `apps/proxy-plugin/cmd/proxy-plugin/main.go` insert the check of design.md directly after
  the revocation gate in `ServeHTTP`, and replace the inline `strings.TrimPrefix(req.URL.Path, "/"+serviceID)` block
  by `req.URL.Path = upstreamPath(req.URL.Path, serviceID)` in the directors of `ServeHTTP`,
  `handleOAuth2ClientCredentials`, `handleHTTPDigest` and `handleOAuth2PasswordGrant` (not in `handleClassicalKey`).
  The existing tests in `cmd/proxy-plugin` keep passing.

## 3. The MCP server passes the limits through

- [ ] 3.1 Tests first, new file `apps/mcp-server/tests/test_request_token_scope_claims.py`. Sync test functions run
  coroutines with `asyncio.run`. Call `mcp_server.tools.request_token.request_token(request=MagicMock(),
  body=TokenRequest(...), session=session, agent_ctx={"agent_id": "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd",
  "tenant_id": "11111111-2222-3333-4444-555555555555"})` directly, with `monkeypatch` setting on that module
  `set_tenant_context` to an `AsyncMock`, `resolve_service_id` to an `AsyncMock` returning
  `uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")`, `resolve_email_service_id` to an `AsyncMock` (returning `None`,
  or that UUID for the email case), and `httpx` to a `types.SimpleNamespace(AsyncClient=FakeClient)` whose async
  context manager records each `post(url, json=..., headers=..., timeout=...)` and returns an object with
  `status_code` and `json()` (200 `{"token": "t", "expires_at": 1}`, or the scenario's 400 body). `session.execute` is
  an `AsyncMock` whose results' `fetchone()` return, in call order, the grant row (a `MagicMock` with `constraints =
  {}`; `None` for the email case), then the service row (`auth_scheme` `api_key_header`, or `ssh_private_key`), then for
  the email case the email grant row. Every test first asserts `isinstance(response, JSONResponse)`, then reads
  `status_code` and `json.loads(response.body)`. `test_request_token_forwards_scope_claims_only_when_given`,
  `test_request_token_answers_broker_validation_error_with_400` and
  `test_request_token_refuses_scope_claims_for_ssh_and_email_services` cover the first three scenarios of the
  requirement "The MCP server passes the limits to the broker"; `test_jsonrpc_request_token_forwards_scope_claims`
  covers the fourth: it awaits `mcp_server.tools.jsonrpc._dispatch_tool(client, "mintkey_request_token", args, {})`
  with a fake client whose `post(path, headers=..., json=...)` records `json`, reads the `mintkey_request_token` entry
  of `mcp_server.tools.jsonrpc.TOOLS`, and loads `docs/architecture/contracts/mcp/tools.yaml` (path from
  `Path(__file__).resolve().parents[3]`) with `yaml.safe_load` (PyYAML is installed in this environment with
  `uvicorn[standard]`) to find the tool named `request_token`. Each fails
  before the change for the reason it checks (the fields are dropped, a 400 becomes 502, the broker is called, the
  schemas lack the properties).
  Then in `apps/mcp-server/src/mcp_server/tools/request_token.py` add the two `TokenRequest` fields,
  `_scope_claims_http_only`, the two refusals, the optional payload keys and the 400 mapping exactly as design.md
  gives them; in `apps/mcp-server/src/mcp_server/tools/jsonrpc.py` add the two input-schema properties of
  `mintkey_request_token` and forward each argument only when present; in `docs/architecture/contracts/mcp/tools.yaml`
  add the two optional properties to `request_token`'s `input_schema` as design.md describes. The email token request
  and every other tool are unchanged.
