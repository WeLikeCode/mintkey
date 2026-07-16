# Auth0 Management Template

## ADDED Requirements

### Requirement: Client-credentials token request includes audience when configured
The egress proxy SHALL, when an `oauth2_client_credentials` credential payload contains a non-empty `audience`, include `audience=<value>` in the form-encoded token-request body alongside `grant_type=client_credentials` (and `scope` when present). The request MUST remain `application/x-www-form-urlencoded` and MUST remain authenticated with HTTP Basic `client_id:client_secret`; the token MUST still be extracted via `token_response_path` (default `$.access_token`) with `expires_in` honored for cache TTL.

#### Scenario: Auth0 exchange sends the audience
- **WHEN** the proxy exchanges a credential whose payload has `token_url` `https://tenant.auth0.com/oauth/token` and `audience` `https://tenant.auth0.com/api/v2/`
- **THEN** the POST to the token endpoint is form-encoded with a body containing both `grant_type=client_credentials` and `audience=https://tenant.auth0.com/api/v2/`, carries `Authorization: Basic base64(client_id:client_secret)`, and the returned `access_token` (a 24-hour token, `expires_in` 86400) is injected upstream as `Authorization: Bearer <token>` without the agent ever seeing it

#### Scenario: No audience key when unset
- **WHEN** the proxy exchanges a credential whose payload has no `audience` (or an empty one)
- **THEN** the form body contains no `audience` key — exactly `grant_type=client_credentials` plus `scope` when configured

### Requirement: Optional audience is validated and persisted without echoing secrets
The Admin REST API SHALL accept an optional `audience` field on `oauth2_client_credentials` credential registration. When present, `audience` MUST be a non-empty absolute URI (it is NOT SSRF-checked and NOT restricted to HTTPS — it is an opaque identifier never dereferenced by Mintkey) and MUST be emitted in the canonical vault envelope; when absent, the envelope MUST omit the `audience` key. On validation failure the response MUST NOT contain any submitted credential value.

#### Scenario: Audience stored in the canonical envelope
- **WHEN** an operator registers an `oauth2_client_credentials` credential with a valid HTTPS `token_url`, non-empty `client_id`/`client_secret`, and `audience` `https://tenant.auth0.com/api/v2/`
- **THEN** the encrypted envelope handed to the Vault Adapter contains `"audience":"https://tenant.auth0.com/api/v2/"` and the API response carries metadata only

#### Scenario: Envelope omits an absent audience
- **WHEN** an operator registers an `oauth2_client_credentials` credential without an `audience` field
- **THEN** the stored envelope contains no `audience` key and is identical to the pre-extension envelope for the same input

#### Scenario: Invalid audience rejected without echoing secrets
- **WHEN** an operator submits an `audience` that is whitespace-only or lacks a URI scheme
- **THEN** the API returns a 4xx with structured field errors and the response body contains no `client_secret`, `client_id`, or other submitted value

### Requirement: Auth0 Management API template registers correctly
The template registry SHALL provide `auth0-management` with `auth_type: oauth2_client_credentials`, placeholder `base_url: https://YOUR_TENANT.auth0.com/api/v2`, `openapi_spec_url: https://auth0.com/docs/oas/management/v2/management-api-oas.json`, `test_path: /clients`, and a credential hint whose `token_url` is `https://YOUR_TENANT.auth0.com/oauth/token`, whose `token_response_path` is `$.access_token`, and whose `credential_fields` map includes `client_id`, `client_secret`, and `audience` with the canonical trailing-slash placeholder `https://YOUR_TENANT.auth0.com/api/v2/`. The template's `config_notes` MUST instruct the operator to replace `YOUR_TENANT` with their tenant domain everywhere (including regional or custom domains) and MUST state that the audience must match the tenant's Management API identifier exactly, including the trailing slash.

#### Scenario: Operator registers Auth0 from the template
- **WHEN** an operator instantiates `auth0-management`
- **THEN** a service is created (HTTP 201) with `auth_scheme: oauth2_client_credentials` and `base_url: https://YOUR_TENANT.auth0.com/api/v2`, ready for the operator to replace the placeholder domain and attach the M2M credential

#### Scenario: Placeholder base_url does not block creation
- **WHEN** the template is instantiated while `YOUR_TENANT.auth0.com` does not resolve in DNS
- **THEN** service creation succeeds (the SSRF gate fails open on DNS failure, matching the ssh CHANGE-ME templates) and connectivity simply fails until the operator replaces the placeholder

#### Scenario: Credential hint survives registry loading
- **WHEN** the registry loads `service_templates.yaml` and serves the `auth0-management` template
- **THEN** the returned credential hint retains `token_url`, `token_response_path`, and all three `credential_fields` keys (`client_id`, `client_secret`, `audience`) — none silently dropped by hint parsing

### Requirement: Existing client-credentials credentials are unaffected by the audience extension
An `oauth2_client_credentials` credential without `audience` (e.g. a MongoDB Atlas Service Account) SHALL produce a token request byte-identical to the pre-extension behavior, and its vault envelope SHALL be unchanged. The password-grant scheme, the scheme-5 pre-fetched-bearer fallback dispatch, the token cache key `(tenant_id, service_id)`, and the singleflight/graceful-degradation orchestration MUST NOT change.

#### Scenario: Atlas exchange unchanged
- **WHEN** the proxy exchanges an Atlas Service Account credential (`token_url` `https://cloud.mongodb.com/api/oauth/token`, no `audience`)
- **THEN** the form body, Basic authorization, token extraction, and caching behave exactly as before the extension — the form body contains no `audience` key

#### Scenario: Pre-existing suites pass unmodified
- **WHEN** the existing client-credentials, password-grant, digest, dispatch, and Atlas payload/template test suites run against the extended code
- **THEN** they pass without any test being edited
