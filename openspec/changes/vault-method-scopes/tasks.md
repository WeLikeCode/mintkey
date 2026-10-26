# Tasks: vault-method-scopes

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Run
`go test ./... -short`, `go vet ./...` and `golangci-lint run` in `apps/vault-adapter`, and `go test ./... -short` in
`apps/proxy-plugin` (its `xmodule_integration_test.go` serves through `ListenAndServe`). New test files are in package
`server` and must not redeclare names that already exist there (`newTestGRPCServer`, `newTestGRPCServerWithAuth`,
`mdWithIdentity`, `outCtx`, `contains`, `bufSize`, `sshBufSize`, `fakeSSHStore`, `newFakeAgentSecretStore`); they may
use `fakeSSHStore` and `newFakeAgentSecretStore`. Build a `VaultService` with `NewVaultService(kek, st)` on
`store.New(":memory:")`. A test that calls an interceptor directly passes a handler that records whether it ran and a
context made with `metadata.NewIncomingContext`. Every new test compiles against the base code (design D10): it reaches
`buildGRPCServer` through the `grpcServerBuilder` interface asserted on `New(kek)` (`t.Fatal` when the assertion fails),
never names `streamScopeInterceptor`, `openMethods`, `openStreams` or `anyIdentity`, and is a top-level function
without `t.Run`.

## 1. One closed method table, refused by default

- [x] 1.1 Tests first, new file `apps/vault-adapter/internal/server/method_scopes_test.go`. Cover the requirement
  "Every vault method requires a valid service identity, except the health methods" with
  `TestScopeInterceptor_NoIdentityRefusedOnEveryListedMethod`, `TestScopeInterceptor_WrongTokenRefusedOnEveryListedMethod`,
  `TestScopeInterceptor_UnlistedMethodRefused`, `TestMethodTable_NotWrittenByRegistration`,
  `TestScopeInterceptor_HealthMethodsNeedNoIdentity` (both call `scopeInterceptor` directly),
  `TestListVersions_RequiresIdentity` and `TestValidateServiceIdentity_RequiresIdentityButNoScope` (these two serve the
  server from `buildGRPCServer` over `bufconn` and call it with `vaultv1.NewVaultAdapterClient`); the requirement "Each
  vault method requires its own scope" with `TestMethodTable_ScopePerMethod`,
  `TestScopeInterceptor_ReadOnlyIdentityCannotWrite` and `TestScopeInterceptor_FullIdentityServedEverywhere`; and the
  requirement "The method table covers every method the vault serves" with `TestMethodTable_CoversEveryServedMethod`
  (the server from `buildGRPCServer` on
  `New(kek).WithSSHStore(&fakeSSHStore{agents: map[string]*store.AgentSSHRecord{}, hostKeys: map[string]string{}}).WithAgentSecretStore(newFakeAgentSecretStore())`,
  read with `GetServiceInfo()`) and `TestBuiltServer_OnlyHealthWatchStreams` (as the stream scenario says: the extra
  service is registered with `RegisterService` and a `grpc.ServiceDesc` whose `HandlerType` is `(*interface{})(nil)`,
  before `Serve`; the client opens `Echo` with `conn.NewStream` and reads with `RecvMsg(new(emptypb.Empty))`, and
  `Watch` with `grpc_health_v1.NewHealthClient(conn).Watch`). Before the change the unlisted-method, not-written,
  scope-per-method, `RevokeCredential` and `StoreHostKeyFingerprint` read-only cases fail by assertion, and every test
  that needs `buildGRPCServer` fails because the type assertion fails. Also change two existing tests in place:
  `apps/vault-adapter/internal/server/grpc_test.go::TestGRPCValidateServiceIdentity_MissingToken` now expects
  `codes.PermissionDenied` (update its comment), and
  `apps/vault-adapter/internal/server/grpc_ssh_test.go::newTestSSHGRPCServer` builds its server with
  `grpc.NewServer(grpc.UnaryInterceptor(scopeInterceptor(svc)))` and registers `svcid_ssh_proxy` with
  `[]string{"vault.read", "vault.hostkey.put"}` (design D9). With that helper,
  `apps/vault-adapter/internal/server/grpc_ssh_test.go::TestSSHVault_StoreHostKeyFingerprint_HappyPath` and
  `apps/vault-adapter/internal/server/grpc_ssh_test.go::TestSSHVault_StoreHostKeyFingerprint_MissingArgs` fail at red
  (the handler still requires `vault.put`); that is the expected red: keep the helper as described and let green make
  them pass, without editing those two tests. Then, in `apps/vault-adapter/internal/server/grpc.go`:
  replace `methodScopes` with the design's map literal and its comment, add `openMethods`, `openStreams`,
  `anyIdentity`, rewrite `scopeInterceptor`'s body by design D2 and D3 (update its doc comment, which says unlisted
  methods are allowed), add `streamScopeInterceptor` (D5) and `buildGRPCServer`, and make `ListenAndServe` call
  `buildGRPCServer`. In `apps/vault-adapter/internal/server/grpc_agent_secrets.go` delete the three `methodScopes`
  writes in `RegisterAgentSecretsVaultServer` and their comment. In `apps/vault-adapter/internal/server/grpc_ssh.go`
  delete the `requireScope` calls from `GetAgentByFingerprint`, `GetHostKeyFingerprint` and
  `StoreHostKeyFingerprint`, delete `requireScope` and the `metadata` import if nothing else uses it, and update the file
  comment and method comments to say the interceptor checks the scope (`vault.read`, `vault.hostkey.put`).

## 2. Each boot identity holds only the scopes it uses

- [ ] 2.1 Tests first, new file `apps/vault-adapter/internal/server/identity_scopes_test.go`. Cover the requirement
  "Each boot identity holds only the scopes its component uses" with `TestBootIdentities_LeastPrivilegeScopes` (reads
  `BootIdentities`, which exists at the base: design D10), `TestProxyIdentity_CannotPutCredential_AdminCan` and
  `TestSSHProxyIdentity_StoresHostKeyButCannotPutCredential`. The two server tests register identities with
  `svc.RegisterBootIdentities("dev", lookup)`, where `lookup` gives each `TokenVar` a distinct 32-byte test token and
  each id variable `""`, and serve the server that `buildGRPCServer` returns for
  `New(kek).WithSSHStore(&fakeSSHStore{agents: map[string]*store.AgentSSHRecord{}, hostKeys: map[string]string{}})`
  over `bufconn`, reached through the `grpcServerBuilder` interface; the SSH calls use `conn.Invoke` with
  `grpc.ForceCodec(sshvault.JSONCodec{})` and the `sshvault` request and response types, as `grpc_ssh_test.go` does. The
  least-privilege test fails before the change by assertion (the proxy and the SSH proxy hold `vault.put`); the two
  server tests fail because the type assertion fails until task 1.1's green, and then by assertion until this task's
  green. Then in `apps/vault-adapter/internal/server/identities.go` set the proxy entry's `Scopes` to
  `[]string{"vault.read"}` and the SSH proxy entry's to `[]string{"vault.read", "vault.hostkey.put"}`; nothing else in
  the file changes.
