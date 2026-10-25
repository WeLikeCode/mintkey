# Tasks: service-token-files

Each task writes its tests first and sees them fail for the reason it names, then changes the code. Run
`go test ./... -short`, `go vet ./...` and `golangci-lint run` in every module the task touches (and in the repository
root for `packages/go/svcid`). Tests set variables with `t.Setenv` (also setting to `""` every other token and id
variable of the same service, and its `_FILE` form) and write secret files under `t.TempDir()` with mode `0600`; none
uses `t.Parallel` or `t.Run`. Every new test compiles against the base code (design D7): no test calls `svcid.FromEnv`
or names a new field; the new `SecretErr` method is reached through
`type secretErrer interface { SecretErr() error }` asserted on the `*config.Config` (`t.Fatal` when it fails). New test
files must not redeclare names that already exist in their test package.

## 1. The rule, svcid.FromEnv, and the SSH proxy

- [ ] 1.1 Tests first, new file `apps/ssh-proxy/internal/config/config_files_test.go` (package `config`, calling the
  existing `Load("")`): `TestLoad_SSHProxyTokenFromVariable`, `TestLoad_SSHProxyTokenFromFile`,
  `TestLoad_SSHProxyTokenFileTrailingLineEndsRemoved`, `TestLoad_SSHProxyTokenFileWithOnlyANewline`,
  `TestLoad_SSHProxyTokenSetTwice` and `TestLoad_UnreadableSSHProxyTokenFile` cover the six scenarios of the
  requirement "A secret can come from a file named by NAME_FILE"; the file, trailing-line-end, set-twice and unreadable
  tests fail before the change (the `_FILE` variable is ignored). Then create `packages/go/svcid/fromenv.go` with `FromEnv` as the design's Interfaces and
  D1 to D4 give it (`fmt`, `os`, `strings`), and in `apps/ssh-proxy/internal/config/config.go` `Load` read
  `MINTKEY_VAULT_SSH_PROXY_TOKEN` with it as the design gives; every other line of `Load` stays.

## 2. The broker and the egress proxy

- [ ] 2.1 Tests first, new file `apps/broker/internal/config/config_files_test.go` (package `config_test`):
  `TestLoad_BrokerTokensFromFiles`, `TestLoad_BrokerTokensFromVariables` and `TestLoad_UnreadableBrokerTokenFile` cover
  the first three scenarios of the requirement "The broker and the egress proxy read their tokens from files too". New
  file `apps/proxy-plugin/internal/config/config_files_test.go` (package `config_test`):
  `TestLoad_ProxyTokensFromFiles` and `TestLoad_ProxyTokenSetTwice` cover the last two. Each calls the existing
  `config.Load()`, reads the existing token fields, and reaches `SecretErr()` through the `secretErrer` interface; all
  but `TestLoad_BrokerTokensFromVariables` fail before the change (the type assertion fails, or the `_FILE` variable is
  ignored). Then in `apps/broker/internal/config/config.go` and `apps/proxy-plugin/internal/config/config.go` read the
  tokens with `svcid.FromEnv` and add `secretErr` and `SecretErr()` by design D6; in `apps/broker/cmd/broker/main.go`
  and `apps/proxy-plugin/cmd/proxy-plugin/main.go` add the `SecretErr()` check the design gives, right after
  `config.Load()`. `apps/proxy-plugin/internal/config/config_test.go::TestLoadAudEnforcementDefaults` stays as it is.

## 3. The vault adapter

- [ ] 3.1 Tests first, new file `apps/vault-adapter/internal/server/identities_files_test.go` (package `server`):
  `TestRegisterBootIdentitiesFromEnv_TokenFromFile` and `TestRegisterBootIdentitiesFromEnv_UnreadableTokenFile` cover
  the requirement "The vault adapter reads its identity variables from files too", calling the existing
  `svc.RegisterBootIdentitiesFromEnv("dev")` on a `VaultService` built with `NewVaultService(kek, st)` on
  `store.New(":memory:")`, after setting every id and token variable of `BootIdentities` and their `_FILE` forms with
  `t.Setenv`. Both fail before the change (the `_FILE` variable is ignored). Then in
  `apps/vault-adapter/internal/server/identities.go` make `RegisterBootIdentitiesFromEnv` pass `svcid.FromEnv` to
  `RegisterBootIdentities` (import `github.com/mintkey/mintkey/packages/go/svcid`); nothing else changes.

## 4. The email proxy

- [ ] 4.1 Tests first, new file `apps/email-proxy/internal/config/config_files_test.go` (package `config`, calling the
  existing `Load()`): `TestLoad_EmailProxyTokensFromFiles`, `TestLoad_UnreadableEmailProxyTokenFile` and
  `TestLoad_EmailProxyTokenFileWithOnlyANewline` cover the requirement "The email proxy reads its tokens from files
  too"; the first two fail before the change (the `_FILE` variables are ignored). Then in
  `apps/email-proxy/internal/config/config.go` replace the two token reads as the design's Interfaces give them; every
  other line of `Load` stays.
