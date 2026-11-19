# service-token-enforcement Specification

## Purpose
How the broker's internal endpoints and the vault adapter's boot identities behave when a service token is not
configured: an endpoint without its token refuses every request, and production refuses to start without the tokens
it relies on.

## Requirements

### Requirement: A broker endpoint with no configured service token refuses every request
`issue.Handler` and `resolve.Handler` SHALL answer every request with status 401 and the body
`{"mintkey:code": "unauthenticated", "title": "Service token missing or invalid"}` when the token they were constructed
with is the empty string, whether the request has no `X-Mintkey-Service-Token` header, an empty one, or any other
value. In that case `issue.Handler` SHALL sign no token and enqueue no audit event, and `resolve.Handler` SHALL NOT
call its store.

#### Scenario: issue with no configured token and no header
- **WHEN** `issue.NewHandlerWithAudit(iss, "", audit)` serves a valid `POST /v1/issue` body without the
  `X-Mintkey-Service-Token` header
- **THEN** the response is 401 with `mintkey:code` `unauthenticated`, and `audit` received no event

#### Scenario: issue with no configured token and an empty header
- **WHEN** the same handler serves the same body with `X-Mintkey-Service-Token` set to the empty string
- **THEN** the response is 401 with `mintkey:code` `unauthenticated`, and `audit` received no event

#### Scenario: issue with no configured token and a non-empty header
- **WHEN** the same handler serves the same body with `X-Mintkey-Service-Token: some-token`
- **THEN** the response is 401 with `mintkey:code` `unauthenticated`, and the body holds no `token` field

#### Scenario: resolve with no configured token
- **WHEN** `resolve.NewHandler(store, "")` serves a valid `POST /v1/api-keys/resolve` body, once without the header,
  once with an empty header and once with `X-Mintkey-Service-Token: some-token`
- **THEN** each response is 401 with `mintkey:code` `unauthenticated`, and the store's `LookupByFingerprint` and
  `AgentActive` were never called

### Requirement: The broker refuses to start in production without its inbound service tokens
`(*config.Config).MissingServiceTokens()` SHALL return the names of the empty variables among
`MINTKEY_MCP_SERVICE_TOKEN` (field `MCPServiceToken`) and `MINTKEY_PROXY_SERVICE_TOKEN` (field `ProxyServiceToken`),
in that order. `(*config.Config).Validate()` SHALL return an error with the message
`production requires these variables to be set: <names joined by ", ">` when `Env` is `production` and that list is
not empty, and `nil` otherwise. (The broker's `main` calls `Validate` right after `config.Load()`, exits with status
1 logging its error, and otherwise logs one warning per missing variable: design D3.)

#### Scenario: both tokens missing
- **WHEN** a `Config` has `MCPServiceToken` and `ProxyServiceToken` empty
- **THEN** `MissingServiceTokens()` returns `["MINTKEY_MCP_SERVICE_TOKEN", "MINTKEY_PROXY_SERVICE_TOKEN"]`

#### Scenario: one token missing
- **WHEN** a `Config` has `MCPServiceToken` set and `ProxyServiceToken` empty
- **THEN** `MissingServiceTokens()` returns `["MINTKEY_PROXY_SERVICE_TOKEN"]`

#### Scenario: production with a token missing
- **WHEN** a `Config` with `Env` `production` has both tokens empty
- **THEN** `Validate()` returns an error whose message is
  `production requires these variables to be set: MINTKEY_MCP_SERVICE_TOKEN, MINTKEY_PROXY_SERVICE_TOKEN`

#### Scenario: production with both tokens set
- **WHEN** a `Config` with `Env` `production` has both tokens set
- **THEN** `Validate()` returns `nil` and `MissingServiceTokens()` is empty

#### Scenario: development with tokens missing
- **WHEN** a `Config` with `Env` `dev` has both tokens empty
- **THEN** `Validate()` returns `nil`

