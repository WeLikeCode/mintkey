# Design: vault-method-scopes

## Context

Methods the vault adapter serves (`ListenAndServe` in `apps/vault-adapter/internal/server/grpc.go`), and how each is
checked today:

| Method (full name) | Check today |
|---|---|
| `/mintkey.vault.v1.VaultAdapter/GetCredential` | interceptor, `vault.read` |
| `/mintkey.vault.v1.VaultAdapter/PutCredential` | interceptor, `vault.put` |
| `/mintkey.vault.v1.VaultAdapter/RevokeCredential` | none (answers `UNIMPLEMENTED`) |
| `/mintkey.vault.v1.VaultAdapter/ListVersions` | none |
| `/mintkey.vault.v1.VaultAdapter/ValidateServiceIdentity` | in the handler (`UNAUTHENTICATED` without identity) |
| `/mintkey.vault.v1.AgentSecretsVault/{Put,Get,Delete}AgentSecret` | interceptor, after `RegisterAgentSecretsVaultServer` adds them |
| `/mintkey.vault.v1.SSHVaultAdapter/GetAgentByFingerprint`, `/GetHostKeyFingerprint` | in the handler (`requireScope`), `vault.read` |
| `/mintkey.vault.v1.SSHVaultAdapter/StoreHostKeyFingerprint` | in the handler, `vault.put` |
| `/grpc.health.v1.Health/Check`, `/List` (unary), `/Watch` (stream) | none; `grpc_health_probe` in compose and the Helm `grpc` probe call `Check` |

The server has a unary interceptor only. The generated constants are `vaultv1.VaultAdapter_<Name>_FullMethodName`,
`vaultv1.AgentSecretsVault_<Name>_FullMethodName` and `grpc_health_v1.Health_{Check,List,Watch}_FullMethodName`; the SSH
names are `"/" + sshVaultServiceName + "/<Name>"`.

Every client call site in the repository, with the identity it sends (all send both `x-mintkey-service-identity` and
`x-mintkey-service-token`) and the scope it needs after this change:

| Caller (file, function) | Method | Identity | Scope |
|---|---|---|---|
| proxy-plugin `cmd/proxy-plugin/main.go` `proxyHandler.ServeHTTP`, `proxyHandler.handleClassicalKey`, via `internal/vault/client.go` `Client.GetCredential` | GetCredential | `svcid_proxy` | `vault.read` |
| ssh-proxy `internal/backend/backend.go` `Connector.Connect`, via `internal/vault/client.go` `Client.GetCredential` | GetCredential | `svcid_ssh_proxy` | `vault.read` |
| ssh-proxy `internal/auth/auth.go` `Handler.AuthenticatePublicKey` (`Client.GetAgentByFingerprint`) | GetAgentByFingerprint | `svcid_ssh_proxy` | `vault.read` |
| ssh-proxy `internal/backend/hostkey.go` `TOFUStore.GetFingerprint` (`Client.GetHostKeyFingerprint`) | GetHostKeyFingerprint | `svcid_ssh_proxy` | `vault.read` |
| ssh-proxy `internal/backend/hostkey.go` `TOFUStore.StoreFingerprint` (`Client.StoreHostKeyFingerprint`) | StoreHostKeyFingerprint | `svcid_ssh_proxy` | `vault.hostkey.put` |
| email-proxy `cmd/email-proxy/main.go` `main`, `internal/server/server.go` `Server.handleReadyz` (`Client.ValidateServiceIdentity`) | ValidateServiceIdentity | `svcid_email_proxy` | any identity |
| email-proxy `internal/server/handlers/email.go` `EmailHandlers.leaseIMAPClient`, `EmailHandlers.getSMTPCredential`; `internal/vault/client.go` `Client.GetRefreshToken` (`Client.GetCredential`) | GetCredential | `svcid_email_proxy` | `vault.read` |
| admin-api `services/vault_client.py` `VaultAdapterClient.put_credential` / `.get_credential` / `.list_versions` | PutCredential / GetCredential / ListVersions | `svcid_admin_api` | `vault.put` / `vault.read` / `vault.read` |
| admin-api `services/agent_secrets_vault_client.py` `AgentSecretsVaultClient.put_agent_secret` / `.delete_agent_secret` | PutAgentSecret / DeleteAgentSecret | `svcid_admin_api` | `vault.secret.put` / `vault.secret.delete` |
| mcp-server `vault/agent_secrets_client.py` `AgentSecretsVaultClient.put_agent_secret` / `.get_agent_secret` / `.delete_agent_secret` | the three agent-secret methods | `svcid_mcp` | `vault.secret.put` / `.read` / `.delete` |

