# Design: broker-service-token-required

## Context

- `issue.Handler` (`apps/broker/internal/api/issue/issue.go`) holds `mcpToken`; `ServeHTTP` compares
  `r.Header.Get("X-Mintkey-Service-Token")` with it by `subtle.ConstantTimeCompare` and answers 401 through
  `writeErr(w, http.StatusUnauthorized, "unauthenticated", "Service token missing or invalid")` on a mismatch. The
  constructors are `NewHandler(iss *issuer.Issuer, mcpToken string) http.Handler`, `NewHandlerWithAudit(iss, mcpToken,
  audit AuditEnqueuer)` and `NewHandlerWithAuditAndMetrics(iss, mcpToken, audit, m *metrics.Metrics)`.
- `resolve.Handler` (`apps/broker/internal/api/resolve/resolve.go`) does the same with `proxyToken`; its constructor is
  `NewHandler(store Store, proxyToken string) http.Handler`. After the header check it parses the body, applies two
  rate limiters, then calls `store.LookupByFingerprint`.
- `config.Config` (`apps/broker/internal/config/config.go`) has `Env` (default `"dev"`), `MCPServiceToken`
  (`MINTKEY_MCP_SERVICE_TOKEN`) and `ProxyServiceToken` (`MINTKEY_PROXY_SERVICE_TOKEN`). `cmd/broker/main.go` passes
  them to the two handlers.
- The vault adapter's `main()` repeats one block five times: read `<X>_IDENTITY_ID` (default id when empty) and
  `<X>_TOKEN`; when the token is empty log a warning and skip; else call
  `svc.RegisterServiceIdentity(id, []byte(token), scopes)` and exit 1 on error. `cfg.Env` comes from
  `config.Load()` (`MINTKEY_ENV`, default `"dev"`).

## Decisions

**D1. The handler refuses, and production also refuses to start.** The handler is the one place every request
passes, so it covers development stacks and any future constructor. The start check makes a misconfigured production
broker fail loudly instead of running with an endpoint that refuses everyone. Each handler checks
`h.mcpToken == ""` (`h.proxyToken == ""` in resolve) first, then the constant-time comparison; either failing gives
today's 401. Nothing after the check runs: no body read, no rate-limit bucket, no store call, no signing, no audit
event, no metric.

**D2. The refusal looks like a wrong token.** The 401 body is the existing `unauthenticated` one, so a caller cannot
tell a missing configuration from a wrong token. The operator learns it from the start log (D3).

**D3. The broker's start rule.** `MissingServiceTokens` lists `MINTKEY_MCP_SERVICE_TOKEN` then
`MINTKEY_PROXY_SERVICE_TOKEN`, each when its field is empty. `Validate` returns an error only when `Env` is exactly
`"production"` and the list is not empty. In `main`, right after `config.Load()`:
`if err := cfg.Validate(); err != nil { log.Fatalf("broker: %v", err) }`, then for each name of
`cfg.MissingServiceTokens()`:
`log.Printf("broker: WARNING: %s is not set; the endpoint it guards refuses every request", name)`.
`log.Fatalf` exits with status 1. Only the two inbound tokens are required: `MINTKEY_BROKER_SERVICE_TOKEN` is what the
broker sends to the audit sink, and `MINTKEY_SERVICE_TOKEN` is read but not used.

**D4. The vault adapter's start rule: the proxy and admin identities are required in production.** The egress proxy
reads every credential and admin-api (or the application that embeds the data plane, with the same identity) writes
them; a vault without either serves no purpose. The SSH proxy, email proxy and MCP server identities belong to optional
components and stay optional: an empty token leaves the identity unregistered and its calls refused, as today. The
Helm chart already passes the two required tokens. (See Open questions.)

