# Auth0 Management API service template

## Why

Agents have no first-class way to perform Auth0 tenant administration (manage applications/clients, users, connections, roles, actions, logs) through Mintkey. The Auth0 Management API (`https://{tenantDomain}/api/v2`) is Bearer-authenticated with an access token obtained via **OAuth 2.0 client-credentials** from the tenant's own token endpoint (`https://{tenantDomain}/oauth/token`) — a scheme Mintkey already implements end-to-end (`oauth2_client_credentials`, enum 5, ADR-0029 D2 / change `mongodb-atlas-admin-api`). One gap blocks Auth0:

- **Auth0's client-credentials token request requires an `audience` parameter** — `audience=https://{tenantDomain}/api/v2/` (trailing slash), form-urlencoded alongside `grant_type=client_credentials`, `client_id`, `client_secret`. Verified against the Management API OAS (`securitySchemes.oAuth2ClientCredentials.flows.clientCredentials` carries `tokenUrl: /oauth/token/` and `x-form-parameters: {audience: /api/v2/}`) and Auth0's production-token guide (response `{access_token, expires_in: 86400, scope, token_type: "Bearer"}` — a 24-hour token). The current scheme never sends `audience`: the Go `ExchangeClientCredentials` form body emits only `grant_type` (+ optional `scope`), and admin-api's `OAuth2ClientCredentialsPayload` has no `audience` field — Pydantic's default `extra='ignore'` silently drops a submitted `audience` at registration, so the stored envelope can never carry it.

Two further Auth0 facts shape the design:

1. **Everything is per-tenant-domain** — token endpoint, audience, and API base URL all live on the operator's Auth0 domain (`YOUR_TENANT.auth0.com`, regional variants like `YOUR_TENANT.us.auth0.com`, or a custom domain). The template ships CHANGE-ME-style placeholders exactly like the `ssh-bastion-*` templates (`ssh://CHANGE-ME-HOST:22`).
2. Auth0 needs **no dated `Accept` version header** (unlike MongoDB Atlas): the Management API OAS declares plain `bearerAuth` (`type: http, scheme: bearer, bearerFormat: jwt`) and nothing else — no special headers to instruct the agent about.

## What Changes

- **The `oauth2_client_credentials` scheme gains an optional `audience` field** — a surgical, additive extension across the three existing surfaces: Go `OAuth2ClientCredentialsCredential` + `ClientCredentialsRequest` (`audience,omitempty`; emitted in the form body only when non-empty), the egress handler's field mapping, and admin-api `OAuth2ClientCredentialsPayload` (+ `to_vault_envelope()`; validated when present as a non-empty absolute URI). Credentials **without** `audience` (MongoDB Atlas Service Accounts) produce a byte-identical token request — the Atlas path is regression-pinned unchanged. `cmd/proxy-plugin/main.go`, the token cache, the password-grant `Exchange`, and the injector are untouched.
- **A new `auth0-management` service template** — `auth_type: oauth2_client_credentials`, placeholder `base_url: https://YOUR_TENANT.auth0.com/api/v2`, credential hint with `token_url: https://YOUR_TENANT.auth0.com/oauth/token`, `credential_fields` for `client_id` / `client_secret` / `audience` (canonical trailing-slash value `https://YOUR_TENANT.auth0.com/api/v2/`), the Management API OAS URL as `openapi_spec_url`, `test_path: /clients`, and `config_notes` walking the operator through replacing `YOUR_TENANT` (including regional/custom domains), creating an authorized M2M application, and the trailing-slash audience pitfall.
- **No new ADR, enum, table, or endpoint** — the scheme stays enum 5 on every wire surface; `audience` is a minor additive parameter within the payload ADR-0029 D2 defines. ADR-0029 is still **Proposed** (not yet immutable), so a one-line `"audience": "(optional)"` addition to its D2 payload example rides along as a doc task rather than a new ADR.

## Capabilities

### New Capabilities
- `auth0-management-template`: optional `audience` on the client-credentials token exchange (proxy + admin-api validation + vault envelope) and a one-click Auth0 Management API service template with per-tenant-domain placeholder handling.

### Modified Capabilities
<!-- none at main-spec level — the oauth2-client-credentials-auth delta from the (stacked, unarchived) mongodb-atlas-admin-api change is not yet synced into openspec/specs/, so there is no main-spec requirement to MODIFY; this change's spec states the audience requirements standalone, including the Atlas non-regression requirement -->

## Impact

- **Proxy (Go)** — `apps/proxy-plugin/internal/credential/types.go` (+`Audience` on `OAuth2ClientCredentialsCredential`); `apps/proxy-plugin/internal/credential/exchanger.go` (+`Audience` on `ClientCredentialsRequest`; form body gains `audience` when non-empty); `apps/proxy-plugin/internal/egress/oauth2_client_credentials.go` (map `cred.Audience` into the exchange request). `cmd/proxy-plugin/main.go` untouched — dispatch keys on the presence of a non-empty `token_url`, not on `audience`.
- **admin-api (Python)** — `apps/admin-api/src/admin_api/services/credential_service.py` (optional `audience` on `OAuth2ClientCredentialsPayload` + validator + envelope emission); `apps/admin-api/src/admin_api/api/credentials.py` **unchanged** (its scheme-5 block validates via `OAuth2ClientCredentialsPayload(**raw_cc)`, so the new field flows through automatically); `apps/admin-api/src/admin_api/templates/service_templates.yaml` (+`auth0-management`).
- **Contracts** — none. No proto/OpenAPI/MCP enum change (scheme 5 already exists everywhere); the credential value is an opaque encrypted envelope on every wire surface, so the OpenAPI snapshot must not change.
- **MCP server** — none. The existing `oauth2_client_credentials` injection hint already describes the exchange-and-inject behavior; enum-parity and bootstrap-parity gates must simply stay green.
- **Docs** — `docs/HOW-TO.md` new §14 "Auth0 Management API"; one-line `audience` mention in still-Proposed ADR-0029 D2's payload example.
- **Tests** — Go exchanger/egress audience cases + an Atlas no-audience byte-level regression; admin-api payload tests (audience accepted/omitted/rejected, secrets never echoed) + `test_auth0_management_template.py` (registry fields, hint survival, from-template); parity/snapshot/plaintext gates green; live smoke against a real Auth0 tenant.
- **Out of scope**: read-scoped method gating for Auth0 (agents use the existing `call` action; least privilege comes from the Management API scopes granted to the operator's M2M application on Auth0's side); a generic `extra_token_params` map (see design — rejected as speculative); the Auth0 Authentication API (login/passwordless flows) as a brokered service; a `client_auth_method` (Basic vs Post) switch on the exchanger; automatic tenant-domain discovery or placeholder templating beyond the ssh-style CHANGE-ME convention; admin-ui form work beyond what template instantiation already provides.