### Requirement: The vault adapter registers its boot identities from one table
`(*VaultService).RegisterBootIdentities(env, lookup)` SHALL read each `IDVar` and `TokenVar` of `BootIdentities`
through `lookup`, use `DefaultID` when the id value is empty, register each identity whose token is not empty with
`RegisterServiceIdentity(id, token, Scopes)`, and return the `TokenVar` of every identity whose token was empty, in
table order. When `lookup` returns an error it SHALL return an error wrapping it and register nothing.
`BootIdentities` SHALL list the five identities with the variable names and default ids of the design.
`(*VaultService).RegisterBootIdentitiesFromEnv(env)` SHALL do the same with the process environment. (The vault
adapter's `main` registers its identities only through `RegisterBootIdentitiesFromEnv`: design D5.)

#### Scenario: every token set
- **WHEN** `RegisterBootIdentities("dev", lookup)` runs with a lookup that gives `MINTKEY_VAULT_PROXY_TOKEN`,
  `MINTKEY_VAULT_ADMIN_TOKEN`, `MINTKEY_VAULT_SSH_PROXY_TOKEN`, `MINTKEY_VAULT_EMAIL_PROXY_TOKEN` and
  `MINTKEY_VAULT_MCP_TOKEN` distinct 32-byte tokens and every other variable `""`
- **THEN** it returns no error and an empty list, and `ValidateServiceIdentity` accepts `svcid_proxy`,
  `svcid_admin_api`, `svcid_ssh_proxy`, `svcid_email_proxy` and `svcid_mcp`, each with its own token and with no
  other

#### Scenario: an id variable is set
- **WHEN** the lookup also gives `MINTKEY_VAULT_PROXY_IDENTITY_ID` the value `svcid_proxy_custom`
- **THEN** `ValidateServiceIdentity` accepts `svcid_proxy_custom` with the proxy token and refuses `svcid_proxy`

#### Scenario: an empty token leaves its identity unregistered
- **WHEN** the lookup gives every token except `MINTKEY_VAULT_MCP_TOKEN`, env `dev`
- **THEN** no error is returned, the list is `["MINTKEY_VAULT_MCP_TOKEN"]`, the other four ids are accepted with
  their tokens, and `ValidateServiceIdentity` refuses `svcid_mcp` with any token

#### Scenario: a lookup error registers nothing
- **WHEN** the lookup returns an error `e` for `MINTKEY_VAULT_ADMIN_TOKEN` and values for every other token
- **THEN** `RegisterBootIdentities` returns a nil list and an error `err` with `errors.Is(err, e)`, and
  `ValidateServiceIdentity` refuses `svcid_proxy` with its token

#### Scenario: the environment variant
- **WHEN** `MINTKEY_VAULT_PROXY_TOKEN` and `MINTKEY_VAULT_ADMIN_TOKEN` hold 32-byte tokens in the process environment,
  the other three token variables and the five id variables are `""`, and `RegisterBootIdentitiesFromEnv("dev")` runs
- **THEN** it returns no error and `["MINTKEY_VAULT_SSH_PROXY_TOKEN", "MINTKEY_VAULT_EMAIL_PROXY_TOKEN",
  "MINTKEY_VAULT_MCP_TOKEN"]`, and `ValidateServiceIdentity` accepts `svcid_proxy` and `svcid_admin_api` with their
  tokens

### Requirement: The vault adapter refuses to start in production without the proxy and admin tokens
When `env` is `production` and the token of an identity with `RequiredInProduction` is empty, `RegisterBootIdentities`
SHALL return an error with the message `production requires these variables to be set: <names joined by ", ">`, naming
every such `TokenVar` in table order, and SHALL register nothing. In `BootIdentities` only `MINTKEY_VAULT_PROXY_TOKEN`
and `MINTKEY_VAULT_ADMIN_TOKEN` are `RequiredInProduction`. (The vault adapter's `main` exits with status 1 and prints
the error when registration fails.)

#### Scenario: production without the proxy and admin tokens
- **WHEN** `RegisterBootIdentities("production", lookup)` runs with a lookup that gives only the SSH proxy, email proxy
  and MCP tokens
- **THEN** it returns a nil list and an error whose message is
  `production requires these variables to be set: MINTKEY_VAULT_PROXY_TOKEN, MINTKEY_VAULT_ADMIN_TOKEN`, and
  `ValidateServiceIdentity` refuses `svcid_mcp` with the MCP token

#### Scenario: production without the optional tokens
- **WHEN** env is `production` and the lookup gives only the proxy and admin tokens
- **THEN** no error is returned, the list is `["MINTKEY_VAULT_SSH_PROXY_TOKEN", "MINTKEY_VAULT_EMAIL_PROXY_TOKEN",
  "MINTKEY_VAULT_MCP_TOKEN"]`, and the proxy and admin ids are accepted with their tokens

#### Scenario: development without the proxy token
- **WHEN** env is `dev` and the lookup gives every token except `MINTKEY_VAULT_PROXY_TOKEN`
- **THEN** no error is returned and the list is `["MINTKEY_VAULT_PROXY_TOKEN"]`

### Requirement: An identity cannot be registered with an empty id or token
`VaultService.RegisterServiceIdentity` SHALL return an error and register nothing when the identity id is empty or the
token has length zero.

#### Scenario: empty token
- **WHEN** `RegisterServiceIdentity("svcid_x", []byte{}, []string{"vault.read"})` is called
- **THEN** it returns an error whose message contains `empty token`, and `ValidateServiceIdentity` refuses `svcid_x`
  with an empty token and with any other token

#### Scenario: empty id
- **WHEN** `RegisterServiceIdentity("", []byte("a-32-byte-token-for-the-test-xx!"), []string{"vault.read"})` is called
- **THEN** it returns an error whose message contains `empty identity id`, and `ValidateServiceIdentity("", that token)`
  is refused