**D5. Registration is a table and two methods.** `BootIdentities` lists the five identities in today's order with
today's variable names, default ids and scopes. `(*VaultService).RegisterBootIdentities(env, lookup)` reads every
variable through `lookup`, checks the production rule, then registers; `RegisterBootIdentitiesFromEnv(env)` is the
same with the process environment, and is what `main()` calls. `main()` keeps no registration logic of its own, so the
rules are tested. `lookup` returns an error so that a source that can fail (a file) fits later without a new
signature. Both are methods on the existing `VaultService` and take and return only built-in types, so a test written
before they exist still compiles (D7).

**D6. `RegisterServiceIdentity` refuses an empty id or token.** A caller other than `RegisterBootIdentities` (tests,
`vaulttest.Start`) cannot register an identity that an empty token would match. No existing caller passes either.

**D7. How the tests reach new code.** The red step runs the new tests against the base code (every non-Python
production file is put back), so a test may not name a function, type, field or variable that only this change adds.
The tests use the existing handlers, constructors, `config.Config` fields, `NewVaultService` and
`ValidateServiceIdentity`, and reach the new methods through an interface the test file declares, with a type
assertion that calls `t.Fatal` when the method is missing:
`type serviceTokenChecker interface { MissingServiceTokens() []string; Validate() error }` (asserted on a
`*config.Config`) and `type bootRegistrar interface { RegisterBootIdentities(env string, lookup func(name string)
(string, error)) ([]string, error); RegisterBootIdentitiesFromEnv(env string) ([]string, error) }` (asserted on a
`*server.VaultService`). They never name `BootIdentities` or `IdentitySpec`. Each test is a top-level function
without `t.Run`. No scaffold is needed.

## Interfaces

`apps/broker/internal/config/config.go`:

```go
// MissingServiceTokens returns the names of the inbound service-token variables whose value is empty, in the order
// MINTKEY_MCP_SERVICE_TOKEN, MINTKEY_PROXY_SERVICE_TOKEN. It returns an empty (nil) slice when both are set.
func (c *Config) MissingServiceTokens() []string

// Validate returns nil unless c.Env == "production" and MissingServiceTokens() is not empty. Then it returns an error
// whose message is "production requires these variables to be set: " + strings.Join(MissingServiceTokens(), ", ").
func (c *Config) Validate() error
```

`apps/vault-adapter/internal/server/identities.go` (new, package `server`):

```go
// IdentitySpec describes one service identity the vault adapter registers at boot.
type IdentitySpec struct {
	IDVar                string   // variable holding the identity id
	DefaultID            string   // id used when IDVar's value is empty
	TokenVar             string   // variable holding the identity's token
	Scopes               []string // scopes the identity is registered with
	RequiredInProduction bool     // production refuses to start when TokenVar's value is empty
}

// BootIdentities lists the identities registered at boot, in registration order.
var BootIdentities = []IdentitySpec{
	{"MINTKEY_VAULT_PROXY_IDENTITY_ID", "svcid_proxy", "MINTKEY_VAULT_PROXY_TOKEN",
		[]string{"vault.read", "vault.put"}, true},
	{"MINTKEY_VAULT_ADMIN_IDENTITY_ID", "svcid_admin_api", "MINTKEY_VAULT_ADMIN_TOKEN",
		[]string{"vault.read", "vault.put", "vault.secret.put", "vault.secret.delete"}, true},
	{"MINTKEY_VAULT_SSH_PROXY_IDENTITY_ID", "svcid_ssh_proxy", "MINTKEY_VAULT_SSH_PROXY_TOKEN",
		[]string{"vault.read", "vault.put"}, false},
	{"MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID", "svcid_email_proxy", "MINTKEY_VAULT_EMAIL_PROXY_TOKEN",
		[]string{"vault.read"}, false},
	{"MINTKEY_VAULT_MCP_IDENTITY_ID", "svcid_mcp", "MINTKEY_VAULT_MCP_TOKEN",
		[]string{"vault.secret.put", "vault.secret.read", "vault.secret.delete"}, false},
}

// RegisterBootIdentities registers the identities of BootIdentities on v, reading every variable through lookup.
// It returns the TokenVar of each identity left unregistered because its token is empty, in table order (nil when
// all five are registered).
func (v *VaultService) RegisterBootIdentities(env string, lookup func(name string) (string, error)) (unset []string, err error)

// RegisterBootIdentitiesFromEnv is RegisterBootIdentities with a lookup that returns os.Getenv(name), nil.
func (v *VaultService) RegisterBootIdentitiesFromEnv(env string) (unset []string, err error)
```

