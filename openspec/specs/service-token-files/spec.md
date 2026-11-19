# service-token-files Specification

## Purpose
How the Go services read their service tokens and vault identity tokens from a file named by `<NAME>_FILE` or from
the variable `<NAME>`, and what they do when a secret file cannot be read.

## Requirements

### Requirement: A secret can come from a file named by NAME_FILE
Every token variable named in this specification SHALL be read by one rule, implemented once in `svcid.FromEnv(name)`
(package `packages/go/svcid`): when `<NAME>_FILE` is not empty and `<NAME>` is empty, the value is the content of the
file `<NAME>_FILE` names, with trailing `\r` and `\n` characters removed and nothing else changed; when `<NAME>_FILE`
is empty, the value is `<NAME>`, which may be empty. Both not empty SHALL be an error whose message is
`<NAME> and <NAME>_FILE are both set; set only one`; a file that cannot be read SHALL be an error whose message starts
with `<NAME>_FILE: cannot read` and contains the path. No error message SHALL contain the value of `<NAME>` or the
file's content. The SSH proxy's `config.Load("")` with `MINTKEY_VAULT_SSH_PROXY_TOKEN` is where the scenarios observe
the rule.

#### Scenario: the variable alone
- **WHEN** `MINTKEY_VAULT_SSH_PROXY_TOKEN` is `from-env` and `MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE` is empty
- **THEN** the SSH proxy's `Load("")` returns no error and `VaultToken` `from-env`

#### Scenario: the file alone
- **WHEN** `MINTKEY_VAULT_SSH_PROXY_TOKEN` is empty and `MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE` names a file holding
  `from-file`
- **THEN** `Load("")` returns no error and `VaultToken` `from-file`

#### Scenario: trailing line ends are removed
- **WHEN** the file holds `from-file\n`, then `from-file\r\n`, then ` from file \n\n`, then `line1\nline2\n`
- **THEN** `VaultToken` is `from-file`, `from-file`, ` from file ` and `line1\nline2`

#### Scenario: a file that holds only a newline
- **WHEN** the file holds `\n` only
- **THEN** `Load("")` returns no error and `VaultToken` `""`

#### Scenario: both are set
- **WHEN** `MINTKEY_VAULT_SSH_PROXY_TOKEN` is `env-secret-value` and `MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE` names a file
  holding `file-secret-value`
- **THEN** `Load("")` returns an error whose message is
  `MINTKEY_VAULT_SSH_PROXY_TOKEN and MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE are both set; set only one`, which contains
  neither value

#### Scenario: the file cannot be read
- **WHEN** `MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE` names a path in a temporary directory that does not exist
- **THEN** `Load("")` returns an error whose message starts with `MINTKEY_VAULT_SSH_PROXY_TOKEN_FILE: cannot read` and
  contains the path

### Requirement: The broker and the egress proxy read their tokens from files too
The broker's `config.Load()` SHALL read `MINTKEY_SERVICE_TOKEN`, `MINTKEY_PROXY_SERVICE_TOKEN`,
`MINTKEY_MCP_SERVICE_TOKEN` and `MINTKEY_BROKER_SERVICE_TOKEN`, and the egress proxy's `config.Load()` SHALL read
`MINTKEY_PROXY_SERVICE_TOKEN` and `MINTKEY_VAULT_PROXY_TOKEN`, by the rule above. `(*Config).SecretErr()` SHALL return
the join of the read errors, or nil when there is none. (Each service's `main` checks `SecretErr()` right after
`config.Load()` and exits with status 1 logging it: design, Interfaces.)

#### Scenario: broker tokens from files
- **WHEN** each of the broker's four `<NAME>_FILE` variables names a file holding a distinct value and the four
  `<NAME>` variables are empty
- **THEN** `config.Load()` returns those values in `ServiceToken`, `ProxyServiceToken`, `MCPServiceToken` and
  `BrokerSvcToken`, and `SecretErr()` returns nil

#### Scenario: broker tokens from variables, as before
- **WHEN** the four `<NAME>` variables hold distinct values and no `<NAME>_FILE` variable is set
- **THEN** `config.Load()` returns those values in the four fields and `SecretErr()` returns nil

