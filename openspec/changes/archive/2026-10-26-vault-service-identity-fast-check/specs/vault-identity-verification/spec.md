# Vault identity verification

## Purpose

What verifying a service identity costs the vault adapter and what it answers, how the egress proxy connects to the
vault, and what the broker's constant-time path costs at start.

## ADDED Requirements

### Requirement: Verifying a service identity uses a keyed hash, not a memory-hard one
`VaultService` SHALL verify service-identity tokens with HMAC-SHA-256 under a 32-byte key drawn from `crypto/rand` in
`NewVaultService` (kept only in the struct: design D1). `RegisterServiceIdentity` and
`ValidateServiceIdentity` SHALL NOT run Argon2id or any other memory-hard function. Thirty calls of
`ValidateServiceIdentity` SHALL allocate less than 1 MiB in total, whether the token is right, wrong, or presented for
an unknown identity; five calls of `RegisterServiceIdentity` SHALL allocate less than 1 MiB in total.

#### Scenario: validations allocate little
- **WHEN** an identity `svcid_cost` is registered with a 32-byte token and `ValidateServiceIdentity` is called ten
  times with the right token, ten times with a wrong 32-byte token and ten times for the unknown identity
  `svcid_absent`
- **THEN** `runtime.MemStats.TotalAlloc` grew by less than 1 MiB (1048576 bytes) across the thirty calls

#### Scenario: registrations allocate little
- **WHEN** `RegisterServiceIdentity` is called five times, for five ids, each with a 32-byte token
- **THEN** `runtime.MemStats.TotalAlloc` grew by less than 1 MiB across the five calls, and each call returned `nil`

### Requirement: Verification outcomes stay as they were
`ValidateServiceIdentity(ctx, id, token)` SHALL return the scopes registered for `id` and `true` exactly when `id` is
registered and `token` equals its registered token byte for byte, and `nil, false` otherwise. The returned scopes
SHALL NOT change when the caller of `RegisterServiceIdentity` later modifies the slice it passed.

#### Scenario: the right token
- **WHEN** `svcid_a` is registered with token `T` and scopes `["vault.read", "vault.put"]`, and
  `ValidateServiceIdentity(ctx, "svcid_a", T)` is called
- **THEN** it returns `["vault.read", "vault.put"]` and `true`

#### Scenario: tokens that are not the registered one
- **WHEN** `ValidateServiceIdentity` is called for `svcid_a` with a token equal to `T` except in its last byte, with
  `T` plus one byte, with `T` minus its last byte, and with an empty token
- **THEN** each call returns `nil` and `false`

#### Scenario: an unknown identity
- **WHEN** `ValidateServiceIdentity(ctx, "svcid_absent", T)` is called
- **THEN** it returns `nil` and `false`

#### Scenario: the registered scopes are a copy
- **WHEN** `svcid_b` is registered with a slice `s` = `["vault.read"]` and the test then sets `s[0] = "vault.put"`
- **THEN** `ValidateServiceIdentity` for `svcid_b` with its token returns `["vault.read"]` and `true`

### Requirement: The proxy reuses one connection to the vault
The proxy's `vault.Client` SHALL NOT dial per call: any number of `GetCredential` calls, sequential or concurrent,
made while the vault adapter stays up SHALL use one accepted connection. It SHALL send `x-mintkey-service-identity` and `x-mintkey-service-token` on every call, SHALL reconnect by
itself after the vault adapter restarts, and SHALL provide `Close() error`, after which `GetCredential` returns an
error containing `vault: client closed` without connecting.

#### Scenario: sequential calls share one connection
- **WHEN** a client made by `vault.NewClient(addr, "conn-test-token", "svcid_conn_test")` calls `GetCredential` five
  times against a gRPC server whose listener counts accepted connections
- **THEN** every call returns the server's value, the listener accepted exactly one connection, and the server saw
  `x-mintkey-service-identity: svcid_conn_test` and `x-mintkey-service-token: conn-test-token` on all five calls

#### Scenario: concurrent calls share one connection
- **WHEN** a new client makes sixteen `GetCredential` calls at once from sixteen goroutines
- **THEN** all sixteen succeed and the listener accepted exactly one connection

#### Scenario: the client recovers after the vault restarts
- **WHEN** a client has made one successful call, the server is stopped, and a new server is started on the same
  address
- **THEN** a `GetCredential` call retried every 100 ms succeeds within 10 s

#### Scenario: a closed client does not connect
- **WHEN** a client that made one successful call is closed with `Close()` and then calls `GetCredential`
- **THEN** `Close()` returned `nil`, the call returns an error containing `vault: client closed`, the listener's
  accept count did not grow, and a second `Close()` returns `nil`

### Requirement: The broker computes its constant-time dummy hash on first use
The broker's `resolve` package SHALL NOT compute an Argon2id hash during package initialisation; the dummy hash for an
unknown fingerprint SHALL be computed on the first request that needs it and reused afterwards.

#### Scenario: initialising the package allocates little
- **WHEN** the `resolve_test` test binary starts and `TestMain` reads `runtime.MemStats.TotalAlloc` before any test
  runs
- **THEN** the value is below 32 MiB (33554432 bytes)

#### Scenario: the unknown-fingerprint path still answers the same
- **WHEN** a resolve request with a valid service token names a fingerprint the store does not know, twice
- **THEN** both responses are 401 with `mintkey:code` `api_key_invalid`