`RegisterBootIdentities`, in this order:
1. For each spec, `lookup(spec.IDVar)` then `lookup(spec.TokenVar)`. On the first error return
   `nil, fmt.Errorf("read %s: %w", name, err)` (`name` being the variable looked up) having registered nothing. An
   empty id value means `spec.DefaultID`.
2. When `env == "production"`, collect each `TokenVar` with `RequiredInProduction` and an empty value, in table order.
   If any, return `nil` and an error whose message is
   `"production requires these variables to be set: " + strings.Join(names, ", ")`, having registered nothing.
3. For each spec with a non-empty token, `v.RegisterServiceIdentity(id, []byte(token), spec.Scopes)`; on error return
   `nil, err` (identities registered before it stay registered; the process exits). A spec with an empty token is not
   registered and its `TokenVar` goes into `unset`.

`vault-adapter` `main()` replaces the five blocks with:

```go
unset, err := svc.RegisterBootIdentitiesFromEnv(cfg.Env)
if err != nil {
	fmt.Fprintf(os.Stderr, "vault-adapter: fatal: %v\n", err)
	os.Exit(1)
}
for _, name := range unset {
	log.Printf("vault-adapter: WARNING: %s is not set; that identity is not registered and its calls fail with PERMISSION_DENIED", name)
}
log.Printf("vault-adapter: registered %d of %d boot identities", len(server.BootIdentities)-len(unset), len(server.BootIdentities))
```

`VaultService.RegisterServiceIdentity(identityID string, token []byte, scopes []string) error` returns
`fmt.Errorf("RegisterServiceIdentity: empty identity id")` when `identityID == ""` and
`fmt.Errorf("RegisterServiceIdentity(%s): empty token", identityID)` when `len(token) == 0`, before any hashing. Its
other behaviour is unchanged.

## For the changes that follow

- `vault-service-identity-fast-check` rewrites how `RegisterServiceIdentity` stores the token and keeps D6's refusal.
- `vault-method-scopes` edits only the `Scopes` values of `BootIdentities`, and its tests call
  `RegisterBootIdentities` directly (it exists at their base).
- `service-token-files` makes `RegisterBootIdentitiesFromEnv` read through `svcid.FromEnv`, and changes how
  `config.Load` reads the tokens; `MissingServiceTokens` and `Validate` keep their contract.
- No test of this change asserts a scope value, so the next changes need not edit these tests.

## Failure cases

- Configured token empty, request with no header, an empty header or any value: 401 `unauthenticated`; nothing else
  runs.
- Configured token set: unchanged (a missing or wrong header 401, the right one proceeds). Covered by the existing
  `issue_test.go::TestIssue_MissingOrWrongToken_Returns401`, `issue_test.go::TestIssue_ValidRequest_Returns200WithJWT`,
  `resolve_test.go::TestMissingServiceToken`, `resolve_test.go::TestWrongServiceToken`, `resolve_test.go::TestHappyPath`.
- `MINTKEY_ENV` unset, `dev` or any value other than `production`: the broker and the vault adapter start; the
  broker warns per missing token; the vault adapter warns per unregistered identity.
- Production with a required token missing: the broker exits 1 with
  `broker: production requires these variables to be set: <names>`; the vault adapter exits 1 with
  `vault-adapter: fatal: production requires these variables to be set: <names>`. No log line contains a token.
- A lookup error (not possible with the environment lookup of this change): the vault adapter exits 1 naming the
  error; nothing is registered.

## Open questions

- D4 picks the proxy and admin identities as the ones production requires. An owner may prefer a configurable list
  (for a stack that runs the SSH proxy as its main component). Recorded here as a decision taken unattended.
