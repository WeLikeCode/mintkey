# Design: vault-service-identity-fast-check

## Context

- `vault.go` (package `server` of `apps/vault-adapter`): `serviceIdentity{tokenHash, salt []byte; scopes []string}`,
  `VaultService{...; identityMu sync.RWMutex; identities map[string]*serviceIdentity}`, `defaultArgon2Params` (64 MiB,
  t=1, 4 lanes, 32-byte key). `RegisterServiceIdentity` draws a 16-byte salt and stores Argon2id(token, salt);
  `ValidateServiceIdentity(ctx context.Context, identityID string, token []byte) (scopes []string, ok bool)` looks the
  identity up under the read lock, runs Argon2id on a zero salt when it is unknown (and returns `nil, false`), else
  recomputes and compares with `subtle.ConstantTimeCompare`. The package's only use of `golang.org/x/crypto/argon2` is
  this; `golang.org/x/crypto` stays in `go.mod` for `ssh`.
- Callers of `ValidateServiceIdentity`: `scopeInterceptor` (every unary call), `grpcVaultServer.ValidateServiceIdentity`,
  `sshVaultServer.requireScope`, and tests.
- `vault.Client` (`apps/proxy-plugin/internal/vault/client.go`): fields `address`, `serviceToken`,
  `serviceIdentityID`; `GetCredential(ctx, req GetCredentialRequest) (*GetCredentialResponse, error)` attaches the
  `x-mintkey-service-token` and `x-mintkey-service-identity` metadata, applies a 60 s deadline, calls
  `grpc.NewClient(c.address, insecure)`, defers `conn.Close()`, and calls `GetCredential` with
  `grpc.WaitForReady(false)`. Its callers are `proxyHandler.ServeHTTP` and `proxyHandler.handleClassicalKey` in
  `apps/proxy-plugin/cmd/proxy-plugin/main.go`, which builds the client once with
  `vault.NewClient(cfg.VaultAddrGRPC, cfg.VaultIdentityToken, cfg.VaultIdentityID)`.
- `resolve.go` (broker): `var dummyHash = hashPassword("dummy_constant_time_placeholder")`, used once in
  `Handler.ServeHTTP` as `hashToCheck := dummyHash` when the fingerprint is unknown.

## Assumed from earlier changes

`broker-service-token-required` made `RegisterServiceIdentity` return an error for an empty identity id or an empty
token, before any hashing. This change keeps both checks as they are and first in the function. It also added
`apps/vault-adapter/internal/server/identities.go` and `apps/broker/internal/api/resolve/resolve_empty_token_test.go`;
neither is touched here.

## Decisions

**D1. HMAC-SHA-256 under a per-process key.** `NewVaultService` fills `identityKey` with 32 bytes from
`crypto/rand.Read` (panic on an error, as `newCredentialID` does). The key lives only in the struct: never logged,
never returned, never written. `serviceIdentity` becomes `{tokenMAC []byte; scopes []string}`; the salt and the
Argon2id parameters go, with the `argon2` import. `RegisterServiceIdentity` stores `v.tokenMAC(token)` and a copy of
`scopes` (`slices.Clone`), so a caller that later edits its slice does not change the grant.
`ValidateServiceIdentity` computes `candidate := v.tokenMAC(token)` before it looks at whether the identity is known,
then compares with `hmac.Equal` against the stored MAC, or against `make([]byte, sha256.Size)` (all zero) for an
unknown identity, so both paths do the same work. The read lock and the returned values are as today.

**D2. Why a keyed hash is enough.** The stored value must not reveal the token, and the comparison must not leak it by
timing. HMAC under a random key that never leaves the process satisfies both; a memory-hard function only adds
protection against offline guessing of a low-entropy secret, which a random service token is not and a hash held in
memory does not face. Restarting the process draws a new key, and `RegisterBootIdentities` registers the identities
again.

**D3. One connection per proxy client.** `vault.Client` gets `mu sync.Mutex`, `conn *grpc.ClientConn` and `closed bool`.
`connection()` holds `mu`, returns `errClientClosed` when closed, else creates `c.conn` once with
`grpc.NewClient(c.address, grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithConnectParams(...))` and
returns it. `grpc.NewClient` does not dial; the first RPC connects, and concurrent RPCs share the HTTP/2 connection.
`GetCredential` keeps its metadata, its 60 s deadline, `grpc.WaitForReady(false)` and its error wrapping
(`vault: GetCredential(<tenant>/<service>): <err>`); it no longer closes the connection. A gRPC client connection
reconnects on its own after the vault restarts.

