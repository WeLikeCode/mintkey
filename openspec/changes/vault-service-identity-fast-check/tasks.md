# Tasks: vault-service-identity-fast-check

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Run the touched
module's tests (`go test ./... -short`), `go vet ./...` and `golangci-lint run` in `apps/vault-adapter`,
`apps/proxy-plugin` or `apps/broker`. New test files must not redeclare names that already exist in their test package
(in `server`: `newTestGRPCServer`, `newTestGRPCServerWithAuth`, `mdWithIdentity`, `outCtx`, `contains`, `bufSize`; in
the proxy's `vault_test`: `seedTestCredential`, `devProxyToken`, `devProxyIdentityID`; in `resolve_test`: `proxyToken`,
`mockStore`, `post`, `reqBody`, `errCode`, `newHandler`). No test may need Docker or a network beyond `127.0.0.1`.
Every new test compiles against the base code (design, Testing notes): it uses only functions, types and fields that
exist before the change, reaches the one new method (`Close`) through an interface the test file declares with a type
assertion that calls `t.Fatal` when it is missing, and is a top-level function without `t.Run`.

## 1. The vault adapter verifies identities with HMAC-SHA-256

- [x] 1.1 Tests first, new file `apps/vault-adapter/internal/server/identity_check_test.go` (package `server`), with a
  `VaultService` built by `NewVaultService(kek, st)` on `store.New(":memory:")`. Cover the requirement "Verifying a
  service identity uses a keyed hash, not a memory-hard one" with `TestValidateServiceIdentity_AllocatesUnderOneMiB`
  and `TestRegisterServiceIdentity_AllocatesUnderOneMiB` (read `runtime.MemStats.TotalAlloc` with
  `runtime.ReadMemStats` right before and right after the measured calls; assert the difference is below `1 << 20`);
  and the requirement "Verification outcomes stay as they were" with `TestValidateServiceIdentity_RightToken`,
  `TestValidateServiceIdentity_OtherTokensRefused`, `TestValidateServiceIdentity_UnknownIdentity` and
  `TestRegisterServiceIdentity_ScopesAreCopied`. The two allocation tests and the copy test fail before the change
  (Argon2id allocates 64 MiB per call; the slice is stored as given). Then in
  `apps/vault-adapter/internal/server/vault.go` apply design D1: add `identityKey` to `VaultService` and fill it in
  `NewVaultService`; replace `serviceIdentity`'s fields with `tokenMAC` and `scopes`; add `tokenMAC`; rewrite the
  bodies of `RegisterServiceIdentity` (keeping the empty id and empty token checks first) and
  `ValidateServiceIdentity`; delete `argon2Params`, `defaultArgon2Params` and the `argon2` import; update the package
  comment's sentence on Argon2id to say HMAC-SHA-256 under a per-process key. Imports added: `crypto/hmac`,
  `crypto/sha256`, `slices`.

## 2. The proxy reuses one connection to the vault

- [x] 2.1 Tests first, new file `apps/proxy-plugin/internal/vault/client_conn_test.go` (package `vault_test`). It
  defines a listener type wrapping `net.Listener` whose `Accept` counts successful accepts in an `atomic.Int32`, and a
  fake server embedding `vaultv1.UnimplementedVaultAdapterServer` whose `GetCredential` records the two metadata values
  of each call (under a mutex) and returns `&vaultv1.GetCredentialResponse{AuthScheme:
  vaultv1.AuthScheme_AUTH_SCHEME_BEARER_TOKEN, Value: []byte("conn-test-value"), ReturnedKeyVersion: 1}`. Each test
  listens on `127.0.0.1:0`, serves with `grpc.NewServer()` and `vaultv1.RegisterVaultAdapterServer`, and stops the
  server in `t.Cleanup`. Cover the requirement "The proxy reuses one connection to the vault" with
  `TestClient_SequentialCallsShareOneConnection`, `TestClient_ConcurrentCallsShareOneConnection`,
  `TestClient_RecoversAfterVaultRestart` (after `Stop`, listen again on the same address, retrying the listen for up to
  2 s; then retry `GetCredential` every 100 ms for up to 10 s) and `TestClient_ClosedClientDoesNotConnect`. The close test
  reaches `Close` through `type closer interface { Close() error }` asserted on the `*vault.Client` (`t.Fatal` when it
  fails). The two sharing tests fail before the change (one accept per call), the close test because the type
  assertion fails. Then in `apps/proxy-plugin/internal/vault/client.go` apply design D3 and D4 (fields
  `mu`, `conn`, `closed`; `connection()`; `errClientClosed = errors.New("vault: client closed")`; `Close()`), keeping
  `NewClient`'s signature, the metadata, the 60 s deadline, `grpc.WaitForReady(false)` and the error texts; update the
  file's comments that say the client dials per call. In `apps/proxy-plugin/cmd/proxy-plugin/main.go` add the deferred
  `Close` the design gives. The existing tests in `client_test.go` and `xmodule_integration_test.go` stay as they are.

## 3. The broker computes its dummy hash on first use

- [x] 3.1 Tests first, new file `apps/broker/internal/api/resolve/dummy_hash_lazy_test.go` (package `resolve_test`):
  `TestMain(m *testing.M)` reads `runtime.MemStats.TotalAlloc` into a package variable, then `os.Exit(m.Run())`;
  `TestPackageInit_AllocatesUnder32MiB` asserts that value is below `32 << 20`; and
  `TestUnknownFingerprint_StillRefusedTwice` covers the second scenario of the requirement "The broker computes its
  constant-time dummy hash on first use" with a store fake of its own that finds nothing and the handler built with a
  non-empty service token. The first test fails before the change (64 MiB allocated at init). Then in
  `apps/broker/internal/api/resolve/resolve.go` make `dummyHash` the `sync.OnceValue` of design D6 and use
  `dummyHash()` in `Handler.ServeHTTP` (the `sync` import is already there, for the token buckets).
