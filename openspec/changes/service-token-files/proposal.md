# Service tokens can be read from files

## Why

The vault adapter reads its key encryption key from a file (`MINTKEY_VAULT_KEK_FILE`) and the broker reads its signing
key from a file (`MINTKEY_BROKER_SIGNING_KEY_FILE`), but every service token and vault identity token of the Go
services can only come from an environment variable (`os.Getenv` in `apps/broker/internal/config/config.go`,
`apps/proxy-plugin/internal/config/config.go`, `apps/ssh-proxy/internal/config/config.go`,
`apps/email-proxy/internal/config/config.go`, and the vault adapter's identity registration). An environment variable
is shown by `docker inspect`, is inherited by every child process, and is readable in the process environment by
anything running as the same user in the container. Docker secrets and Kubernetes secret volumes deliver secrets as
files; a credential broker should be able to take its own secrets that way too, with the common `<NAME>_FILE`
convention.

## What Changes

- New function `svcid.FromEnv(name string) (string, error)` in the existing package `packages/go/svcid`: when
  `<name>_FILE` is set it returns that file's content without trailing `\r` and `\n`; otherwise the value of `<name>`.
  Both set, or an unreadable file, is an error that names the variables and never contains a secret.
- Every Go service reads its service tokens and vault identity tokens through it:
  - broker: `MINTKEY_SERVICE_TOKEN`, `MINTKEY_PROXY_SERVICE_TOKEN`, `MINTKEY_MCP_SERVICE_TOKEN`,
    `MINTKEY_BROKER_SERVICE_TOKEN`;
  - egress proxy: `MINTKEY_PROXY_SERVICE_TOKEN`, `MINTKEY_VAULT_PROXY_TOKEN`;
  - vault adapter: every variable `RegisterBootIdentitiesFromEnv` reads (the five identity tokens and their ids);
  - SSH proxy: `MINTKEY_VAULT_SSH_PROXY_TOKEN`;
  - email proxy: `MINTKEY_VAULT_EMAIL_PROXY_TOKEN`, `MINTKEY_EMAIL_PROXY_SERVICE_TOKEN`.
- A service whose secret file cannot be read, or that has both forms of one variable, exits at start with a message
  naming the variable, in every mode.
- The broker's and the egress proxy's `Config` gain a `SecretErr() error` method reporting what `Load` could not read;
  their `Load()` signatures stay as they are.

## Capabilities

### New Capabilities
- `service-token-files`: how the Go services read service tokens and vault identity tokens from `<NAME>_FILE` or
  `<NAME>`, and what they do when a file cannot be read.

## Impact

- Changed: `packages/go/svcid` (new file `fromenv.go`), `apps/broker/internal/config/config.go` (`Load`, `Config`),
  `apps/broker/cmd/broker/main.go`, `apps/proxy-plugin/internal/config/config.go` (`Load`, `Config`),
  `apps/proxy-plugin/cmd/proxy-plugin/main.go`, `apps/vault-adapter/internal/server/identities.go` (`RegisterBootIdentitiesFromEnv`), `apps/ssh-proxy/internal/config/config.go` and `apps/email-proxy/internal/config/config.go`
  (`Load`).
- New tests (`svcid.FromEnv` is tested through the loaders that use it: design D7):
  `apps/broker/internal/config/config_files_test.go`,
  `apps/proxy-plugin/internal/config/config_files_test.go`, `apps/vault-adapter/internal/server/identities_files_test.go`,
  `apps/ssh-proxy/internal/config/config_files_test.go`, `apps/email-proxy/internal/config/config_files_test.go`.
- Operators (migration): nothing is required. A deployment that sets only `<NAME>` behaves as today. To use a file,
  set `<NAME>_FILE` to its path and unset `<NAME>`; a service with both refuses to start. A file holding only a
  newline gives an empty token, which the rules of change `broker-service-token-required` treat as unset. The compose
  files and the Helm chart keep passing variables; switching them to files is an operator's choice, outside this unit
  (`infra/**` is not edited by it). `scripts/mintkey-doctor.sh` checks the vault tokens with `printenv`, so on an
  install that uses `<NAME>_FILE` it reports them as not set; teaching it the file form is a follow-up.
- Out of scope: the Python services (admin-api, MCP server), which read their tokens at import; the HashiCorp AppRole
  secret of the vault's HashiCorp backend; hot rotation of a token file (each value is read once at start).

## Issue Intake (remediation gate)

1. **Problem statement**: service tokens and vault identity tokens can only be passed as environment variables.
2. **User-visible symptom**: an operator who keeps secrets in files (Docker or Kubernetes secrets) must still copy every
   service token into the environment.
3. **Expected behavior**: each of these variables also accepts `<NAME>_FILE`; an unreadable file stops the service at
   start with a message naming the variable.
4. **Evidence**: the `os.Getenv` reads in the files named under Why; `kek.Load` and `keyloader.LoadKey` as the existing
   file-based pattern.
5. **Scope**: the changes under What Changes.
6. **Risk**: low. The variable-only path is unchanged; the new path fails at start, never at request time.
