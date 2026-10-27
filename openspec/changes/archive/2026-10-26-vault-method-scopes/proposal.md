# Every vault method requires an identity and its own scope, and each component holds only the scopes it uses

## Why

The vault adapter's gRPC interceptor (`scopeInterceptor` in `apps/vault-adapter/internal/server/grpc.go`) checks the
caller's service identity only for the methods listed in `methodScopes`: `GetCredential` (`vault.read`) and
`PutCredential` (`vault.put`). `RegisterAgentSecretsVaultServer` adds the three agent-secret methods to the same map
when the agent-secret store is configured. Every other method is served without the interceptor's check:
`ListVersions` (credential ids, key versions, auth schemes and creation times for a tenant and service),
`RevokeCredential` (not implemented yet), and `ValidateServiceIdentity` and the three SSH methods, which check the
token in their own handlers. Whether a method is protected therefore depends on code in three files, and a method
added later is served to any caller unless someone remembers to list it. A credential store should refuse by default:
every method names the scope it needs, and a method nobody listed is refused.

The identities also hold more than their components use. The egress proxy's identity is registered with `vault.read`
and `vault.put`, but the proxy only reads credentials. The SSH proxy's identity holds `vault.put` because
`StoreHostKeyFingerprint` (trust on first use) requires it, and the same scope also allows `PutCredential`. A component
that only reads credentials should not be able to change a stored credential or its target, which would outlast a
restart of that component; only the control plane (admin-api, or an application that embeds the data plane and uses
the admin identity) writes them.

## What Changes

- One closed table in `grpc.go` gives every unary method the vault serves its required scope; `ValidateServiceIdentity`
  needs a valid identity with any scopes. Only the gRPC health methods (`Check`, `List`, and the `Watch` stream) are
  served without an identity, because container and Kubernetes probes call them.
- The interceptor refuses a method that is not in the table with `PERMISSION_DENIED`, before it looks at the token. A
  new stream interceptor refuses every streaming method except the health `Watch`.
- `ListenAndServe` builds its server through a new `buildGRPCServer`, so a test enumerates exactly the methods served
  and fails when one has no entry.
- New scope `vault.hostkey.put` for `StoreHostKeyFingerprint`. `GetAgentByFingerprint`, `GetHostKeyFingerprint` and
  `ListVersions` need `vault.read`; `RevokeCredential` needs `vault.put`.
- `RegisterAgentSecretsVaultServer` no longer writes the table, and the SSH handlers lose their own token check
  (`requireScope`): the interceptor is the one place that authorises a call.
- `BootIdentities` scopes: proxy `[vault.read]`; SSH proxy `[vault.read, vault.hostkey.put]`; admin-api, email proxy
  and MCP server unchanged.
- `ValidateServiceIdentity` without an identity now answers `PERMISSION_DENIED` (today `UNAUTHENTICATED`), as every
  other method does.

## Capabilities

### New Capabilities
- `vault-method-authorization`: which identity and scope each vault method requires, what is served without one, and
  which scopes each boot identity holds.

## Impact

- Changed: `apps/vault-adapter/internal/server/grpc.go` (`methodScopes`, `scopeInterceptor`, `ListenAndServe`; new
  `streamScopeInterceptor`, `buildGRPCServer`, `openMethods`, `openStreams`, `anyIdentity`),
  `apps/vault-adapter/internal/server/grpc_agent_secrets.go` (`RegisterAgentSecretsVaultServer`),
  `apps/vault-adapter/internal/server/grpc_ssh.go` (the three method bodies; `requireScope` goes),
  `apps/vault-adapter/internal/server/identities.go` (`BootIdentities` scopes).
- Changed tests: `apps/vault-adapter/internal/server/grpc_ssh_test.go::newTestSSHGRPCServer`,
  `apps/vault-adapter/internal/server/grpc_test.go::TestGRPCValidateServiceIdentity_MissingToken`.
- New tests: `apps/vault-adapter/internal/server/method_scopes_test.go`,
  `apps/vault-adapter/internal/server/identity_scopes_test.go`.
- Clients: no code change. Every caller already sends its identity and token (the call sites are listed in the
  design); each holds the scopes for the methods it calls.
- Operators (migration):
  - Anything that writes credentials with the proxy's identity (`MINTKEY_VAULT_PROXY_*`), for example a seeding
    script, must use the admin identity (`MINTKEY_VAULT_ADMIN_*`). The repository's own acceptance tests already do.
  - Tools that call `ListVersions` or `ValidateServiceIdentity` without an identity now get `PERMISSION_DENIED`.
  - The comments in `infra/compose/docker-compose.yml` and `infra/compose/docker-compose.ghcr.yml` that say the proxy
    and SSH proxy get `vault.read + vault.put` become out of date. The unit may not edit `infra/**`; a person updates
    those comments after the merge. No compose or Helm value changes.
- Out of scope: tenant checks on the caller (an identity with `vault.read` still reads any tenant's credential); TLS on
  the vault port; reading tokens from files (change `service-token-files`).

## Issue Intake (remediation gate)

1. **Problem statement**: vault methods outside one map are served without an identity, and two components hold a
   write scope they do not use.
2. **User-visible symptom**: `ListVersions` answers a caller with no identity; the proxy's and the SSH proxy's
   identities can call `PutCredential`.
3. **Expected behavior**: every method except the health methods requires a valid identity with the method's scope; an
   unlisted method is refused; the proxy holds `vault.read` only; the SSH proxy holds `vault.read` and
   `vault.hostkey.put`.
4. **Evidence**: `methodScopes` and the "not listed" branch in `scopeInterceptor`; the map writes in
   `RegisterAgentSecretsVaultServer`; `requireScope` in `grpc_ssh.go`; the scopes in `BootIdentities`.
5. **Scope**: the changes under What Changes.
6. **Risk**: medium. A caller this change does not know of would be refused; the design lists every call site in the
   repository and the scope each needs.
