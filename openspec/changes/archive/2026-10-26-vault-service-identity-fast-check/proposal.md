# Verify vault service identities with a keyed hash, and reuse the proxy's vault connection

## Why

Every gRPC call to the vault adapter goes through `scopeInterceptor` (`apps/vault-adapter/internal/server/grpc.go`),
which calls `VaultService.ValidateServiceIdentity` (`apps/vault-adapter/internal/server/vault.go`). That function
derives an Argon2id hash of the presented token with 64 MiB of memory, one pass and four lanes, and runs the same
derivation on a dummy salt when the identity is unknown; `RegisterServiceIdentity` runs it once per identity at boot.
So each call in flight holds 64 MiB whether or not its caller is registered or its token right, and the memory the
vault needs grows with the number of concurrent calls. The compose files run the vault adapter with `mem_limit: 128m`,
which two concurrent calls already exceed (64 MiB each, plus the process). The egress proxy calls `GetCredential` once
per proxied request, so the vault's capacity bounds the proxy's.

A memory-hard hash protects low-entropy secrets, such as passwords, whose stored hash might be copied and guessed
offline. Service tokens are random shared secrets provisioned per deployment, and their hashes live only in the vault
adapter's memory. For them a keyed hash under a key generated at boot (HMAC-SHA-256) gives the same constant-time
comparison in microseconds and with no memory cost.

Two smaller per-call and per-start costs sit on the same path:

- `vault.Client.GetCredential` in the proxy (`apps/proxy-plugin/internal/vault/client.go`) creates and closes a new
  gRPC client connection on every call, so every proxied request pays a TCP and HTTP/2 handshake to the vault.
- The broker computes an Argon2id hash for its constant-time "unknown key" path at package initialisation
  (`dummyHash` in `apps/broker/internal/api/resolve/resolve.go`): 64 MiB at every start, whether or not a classical
  API key is ever resolved.

## What Changes

- `VaultService` keeps a 32-byte key from `crypto/rand`, made in `NewVaultService`. `RegisterServiceIdentity` stores
  `HMAC-SHA-256(key, token)`; `ValidateServiceIdentity` computes the same for the presented token and compares with
  `hmac.Equal`; for an unknown identity it compares against a zero MAC of the same length. Argon2id is no longer used
  for service identities; the outcomes of every validation stay as they are.
- The proxy's `vault.Client` creates one `*grpc.ClientConn` on first use and reuses it for every call, with a reconnect
  backoff capped at 2 s, and gains `Close() error`. `NewClient(address, serviceToken, serviceIdentityID string) *Client`
  keeps its signature. The proxy's `main` closes the client on shutdown.
- The broker's dummy hash is computed on first use.

## Capabilities

### New Capabilities
- `vault-identity-verification`: the cost and outcomes of verifying a service identity in the vault adapter, the
  proxy's connection to the vault, and the broker's start-up cost for its constant-time path.

## Impact

- Changed: `apps/vault-adapter/internal/server/vault.go` (`VaultService`, `NewVaultService`, `RegisterServiceIdentity`,
  `ValidateServiceIdentity`, `serviceIdentity`; the Argon2id parameters go),
  `apps/proxy-plugin/internal/vault/client.go` (`Client`, `GetCredential`, new `Close`),
  `apps/proxy-plugin/cmd/proxy-plugin/main.go` (one deferred `Close`),
  `apps/broker/internal/api/resolve/resolve.go` (`dummyHash`).
- New tests: `apps/vault-adapter/internal/server/identity_check_test.go`,
  `apps/proxy-plugin/internal/vault/client_conn_test.go`, `apps/broker/internal/api/resolve/dummy_hash_lazy_test.go`.
- Callers: no API change. A wrong or unknown token is refused as before; it now costs the vault microseconds.
- Operators: the vault adapter's memory no longer grows with concurrent calls. A raised memory limit or `GOMEMLIMIT`
  set only to absorb the identity check can be returned to the stock value after this change; nothing requires it.
- The stack-level check (300 proxied calls at concurrency 16 against the vault at its stock 128m limit with no 5xx and
  peak RSS under 100 MiB, and 16 parallel callers with wrong tokens for 60 s without a restart) needs Docker, which the
  gates do not have: a person runs it after the merge. The gates prove the per-call allocation bound it rests on.
- Out of scope: the broker's verification of classical API keys against their stored Argon2id hashes (they are made by
  admin-api, and the proxy caches a resolution for 60 s); the SSH and email proxies' per-call
  connections (lower volume); which methods need which scope (change `vault-method-scopes`).

## Issue Intake (remediation gate)

1. **Problem statement**: verifying a service identity costs 64 MiB of memory per call in the vault adapter, for any
   caller.
2. **User-visible symptom**: under concurrent proxied requests the vault adapter exceeds its memory limit and restarts;
   the proxy answers 502 while it is down.
3. **Expected behavior**: the identity check costs no memory-hard hash; the vault's memory does not grow with
   concurrent callers; the proxy reuses one connection to the vault.
4. **Evidence**: `defaultArgon2Params` (64 MiB) used by `ValidateServiceIdentity` on every interceptor call; the
   compose limit of 128m; `grpc.NewClient` and `conn.Close()` inside the proxy's `GetCredential`; the package-level
   `dummyHash` in the broker.
5. **Scope**: the three changes under What Changes.
6. **Risk**: low. The comparison stays constant-time and its outcomes unchanged; the key never leaves the process.
