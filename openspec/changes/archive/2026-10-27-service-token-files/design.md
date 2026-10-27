# Design: service-token-files

## Context

- `packages/go/svcid` (root module `github.com/mintkey/mintkey`) holds `Client`, which reads a service token from a
  file and trims trailing `\r\n` (`strings.TrimRight(string(data), "\r\n")`). No service imports it yet. Every Go
  service's Dockerfile copies `packages/go/`, and `go.work` makes the root module visible to every app module, as it
  already does for `packages/go/auditq` and `packages/go/otelinit`.
- The token reads today:
  - broker `config.Load()`: `ServiceToken`, `ProxyServiceToken`, `MCPServiceToken` with `os.Getenv`, `BrokerSvcToken`
    with `os.Getenv`; `Load() *Config`, called only by `cmd/broker/main.go`.
  - egress proxy `config.Load()`: `ProxyServiceToken` and `VaultIdentityToken` with `getEnv(key, "")`;
    `Load() *Config`, called by `cmd/proxy-plugin/main.go` and `config_test.go::TestLoadAudEnforcementDefaults`.
  - vault adapter `main()`: `svc.RegisterBootIdentitiesFromEnv(cfg.Env)`, which reads with `os.Getenv`.
  - SSH proxy `config.Load(configPath string) (*Config, error)`: `if v := os.Getenv("MINTKEY_VAULT_SSH_PROXY_TOKEN");
    v != "" { cfg.VaultToken = v }`.
  - email proxy `config.Load() (*Config, error)`: `MINTKEY_VAULT_EMAIL_PROXY_TOKEN` and
    `MINTKEY_EMAIL_PROXY_SERVICE_TOKEN` with `os.Getenv`, each returning `"<NAME> is required but not set"` when empty.

## Assumed from earlier changes

- `broker-service-token-required` added `server.BootIdentities` and two `VaultService` methods:
  `RegisterBootIdentities(env string, lookup func(name string) (string, error)) (unset []string, err error)`, which
  reads every id and token variable through `lookup` and returns `fmt.Errorf("read %s: %w", name, err)` on a lookup
  error, registering nothing; and `RegisterBootIdentitiesFromEnv(env string) (unset []string, err error)`, the same
  with `os.Getenv`, which `main()` calls. The base of this unit has them (the plan orders this change after that one),
  so the tests call them directly. It also added
  `(*Config).MissingServiceTokens()` and `(*Config).Validate()` to the broker's config and calls them in
  `cmd/broker/main.go` right after `config.Load()`; this change keeps both and puts its own check before them.
- `vault-method-scopes` changed only the scopes in `BootIdentities`; this change does not touch them.
- `vault-service-identity-fast-check` touched none of the files of this change.

## Decisions

**D1. One reader, the common convention.** `svcid.FromEnv(name)` lets every service read a secret the same way:
`<name>_FILE` names a file whose content is the value, else `<name>` holds it. A variable whose value is the empty
string counts as not set, as `getEnv` treats it today.

**D2. Both forms set is an error.** Picking one silently would hide a configuration mistake (an old value left in the
environment); the service refuses to start and names both variables.

**D3. Trailing line ends are trimmed, nothing else.** Files written by `echo` or editors end with `\n` or `\r\n`;
`strings.TrimRight(content, "\r\n")` removes them, as `svcid.Client.Token` does. Spaces and inner line ends are kept.
An empty result is returned as `""` with no error; the callers' own rules for an empty token apply (the broker and
the vault adapter: change `broker-service-token-required`; the email proxy: "is required but not set").

**D4. Errors name variables and paths, never values.** The messages are
`"<name> and <name>_FILE are both set; set only one"` and `"<name>_FILE: cannot read %q: <os error>"` (the path is
quoted with `%q`; the os error is wrapped with `%w`). No message contains the value of `<name>` or the file's content.

**D5. Read once at start.** Each value is read when the service loads its configuration; a changed file is picked up
at the next start. Hot rotation is out of scope (`svcid.Client.Token` keeps that behaviour for any future caller).