Nothing calls `RevokeCredential`; the broker and kong-syncer do not call the vault. `tests/acceptance/test_data_plane_smoke.py`
and `tests/acceptance/test_golden_path.py` write with the admin identity; `scripts/mintkey-doctor.sh` only checks that
the token variables are set. `xmodule_integration_test.go` (proxy-plugin) registers its own identity with explicit
scopes through `vaulttest.Start`, so `BootIdentities` does not affect it and it stays as it is.

## Assumed from earlier changes

- `broker-service-token-required` added `apps/vault-adapter/internal/server/identities.go` with `IdentitySpec`,
  `BootIdentities` (today's scopes) and `func (v *VaultService) RegisterBootIdentities(env string, lookup func(name
  string) (string, error)) (unset []string, err error)`, which registers each identity of `BootIdentities` whose token
  is set. This change edits only the `Scopes` values of two `BootIdentities` entries.
- `vault-service-identity-fast-check` made `ValidateServiceIdentity` cheap, so the interceptor validating every call
  (including `ValidateServiceIdentity` and the SSH methods) costs microseconds.

## Decisions

**D1. One closed table.** `methodScopes` becomes a package-level map literal holding every unary method of the
VaultAdapter, AgentSecretsVault and SSHVaultAdapter services (eleven entries, values in Interfaces) and is never
written at run time. `RegisterAgentSecretsVaultServer` loses its three map writes. The table lists the agent-secret and
SSH methods even when their service is not registered (SQLite backend): gRPC answers `UNIMPLEMENTED` for an
unregistered service before any interceptor runs.

**D2. Refuse first, then authenticate.** In `scopeInterceptor`: an `openMethods` method goes straight to the handler; a
method not in `methodScopes` is refused with `status.Errorf(codes.PermissionDenied, "method not allowed: %s",
info.FullMethod)` without reading metadata; then the existing checks run in their existing order with their existing
messages (`missing metadata`, `missing service token`, `invalid service token`, `caller lacks required scope %q`).

**D3. `ValidateServiceIdentity` needs any valid identity.** Its table value is `anyIdentity` (`"*"`), which skips only
the scope check. The handler keeps its own code; it now runs only for a caller the interceptor has authenticated. The
answer without an identity becomes `PERMISSION_DENIED`, like every other method.

**D4. Health stays open.** `openMethods` holds `Health_Check_FullMethodName` and `Health_List_FullMethodName`;
`openStreams` holds `Health_Watch_FullMethodName`. They report serving status only.

**D5. Streams are refused by default.** `streamScopeInterceptor()` serves an `openStreams` method and refuses any other
with `status.Errorf(codes.PermissionDenied, "method not allowed: %s", info.FullMethod)`. No vault method streams today;
this keeps a future one from being served unchecked.

**D6. Scope per method.** Reads (`GetCredential`, `ListVersions`, `GetAgentByFingerprint`, `GetHostKeyFingerprint`)
need `vault.read`; credential writes (`PutCredential`, `RevokeCredential`) need `vault.put`; the agent-secret methods
keep their scopes; `StoreHostKeyFingerprint` needs the new `vault.hostkey.put`. A narrower scope for the two SSH reads
was considered and left out: they return no secret, and `vault.read` already returns credentials themselves.

**D7. Least privilege per identity.** `BootIdentities` scopes after this change: proxy `[vault.read]`; admin-api
`[vault.read, vault.put, vault.secret.put, vault.secret.delete]` (unchanged); SSH proxy `[vault.read,
vault.hostkey.put]`; email proxy `[vault.read]` (unchanged); MCP server `[vault.secret.put, vault.secret.read,
vault.secret.delete]` (unchanged). Each matches the call-site table.

**D8. One place authorises.** The SSH handlers drop their `requireScope` calls and the function goes (it would be
unused, which `golangci-lint` reports). In production `ListenAndServe` always installs the interceptor; the SSH test
helper installs it too (D9).

**D9. Existing tests changed in place.** `grpc_ssh_test.go::newTestSSHGRPCServer` builds its server with
`grpc.NewServer(grpc.UnaryInterceptor(scopeInterceptor(svc)))` and registers `svcid_ssh_proxy` with
`[]string{"vault.read", "vault.hostkey.put"}`; the SSH tests that use it keep their assertions.
`grpc_test.go::TestGRPCValidateServiceIdentity_MissingToken` expects `codes.PermissionDenied` (its comment says so).

**D10. How the tests reach new code.** The red step runs the new tests against the base code (every non-Python
production file is put back), so a test may not name what only this change adds. The base of this unit is staging
with `broker-service-token-required` merged (the plan orders this change after it), so `BootIdentities`,
`IdentitySpec` and `(*VaultService).RegisterBootIdentities` exist there and the tests use them directly, as they use
`scopeInterceptor`, `methodScopes`, `RegisterAgentSecretsVaultServer`, `RegisterSSHVaultServer`, `New`,
`WithSSHStore`, `WithAgentSecretStore`, `fakeSSHStore` and `newFakeAgentSecretStore`. The new method
`buildGRPCServer` is reached through `type grpcServerBuilder interface { buildGRPCServer(svc *VaultService)
*grpc.Server }` asserted on the `*VaultServer` (`t.Fatal` when it fails); the stream rule is tested through such a
server, never by naming `streamScopeInterceptor`. The tests never name `openMethods`, `openStreams` or `anyIdentity`:
they write the health method names with the `grpc_health_v1` constants and `anyIdentity` as the literal `"*"`. Each test
is a top-level function without `t.Run`. No scaffold is needed.

## Interfaces

`apps/vault-adapter/internal/server/grpc.go`:

```go
// anyIdentity as a methodScopes value means: a valid identity, whatever its scopes.
const anyIdentity = "*"

