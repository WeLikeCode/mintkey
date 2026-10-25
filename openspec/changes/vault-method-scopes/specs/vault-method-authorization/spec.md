# Vault method authorization

## Purpose

Which service identity and scope each vault adapter method requires, what is served without an identity, and which
scopes each identity registered at boot holds.

## ADDED Requirements

### Requirement: Every vault method requires a valid service identity, except the health methods
The vault adapter's unary interceptor SHALL serve the methods in `openMethods` (`/grpc.health.v1.Health/Check` and
`/grpc.health.v1.Health/List`) without an identity, SHALL refuse with `PERMISSION_DENIED` and the message
`method not allowed: <full method>` any method that is not a key of `methodScopes`, without running its handler, and
SHALL refuse with `PERMISSION_DENIED`, without running the handler, a call to any method of `methodScopes` that has no
metadata, no or an empty `x-mintkey-service-token`, an unregistered `x-mintkey-service-identity`, or a token that is
not that identity's. `methodScopes` SHALL NOT be written at run time.

#### Scenario: no identity on any listed method
- **WHEN** the interceptor is called directly for each key of `methodScopes` with a context that has no incoming
  metadata, and again with metadata naming a registered identity and an empty token
- **THEN** each call returns a status with code `PermissionDenied` and the handler is never called

#### Scenario: a wrong token on any listed method
- **WHEN** the interceptor is called for each key of `methodScopes` with a registered identity and a token that is not
  its own
- **THEN** each call returns `PermissionDenied` and the handler is never called

#### Scenario: an unlisted method
- **WHEN** the interceptor is called for `/mintkey.vault.v1.VaultAdapter/NotAMethod` with the metadata of an identity
  that holds every value of `methodScopes` other than `anyIdentity`
- **THEN** it returns `PermissionDenied` with the message `method not allowed: /mintkey.vault.v1.VaultAdapter/NotAMethod`
  and the handler is never called

#### Scenario: registering a service leaves the table as it was
- **WHEN** the test copies `methodScopes`, then calls `RegisterAgentSecretsVaultServer` and `RegisterSSHVaultServer` on
  a new `grpc.Server`
- **THEN** `methodScopes` still has eleven keys and equals the copy

#### Scenario: health methods need no identity
- **WHEN** the interceptor is called for `/grpc.health.v1.Health/Check` and for `/grpc.health.v1.Health/List` with no
  metadata
- **THEN** the handler is called for both and its result is returned

#### Scenario: ListVersions needs an identity
- **WHEN** a client of a server built by `buildGRPCServer` calls `ListVersions` with no metadata, then as an identity
  registered with `["vault.read"]`
- **THEN** the first call fails with `PermissionDenied` and the second succeeds

#### Scenario: ValidateServiceIdentity needs an identity but no scope
- **WHEN** `ValidateServiceIdentity` is called without metadata, and then as an identity registered with no scopes
- **THEN** the first call fails with `PermissionDenied`, and the second passes the interceptor (its handler runs and
  answers `ok: true`)

### Requirement: Each vault method requires its own scope
`methodScopes` SHALL map `GetCredential`, `ListVersions`, `GetAgentByFingerprint` and `GetHostKeyFingerprint` to
`vault.read`; `PutCredential` and `RevokeCredential` to `vault.put`; `PutAgentSecret`, `GetAgentSecret` and
`DeleteAgentSecret` to `vault.secret.put`, `vault.secret.read` and `vault.secret.delete`; `StoreHostKeyFingerprint` to
`vault.hostkey.put`; and `ValidateServiceIdentity` to `anyIdentity` (`"*"`), which requires a valid identity and no
scope. The interceptor SHALL refuse with `PERMISSION_DENIED` and the message `caller lacks required scope "<scope>"`
a valid identity that does not hold the method's scope.

#### Scenario: the table holds these scopes
- **WHEN** the test reads `methodScopes`
- **THEN** it has exactly eleven keys, and each method named above maps to the scope named for it (the three SSH methods
  under `/mintkey.vault.v1.SSHVaultAdapter/`)