**D6. `Load` keeps its signature where tests or other changes call it.** The broker's and the egress proxy's
`Load() *Config` stay; each `Config` gains an unexported field `secretErr error`, set by `Load` to `errors.Join` of every
read error in read order (nil when there is none), and a method `SecretErr() error` that returns it; `main` exits on it
before anything else. The SSH and email proxies' `Load` already return an error and return the read error directly.

**D7. How the tests reach new code.** The red step runs the new tests against the base code (every non-Python
production file is put back), so a test may not name a function, field or package that only this change adds:
`svcid.FromEnv` is not called by any test, and is tested through the services' existing loaders
(`config.Load()` of the broker and the egress proxy, `Load(configPath)` of the SSH proxy, `Load()` of the email proxy)
and through `RegisterBootIdentitiesFromEnv`. The new `SecretErr` method is reached through
`type secretErrer interface { SecretErr() error }` asserted on the `*config.Config` (`t.Fatal` when it fails). Each
test is a top-level function without `t.Run`. No scaffold is needed.

## Interfaces

`packages/go/svcid/fromenv.go` (new):

```go
// FromEnv returns the secret named name. When the environment variable name+"_FILE" is set (not empty), it returns
// the content of that file with trailing '\r' and '\n' characters removed. Otherwise it returns the value of name,
// which may be "". It returns an error when both variables are set or when the file cannot be read.
func FromEnv(name string) (string, error)
```

`apps/broker/internal/config/config.go`:

```go
type Config struct {
	// ... existing fields unchanged ...
	secretErr error // errors.Join of the errors reading MINTKEY_SERVICE_TOKEN, MINTKEY_PROXY_SERVICE_TOKEN,
	// MINTKEY_MCP_SERVICE_TOKEN and MINTKEY_BROKER_SERVICE_TOKEN through svcid.FromEnv, in that order; nil when none
}

// SecretErr returns the error of reading the service tokens in Load, or nil.
func (c *Config) SecretErr() error
```

`Load` sets the four token fields from `svcid.FromEnv` (a field is `""` when its read failed) and `secretErr`.
`cmd/broker/main.go`, right after `cfg := config.Load()` and before `cfg.Validate()`:
`if err := cfg.SecretErr(); err != nil { log.Fatalf("broker: %v", err) }`.

`apps/proxy-plugin/internal/config/config.go`: the same `secretErr` field and `SecretErr() error` method, covering
`MINTKEY_PROXY_SERVICE_TOKEN` then `MINTKEY_VAULT_PROXY_TOKEN`. `cmd/proxy-plugin/main.go`, right after
`cfg := config.Load()`: `if err := cfg.SecretErr(); err != nil { log.Fatalf("proxy-plugin: %v", err) }`.

`apps/vault-adapter/internal/server/identities.go`: `RegisterBootIdentitiesFromEnv` passes `svcid.FromEnv` to
`RegisterBootIdentities` in place of its `os.Getenv` lookup; nothing else in the file and nothing in `main()` changes.

`apps/ssh-proxy/internal/config/config.go` `Load`: `v, err := svcid.FromEnv("MINTKEY_VAULT_SSH_PROXY_TOKEN")`; on error
`return nil, err`; when `v != ""`, `cfg.VaultToken = v`.

`apps/email-proxy/internal/config/config.go` `Load`: the same for `MINTKEY_VAULT_EMAIL_PROXY_TOKEN` (into `VaultToken`)
and `MINTKEY_EMAIL_PROXY_SERVICE_TOKEN` (into `EmailProxyServiceToken`), returning the read error; an empty value keeps its
existing `"<NAME> is required but not set"` error.

## Failure cases

- Neither form set: as today (the broker and vault rules for an empty token, the email proxy's required error, the SSH
  proxy's default).
- `<NAME>_FILE` names a missing or unreadable file: the service exits at start; the message contains `<NAME>_FILE` and
  the path.
- Both forms set: the service exits at start; the message names both.
- The file holds only line ends: an empty value (D3).
- The vault adapter: a read error stops it before any identity is registered (`RegisterBootIdentities` reads every
  variable first).

## Open questions

- None that block. The Python services keep reading their tokens from the environment.
