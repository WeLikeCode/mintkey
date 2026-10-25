# Tasks: broker-service-token-required

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Run the touched
module's tests (`go test ./... -short` in `apps/broker` or `apps/vault-adapter`), `go vet ./...` and `golangci-lint run`
there. Every new test compiles against the base code (design D7): it uses only functions, types and fields that exist
before the change, and reaches a new method through an interface the test file declares, with a type assertion that
calls `t.Fatal` when the method is missing. Tests are top-level functions without `t.Run`. New test files must not
redeclare names that already exist in their test package (`testMCPToken`, `newTestHandler` in `issue_test`;
`proxyToken`, `mockStore`, `post`, `reqBody`, `errCode`, `newHandler` in `resolve_test`; `newTestGRPCServer`,
`newTestGRPCServerWithAuth`, `mdWithIdentity`, `outCtx`, `contains` in `server`).

## 1. Broker endpoints refuse every request when their token is not configured

- [ ] 1.1 Tests first, new file `apps/broker/internal/api/issue/issue_empty_token_test.go` (package `issue_test`):
  build an `*issuer.Issuer` as `newTestHandler` in `issue_test.go` does, and a fake `issue.AuditEnqueuer` that counts
  `Enqueue` calls. `TestIssue_EmptyConfiguredToken_NoHeader_Returns401`,
  `TestIssue_EmptyConfiguredToken_EmptyHeader_Returns401` and `TestIssue_EmptyConfiguredToken_AnyHeader_Returns401`
  cover the first three scenarios of the requirement "A broker endpoint with no configured service token refuses every
  request" with `issue.NewHandlerWithAudit(iss, "", fake)` and a valid JSON body (`agent_id`, `service_id`,
  `tenant_id`, `scope`, `ttl_seconds` 300): status 401, `mintkey:code` `unauthenticated`, zero `Enqueue` calls, no
  `token` key in the body. The no-header and empty-header tests fail before the change (200). New file
  `apps/broker/internal/api/resolve/resolve_empty_token_test.go` (package `resolve_test`):
  `TestResolve_EmptyConfiguredToken_RefusesEveryRequest` covers the fourth scenario with a store fake of its own that
  counts calls to both methods, building each request with `httptest.NewRequest` so the empty-header case sets the
  header to `""` explicitly; it must not call `resolve.HashForTest` at package level. Then in
  `apps/broker/internal/api/issue/issue.go` `Handler.ServeHTTP`, refuse with the existing
  `writeErr(w, http.StatusUnauthorized, "unauthenticated", "Service token missing or invalid")` when
  `h.mcpToken == ""` or the constant-time comparison fails; the same in
  `apps/broker/internal/api/resolve/resolve.go` `Handler.ServeHTTP` with `h.proxyToken`. Nothing else changes.

## 2. The broker refuses to start in production without its inbound tokens

- [ ] 2.1 Tests first, new file `apps/broker/internal/config/config_test.go` (package `config_test`), building
  `config.Config` values directly from their existing fields `Env`, `MCPServiceToken` and `ProxyServiceToken` (no
  environment) and reaching the new methods through
  `type serviceTokenChecker interface { MissingServiceTokens() []string; Validate() error }`, asserted on the
  `*config.Config` (`t.Fatal` when the assertion fails): `TestMissingServiceTokens_BothMissing`,
  `TestMissingServiceTokens_OneMissing`, `TestValidate_ProductionWithTokenMissing`,
  `TestValidate_ProductionWithBothTokens` and `TestValidate_DevWithTokensMissing` cover the five scenarios of the
  requirement "The broker refuses to start in production without its inbound service tokens"; the production test
  compares the error message exactly. All five fail before the change because the type assertion fails. Then
  implement `MissingServiceTokens` and `Validate` in `apps/broker/internal/config/config.go` exactly as the design's
  Interfaces give them (`strings` import), and in `apps/broker/cmd/broker/main.go` call them right after
  `config.Load()` as design D3 says.

## 3. The vault adapter registers its identities from one table

- [ ] 3.1 Tests first, new file `apps/vault-adapter/internal/server/identities_test.go` (package `server`). The tests
  build a `VaultService` with `NewVaultService(kek, st)` on `store.New(":memory:")` as `newTestGRPCServer` in
  `grpc_test.go` does, reach the two new methods through the `bootRegistrar` interface of design D7 asserted on the
  `*VaultService` (`t.Fatal` when it fails), pass a lookup built from a `map[string]string` (a missing key gives `""`,
  nil; a chosen key can give an error), and check registrations only with `ValidateServiceIdentity`; they never name
  `BootIdentities` or `IdentitySpec` and assert no scope value. Cover the requirement "The vault adapter registers its
  boot identities from one table" with `TestRegisterBootIdentities_EveryTokenSet`,
  `TestRegisterBootIdentities_IDVariableSet`, `TestRegisterBootIdentities_EmptyTokenNotRegistered`,
  `TestRegisterBootIdentities_LookupErrorRegistersNothing` and `TestRegisterBootIdentitiesFromEnv_ReadsEnvironment`
  (`t.Setenv` for the ten variables); the requirement "The vault adapter refuses to start in production without the
  proxy and admin tokens" with `TestRegisterBootIdentities_ProductionRequiresProxyAndAdmin`,
  `TestRegisterBootIdentities_ProductionWithoutOptionalTokens` and `TestRegisterBootIdentities_DevWithoutProxyToken`;
  and the requirement "An identity cannot be registered with an empty id or token" with
  `TestRegisterServiceIdentity_EmptyTokenRefused` and `TestRegisterServiceIdentity_EmptyIDRefused` (these call the
  existing method directly). The registration tests fail before the change because the type assertion fails; the two
  empty-input tests because no error is returned. Then create `apps/vault-adapter/internal/server/identities.go` with
  `IdentitySpec`, `BootIdentities` and the two methods exactly as the design's Interfaces give them, add the two checks
  to `RegisterServiceIdentity` in `apps/vault-adapter/internal/server/vault.go` (design, end of Interfaces), and in
  `apps/vault-adapter/cmd/vault-adapter/main.go` replace the five identity blocks with the call and log loop the design
  gives; keep everything else in `main()` as it is.