#### Scenario: a read-only identity cannot write
- **WHEN** an identity registered with `["vault.read"]` calls, through the interceptor, `PutCredential`,
  `RevokeCredential`, `StoreHostKeyFingerprint` and `PutAgentSecret`
- **THEN** each is refused with `PermissionDenied` naming the missing scope, and the handler is never called

#### Scenario: an identity holding every scope is served everywhere
- **WHEN** an identity registered with every value of `methodScopes` other than `anyIdentity` calls each key of
  `methodScopes` through the interceptor
- **THEN** the handler is called for every method

### Requirement: The method table covers every method the vault serves
For the server that `buildGRPCServer` returns with an SSH store and an agent-secret store set, every unary method SHALL
be either a key of `methodScopes` or one of `/grpc.health.v1.Health/Check` and `/grpc.health.v1.Health/List` (never
both), every streaming method SHALL be `/grpc.health.v1.Health/Watch`, and every key of `methodScopes` SHALL be a
method that server serves. That server SHALL serve the health `Watch` stream without an identity and refuse every
other stream with `PERMISSION_DENIED` and `method not allowed: <full method>`, without running its handler.

#### Scenario: the served methods and the table agree
- **WHEN** the test builds that server and reads `GetServiceInfo()`
- **THEN** it holds the services `mintkey.vault.v1.VaultAdapter`, `mintkey.vault.v1.AgentSecretsVault`,
  `mintkey.vault.v1.SSHVaultAdapter` and `grpc.health.v1.Health`, and every method of each satisfies the rule above

#### Scenario: streams other than the health watch are refused
- **WHEN** the test registers, on a server returned by `buildGRPCServer`, a service `mintkey.test.v1.Streams` with one
  server-streaming method `Echo` whose handler records that it ran, serves it over `bufconn`, and with no metadata
  opens `/grpc.health.v1.Health/Watch` and `/mintkey.test.v1.Streams/Echo`
- **THEN** `Watch` delivers a `SERVING` status, and `Echo` ends with `PermissionDenied` and the message
  `method not allowed: /mintkey.test.v1.Streams/Echo` while its handler never ran

### Requirement: Each boot identity holds only the scopes its component uses
`BootIdentities` SHALL register the egress proxy (`MINTKEY_VAULT_PROXY_TOKEN`) with `["vault.read"]`, admin-api
(`MINTKEY_VAULT_ADMIN_TOKEN`) with `["vault.read", "vault.put", "vault.secret.put", "vault.secret.delete"]`, the SSH
proxy (`MINTKEY_VAULT_SSH_PROXY_TOKEN`) with `["vault.read", "vault.hostkey.put"]`, the email proxy
(`MINTKEY_VAULT_EMAIL_PROXY_TOKEN`) with `["vault.read"]`, and the MCP server (`MINTKEY_VAULT_MCP_TOKEN`) with
`["vault.secret.put", "vault.secret.read", "vault.secret.delete"]`. Every scope they name SHALL be a value of
`methodScopes`.

#### Scenario: the scopes are exactly these
- **WHEN** the test reads `BootIdentities`
- **THEN** each entry's `Scopes`, found by its `TokenVar`, equals the list above, element for element, and each scope
  is a value of `methodScopes`

#### Scenario: the proxy cannot write a credential and the admin identity can
- **WHEN** `svc.RegisterBootIdentities("dev", lookup)` registers every boot identity, with a 32-byte token each, on
  the `VaultService` of a server built by `buildGRPCServer`, the proxy
  identity calls `PutCredential`, then the admin identity calls `PutCredential` for the same tenant and service, then
  the proxy identity calls `GetCredential` for them
- **THEN** the first call fails with `PermissionDenied`, the second succeeds, and the third returns the value the admin
  identity stored

#### Scenario: the SSH proxy stores a host key but cannot write a credential
- **WHEN** on the same server the SSH proxy identity calls `StoreHostKeyFingerprint`, then `GetHostKeyFingerprint` for
  the same tenant and service, then `PutCredential`
- **THEN** the first two succeed, `GetHostKeyFingerprint` returns the stored fingerprint, and `PutCredential` fails
  with `PermissionDenied`
