# An internal endpoint without a configured service token refuses every request

## Why

The broker authenticates its two internal endpoints with a shared service token in the `X-Mintkey-Service-Token`
header: `POST /v1/issue` (the MCP server, or an application that embeds the data plane) against
`MINTKEY_MCP_SERVICE_TOKEN`, and `POST /v1/api-keys/resolve` (the egress proxy) against
`MINTKEY_PROXY_SERVICE_TOKEN`. `config.Load` (`apps/broker/internal/config/config.go`) reads both with `os.Getenv`,
and neither handler (`issue.Handler.ServeHTTP`, `resolve.Handler.ServeHTTP`) checks that its configured token is set,
so an unset variable leaves the endpoint without the protection the header check is meant to give. Production mode adds
no guard of its own. `POST /v1/issue` signs a token for whatever agent, service and tenant the body names: the broker
trusts its caller to have made the access decision, which is only sound when the caller is authenticated.

A credential broker should fail closed: an endpoint whose secret is missing refuses every request, and a production
process does not start in a state where it cannot authenticate its callers.

The vault adapter registers its service identities from environment tokens in `main()`
(`apps/vault-adapter/cmd/vault-adapter/main.go`). An empty token already leaves that identity unregistered, so calls
made as it are refused; but production starts even when the egress proxy's and admin-api's tokens are missing, and the
registration code sits in `main()`, where no test reaches it.

## What Changes

- `issue.Handler` and `resolve.Handler` answer every request with 401
  `{"mintkey:code": "unauthenticated", "title": "Service token missing or invalid"}` (the body a wrong token gets today)
  when their configured token is the empty string, whatever the request carries, before they read the body. No token is
  signed, no audit event is queued, no metric moves, the store is not called.
- The broker's config gains `MissingServiceTokens()` and `Validate()`. In `MINTKEY_ENV=production` the broker exits
  non-zero at start and logs the names of the missing variables; in any other mode it starts and logs one warning per
  missing variable.
- The vault adapter's identity registration moves from `main()` into two new `VaultService` methods,
  `RegisterBootIdentities` and `RegisterBootIdentitiesFromEnv`, driven by the table `server.BootIdentities`: the same five identities, variable names, default ids and scopes as today. An empty
  token leaves its identity unregistered, as today, and is reported. In production the vault adapter refuses to start
  when `MINTKEY_VAULT_PROXY_TOKEN` or `MINTKEY_VAULT_ADMIN_TOKEN` is empty.
- `VaultService.RegisterServiceIdentity` refuses an empty identity id or an empty token.

## Capabilities

### New Capabilities
- `service-token-enforcement`: how the broker's internal endpoints and the vault adapter's boot identities behave when
  a service token is not configured, in development and in production.

## Impact

- Changed: `apps/broker/internal/api/issue/issue.go` (`Handler.ServeHTTP`), `apps/broker/internal/api/resolve/resolve.go`
  (`Handler.ServeHTTP`), `apps/broker/internal/config/config.go` (two new methods), `apps/broker/cmd/broker/main.go`
  (calls them), `apps/vault-adapter/internal/server/vault.go` (`RegisterServiceIdentity`),
  `apps/vault-adapter/cmd/vault-adapter/main.go` (the five registration blocks become one call).
- New module: `apps/vault-adapter/internal/server/identities.go`.
- New tests: `apps/broker/internal/api/issue/issue_empty_token_test.go`,
  `apps/broker/internal/api/resolve/resolve_empty_token_test.go`, `apps/broker/internal/config/config_test.go`,
  `apps/vault-adapter/internal/server/identities_test.go`.
- Callers with a configured token see no change. Existing tests that cover them stay as they are.
- Operators (migration):
  - A development stack that leaves `MINTKEY_MCP_SERVICE_TOKEN` or `MINTKEY_PROXY_SERVICE_TOKEN` unset now gets 401 on
    the endpoint that variable guards; set the variable on the broker and on its caller. The compose files under
    `infra/compose/` already set both.
  - A production broker without either variable, or a production vault adapter without `MINTKEY_VAULT_PROXY_TOKEN` or
    `MINTKEY_VAULT_ADMIN_TOKEN`, now exits at start with a message naming the variables. The Helm chart already passes
    all four from the chart's secret (`secretKeyRef`, not optional), so a Helm install that starts today keeps starting.
  - The SSH proxy, email proxy and MCP server identities stay optional in production: without their token they are not
    registered and their calls are refused, as today.
- Out of scope: the broker's outbound tokens (`MINTKEY_BROKER_SERVICE_TOKEN`, sent to the audit sink, and
  `MINTKEY_SERVICE_TOKEN`, read but unused); admin-api, which already ignores an empty configured token
  (`_get_allowed_service_tokens` in `admin_api.api.internal`); the email and SSH proxies' own inbound checks; the scopes
  each identity holds (change `vault-method-scopes`); reading tokens from files (change `service-token-files`); the cost
  of the identity check (change `vault-service-identity-fast-check`).

## Issue Intake (remediation gate)

1. **Problem statement**: the broker's internal endpoints and the vault adapter's production start do not require
   their service tokens to be configured.
2. **User-visible symptom**: a broker started without `MINTKEY_MCP_SERVICE_TOKEN` or `MINTKEY_PROXY_SERVICE_TOKEN`
   serves `POST /v1/issue` or `POST /v1/api-keys/resolve` without authenticating the caller; a production vault adapter
   without the proxy's or admin-api's token starts and then refuses that component's every call.
3. **Expected behavior**: an endpoint with no configured token answers 401 to every request; production refuses to
   start and names the missing variables; development starts and warns.
4. **Evidence**: the handlers and `config.Load` named under Why; the five registration blocks in the vault adapter's
   `main()`.
5. **Scope**: the four changes under What Changes.
6. **Risk**: low. Configured deployments behave as before; the new refusals apply only where a token is missing.