**D4. A bounded reconnect backoff.** The default gRPC backoff grows to 120 s, so after a long vault outage the proxy
could keep failing fast for up to two minutes after the vault is back. The connect parameters are
`grpc.ConnectParams{Backoff: backoff.Config{BaseDelay: 100 * time.Millisecond, Multiplier: 1.6, Jitter: 0.2,
MaxDelay: 2 * time.Second}, MinConnectTimeout: 5 * time.Second}` (`google.golang.org/grpc/backoff`).

**D5. A connection is not a credential cache.** The client still fetches the credential from the vault on every call
and holds no plaintext between calls (ADR-0014.4); `TestVaultClient_HasNoCache` keeps passing because no field is
named `cache` or `Cache`.

**D6. The broker's dummy hash on first use.** `var dummyHash = sync.OnceValue(func() string { return
hashPassword("dummy_constant_time_placeholder") })`, and the handler uses `dummyHash()`. The first unknown-fingerprint
request computes it once; every later one reuses it, as today. The unknown and known paths still both run one
`verifyPassword`.

## Interfaces

`apps/vault-adapter/internal/server/vault.go`:

```go
type serviceIdentity struct {
	tokenMAC []byte   // HMAC-SHA-256(VaultService.identityKey, token)
	scopes   []string // a copy of the registered scopes
}

// VaultService gains: identityKey []byte // 32 random bytes made by NewVaultService; never logged or returned

// tokenMAC returns HMAC-SHA-256(v.identityKey, token).
func (v *VaultService) tokenMAC(token []byte) []byte

// Signatures unchanged:
func NewVaultService(kek []byte, s store.Backend, dekCache ...*cache.DEKCache) *VaultService
func (v *VaultService) RegisterServiceIdentity(identityID string, token []byte, scopes []string) error
func (v *VaultService) ValidateServiceIdentity(ctx context.Context, identityID string, token []byte) (scopes []string, ok bool)
```

`apps/proxy-plugin/internal/vault/client.go`:

```go
// NewClient is unchanged: func NewClient(address, serviceToken, serviceIdentityID string) *Client

// Close closes the client's connection, if one was made. Later calls to GetCredential return an error that
// contains "vault: client closed" without dialling. Close is safe to call more than once and returns nil then.
func (c *Client) Close() error
```

`apps/proxy-plugin/cmd/proxy-plugin/main.go`: right after `vaultClient := vault.NewClient(...)`, add
`defer func() { _ = vaultClient.Close() }()`.

## Failure cases

- Wrong token, unknown identity, empty token: `nil, false`, as today; the interceptor answers `PERMISSION_DENIED`.
- `crypto/rand` fails in `NewVaultService`: panic at start (the process cannot run safely without a key).
- The vault is unreachable on a proxy call: `GetCredential` returns an error (the proxy answers 502, as today); the
  connection is kept and reconnects with the D4 backoff.
- The vault restarts: the next call after it is back succeeds within the backoff (at most about 2 s plus jitter).
- `GetCredential` after `Close`: an error containing `vault: client closed`; no connection is made.
- `grpc.NewClient` rejects the target (a malformed address): every call returns
  `vault: create client for <address>: <err>`, as today; nothing is cached so a later call tries again.

## Testing notes

- The red step runs the new tests against the base code (every non-Python production file is put back), so the tests
  use only existing API: `NewVaultService`, `RegisterServiceIdentity`, `ValidateServiceIdentity`, `vault.NewClient`,
  `Client.GetCredential`, the generated `vaultv1` server registration, `resolve.NewHandler`. The new `Client.Close` is
  reached through `type closer interface { Close() error }` and a type assertion that calls `t.Fatal` when it is
  missing. Each test is a top-level function without `t.Run`. No scaffold is needed.

- The allocation tests read `runtime.MemStats.TotalAlloc` (cumulative, unaffected by garbage collection) with
  `runtime.ReadMemStats` before and after the measured calls. One Argon2id derivation allocates 64 MiB, so a bound of
  1 MiB for 30 validations separates the two implementations by more than three orders of magnitude.
- The broker test records `TotalAlloc` in `TestMain`, before any test runs, so no other test can disturb it. No test
  file of package `resolve_test` may call `resolve.HashForTest` at package level (none does).
- The proxy tests run a real gRPC server on `127.0.0.1:0` (loopback only, as `xmodule_integration_test.go` does) behind a
  listener that counts accepted connections.

## Open questions

- The stack-level acceptance (concurrency 16 at the stock 128m limit, wrong-token callers) is a person's check after
  the merge, since the gates have no Docker.