// methodScopes maps every unary vault method to the scope its caller must hold. Never written at run time.
var methodScopes = map[string]string{
	vaultv1.VaultAdapter_GetCredential_FullMethodName:           "vault.read",
	vaultv1.VaultAdapter_PutCredential_FullMethodName:           "vault.put",
	vaultv1.VaultAdapter_RevokeCredential_FullMethodName:        "vault.put",
	vaultv1.VaultAdapter_ListVersions_FullMethodName:            "vault.read",
	vaultv1.VaultAdapter_ValidateServiceIdentity_FullMethodName: anyIdentity,
	vaultv1.AgentSecretsVault_PutAgentSecret_FullMethodName:     "vault.secret.put",
	vaultv1.AgentSecretsVault_GetAgentSecret_FullMethodName:     "vault.secret.read",
	vaultv1.AgentSecretsVault_DeleteAgentSecret_FullMethodName:  "vault.secret.delete",
	"/" + sshVaultServiceName + "/GetAgentByFingerprint":        "vault.read",
	"/" + sshVaultServiceName + "/GetHostKeyFingerprint":        "vault.read",
	"/" + sshVaultServiceName + "/StoreHostKeyFingerprint":      "vault.hostkey.put",
}

// openMethods are unary methods served without an identity.
var openMethods = map[string]bool{
	grpc_health_v1.Health_Check_FullMethodName: true,
	grpc_health_v1.Health_List_FullMethodName:  true,
}

// openStreams are streaming methods served without an identity; every other stream is refused.
var openStreams = map[string]bool{grpc_health_v1.Health_Watch_FullMethodName: true}

func scopeInterceptor(svc *VaultService) grpc.UnaryServerInterceptor // signature unchanged; rules D2, D3
func streamScopeInterceptor() grpc.StreamServerInterceptor             // rule D5

// buildGRPCServer returns the server ListenAndServe serves: grpc.NewServer with grpc.UnaryInterceptor(scopeInterceptor(svc))
// and grpc.StreamInterceptor(streamScopeInterceptor()); the health service set to SERVING; VaultAdapter; SSHVaultAdapter
// when s.sshStore != nil; AgentSecretsVault when s.agentSecretStore != nil.
func (s *VaultServer) buildGRPCServer(svc *VaultService) *grpc.Server
```

`ListenAndServe` calls `grpcSrv := s.buildGRPCServer(svc)` in place of the code that creates and registers the server
today; the HTTP mux, the routing by content type and the shutdown are unchanged.

## Failure cases

- No metadata, no token, empty token, unknown identity or wrong token on any listed method: `PERMISSION_DENIED`; the
  handler does not run.
- A valid identity without the method's scope: `PERMISSION_DENIED` `caller lacks required scope "<scope>"`.
- A method the table does not list (a future RPC registered without an entry): `PERMISSION_DENIED`
  `method not allowed: <method>`, and `TestMethodTable_CoversEveryServedMethod` fails in the gates.
- A method of a service that is not registered (SQLite backend): `UNIMPLEMENTED`, as today.
- Health probes without identity: served, as today.
- The proxy or SSH proxy calls `PutCredential`: `PERMISSION_DENIED`.

## Open questions

- None that block. The tenant check on the caller (an identity reads every tenant's credentials) is a separate concern.