#### Scenario: an unreadable broker token file
- **WHEN** `MINTKEY_MCP_SERVICE_TOKEN_FILE` names a missing file
- **THEN** `config.Load()` returns `MCPServiceToken` `""` and `SecretErr()` returns an error whose message contains
  `MINTKEY_MCP_SERVICE_TOKEN_FILE`

#### Scenario: egress proxy tokens from files
- **WHEN** `MINTKEY_PROXY_SERVICE_TOKEN_FILE` and `MINTKEY_VAULT_PROXY_TOKEN_FILE` name files holding distinct values
  and the two `<NAME>` variables are empty
- **THEN** the proxy's `config.Load()` returns them in `ProxyServiceToken` and `VaultIdentityToken`, and `SecretErr()`
  returns nil

#### Scenario: an egress proxy token set twice
- **WHEN** `MINTKEY_VAULT_PROXY_TOKEN` and `MINTKEY_VAULT_PROXY_TOKEN_FILE` are both set
- **THEN** the proxy's `SecretErr()` returns an error whose message contains
  `MINTKEY_VAULT_PROXY_TOKEN and MINTKEY_VAULT_PROXY_TOKEN_FILE are both set`

### Requirement: The vault adapter reads its identity variables from files too
`(*VaultService).RegisterBootIdentitiesFromEnv(env)` SHALL read every identity id and token variable of
`BootIdentities` by the rule above, so that a read error leaves every identity unregistered. (The vault adapter's
`main` already registers its identities through it.)

#### Scenario: an identity token from a file
- **WHEN** `MINTKEY_VAULT_ADMIN_TOKEN_FILE` names a file holding a 32-byte token followed by `\n`, the other token and
  id variables and their `_FILE` forms are empty, and `RegisterBootIdentitiesFromEnv("dev")` runs
- **THEN** it returns no error, and `ValidateServiceIdentity` accepts `svcid_admin_api` with the 32-byte token

#### Scenario: an unreadable identity token file
- **WHEN** `MINTKEY_VAULT_PROXY_TOKEN_FILE` names a missing file and `MINTKEY_VAULT_ADMIN_TOKEN` holds a token
- **THEN** `RegisterBootIdentitiesFromEnv("dev")` returns an error whose message contains
  `MINTKEY_VAULT_PROXY_TOKEN_FILE`, and `ValidateServiceIdentity` refuses `svcid_admin_api` with its token

### Requirement: The email proxy reads its tokens from files too
The email proxy's `config.Load()` SHALL read `MINTKEY_VAULT_EMAIL_PROXY_TOKEN` and `MINTKEY_EMAIL_PROXY_SERVICE_TOKEN`
by the rule above and return the read error when there is one, and SHALL keep returning
`<NAME> is required but not set` for a token whose value is empty.

#### Scenario: email proxy tokens from files
- **WHEN** `MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID` is `id_test`, and `MINTKEY_VAULT_EMAIL_PROXY_TOKEN_FILE` and
  `MINTKEY_EMAIL_PROXY_SERVICE_TOKEN_FILE` name files holding `vault-file-token` and `svc-file-token`, the two `<NAME>`
  variables being empty
- **THEN** the email proxy's `Load()` returns no error, `VaultToken` `vault-file-token` and `EmailProxyServiceToken`
  `svc-file-token`

#### Scenario: an unreadable email proxy token file
- **WHEN** `MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID` and `MINTKEY_VAULT_EMAIL_PROXY_TOKEN` are set and
  `MINTKEY_EMAIL_PROXY_SERVICE_TOKEN_FILE` names a missing file
- **THEN** the email proxy's `Load()` returns an error whose message contains `MINTKEY_EMAIL_PROXY_SERVICE_TOKEN_FILE`

#### Scenario: an email proxy token file that holds only a newline
- **WHEN** `MINTKEY_VAULT_EMAIL_PROXY_TOKEN_FILE` names a file holding `\n` and the service token is set
- **THEN** the email proxy's `Load()` returns the error `MINTKEY_VAULT_EMAIL_PROXY_TOKEN is required but not set`
