# Requirements Document

## Introduction

Service templates provide pre-configured service definitions that operators can use to quickly register popular third-party APIs in Mintkey. Each template pre-populates the service registration form with the service name, base URL, auth type, OpenAPI spec reference, and description — reducing manual data entry and configuration errors. Templates are read-only seed data shipped with the Mintkey distribution; operators instantiate them into real service registrations via the existing service registration flow.

## Glossary

- **Service_Template**: A read-only, pre-configured service definition bundled with Mintkey that contains name, description, base URL, auth type, and OpenAPI spec reference for a popular third-party API.
- **Template_Registry**: The in-memory or file-based catalog of all available service templates, loaded at startup by the Admin API.
- **Template_Instantiation**: The act of creating a real `services` row from a service template, applying the operator's tenant context and allowing field overrides.
- **OpenAPI_Spec_Reference**: A URL pointing to the official or community-maintained OpenAPI specification for a templated service.
- **Admin_API**: The FastAPI-based Admin REST API (`apps/admin-api/`).
- **Admin_Console**: The AdminJS-based operator UI (`apps/admin-ui/`).
- **Operator**: A human user of the Admin Console who registers services.
- **OAuth2_Password_Grant**: An auth scheme where the Proxy_Plugin exchanges stored username/password credentials for a short-lived JWT by calling a token endpoint, then injects the resulting bearer token on the upstream request.
- **Token_URL**: The HTTP endpoint that accepts credential fields (e.g., username and password) and returns an access token (JWT or opaque) in its JSON response.
- **Token_Exchange**: The act of the Proxy_Plugin calling the Token_URL with stored credentials to obtain a bearer token for upstream injection.
- **Token_Response_Path**: A JSONPath expression (e.g., `$.token` or `$.access_token`) specifying where in the token endpoint's JSON response the access token value is located.
- **Credential_Fields**: Operator-defined key-value pairs stored in the Vault_Adapter that represent the body fields sent to the Token_URL (e.g., `username`, `password`, `grant_type`).
- **Token_Cache**: An in-memory, per-service cache in the Proxy_Plugin that holds the most recently exchanged bearer token and its expiry time to avoid redundant token exchanges.
- **Proxy_Plugin**: The Kong go-pdk plugin (`apps/proxy-plugin/`) that performs credential injection on outbound requests.
- **Vault_Adapter**: The Go gRPC service that stores and retrieves encrypted credentials.

## Requirements

### Requirement 1: Template Catalog Storage and Loading

**User Story:** As an operator, I want Mintkey to ship with a catalog of service templates so that I can browse and select popular APIs without manual research.

#### Acceptance Criteria

1. WHEN the Admin_API starts, THE Template_Registry SHALL load all service templates from a bundled JSON or YAML file within the application package.
2. THE Template_Registry SHALL contain exactly 12 service templates at initial release: GitLab, Apple App Store Connect, Google Play Developer API, Azure DevOps, Heroku, Brave Search, SendGrid, Twilio, Stripe, Cloudflare, Datadog, and PagerDuty.
3. WHEN a template is loaded, THE Template_Registry SHALL validate that each template contains all required fields: `template_id`, `name`, `display_name`, `description`, `base_url`, `auth_type`, `openapi_spec_url`, and `category`.
4. IF a template file is malformed or missing required fields, THEN THE Admin_API SHALL log a structured warning and exclude the invalid template from the registry without failing startup.

### Requirement 2: Template Listing API

**User Story:** As an operator, I want to list all available service templates so that I can discover which APIs are pre-configured.

#### Acceptance Criteria

1. WHEN an authenticated operator calls `GET /v1/service-templates`, THE Admin_API SHALL return a paginated list of all templates in the Template_Registry.
2. THE Admin_API SHALL include for each template: `template_id`, `name`, `display_name`, `description`, `base_url`, `auth_type`, `openapi_spec_url`, and `category`.
3. WHEN an operator provides a `category` query parameter, THE Admin_API SHALL filter the results to templates matching that category.
4. WHEN an operator provides a `search` query parameter, THE Admin_API SHALL filter templates whose `name`, `display_name`, or `description` contain the search term (case-insensitive).

### Requirement 3: Template Detail API

**User Story:** As an operator, I want to view the full details of a specific template so that I can review its configuration before instantiating it.

#### Acceptance Criteria

1. WHEN an authenticated operator calls `GET /v1/service-templates/{template_id}`, THE Admin_API SHALL return the complete template definition including all fields and configuration notes.
2. IF the `template_id` does not exist in the Template_Registry, THEN THE Admin_API SHALL return `404 Not Found` with `mintkey:code=template_not_found`.

### Requirement 4: Template Instantiation

**User Story:** As an operator, I want to create a service registration from a template so that I can quickly onboard a popular API with minimal manual configuration.

#### Acceptance Criteria

1. WHEN an authenticated operator calls `POST /v1/tenants/{tid}/services/from-template` with body `{template_id, overrides?}`, THE Admin_API SHALL create a new service registration pre-populated with the template's `name`, `display_name`, `description`, `base_url`, `auth_type`, and `openapi_spec_url`.
2. WHEN the operator provides an `overrides` object, THE Admin_API SHALL apply the overrides to the template values before creating the service (allowing customization of `name`, `display_name`, `description`, `base_url`).
3. WHEN a service is created from a template, THE Admin_API SHALL follow the existing service registration flow including audit event emission (`service.registered`), change-channel notification, and RLS enforcement.
4. WHEN a service is created from a template, THE Admin_API SHALL record `template_id` as metadata on the service for traceability.
5. IF a service with the same `(tenant_id, name)` already exists, THEN THE Admin_API SHALL return `409 Conflict` with `mintkey:code=service_name_taken` (consistent with direct registration behavior).

### Requirement 5: Template Content — GitLab

**User Story:** As an operator, I want a pre-configured template for the GitLab API so that I can quickly register GitLab as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a GitLab template with `name=gitlab`, `display_name=GitLab`, `base_url=https://gitlab.com/api/v4`, `auth_type=bearer_token`, `category=ci_cd`.
2. THE GitLab template SHALL reference the official OpenAPI spec at `https://gitlab.com/gitlab-org/gitlab/-/raw/master/doc/api/openapi/openapi.yaml`.
3. THE GitLab template SHALL include a description stating that the API covers CI/CD pipelines, repository management, merge requests, and project administration.

### Requirement 6: Template Content — Apple App Store Connect

**User Story:** As an operator, I want a pre-configured template for the Apple App Store Connect API so that I can quickly register it as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include an Apple App Store Connect template with `name=apple-app-store-connect`, `display_name=Apple App Store Connect`, `base_url=https://api.appstoreconnect.apple.com/v1`, `auth_type=bearer_token`, `category=app_store`.
2. THE Apple App Store Connect template SHALL reference the OpenAPI spec at `https://developer.apple.com/sample-code/app-store-connect/app-store-connect-openapi-specification.zip`.
3. THE Apple App Store Connect template SHALL include a configuration note that authentication requires a JWT signed with an App Store Connect API key (ES256).

### Requirement 7: Template Content — Google Play Developer API

**User Story:** As an operator, I want a pre-configured template for the Google Play Developer API so that I can quickly register it as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a Google Play Developer API template with `name=google-play-developer`, `display_name=Google Play Developer API`, `base_url=https://androidpublisher.googleapis.com`, `auth_type=oauth2_client_credentials`, `category=app_store`.
2. THE Google Play Developer API template SHALL reference the Google Discovery document at `https://androidpublisher.googleapis.com/$discovery/rest?version=v3`.
3. THE Google Play Developer API template SHALL include a configuration note that authentication uses OAuth 2.0 service account credentials.

### Requirement 8: Template Content — Azure DevOps

**User Story:** As an operator, I want a pre-configured template for the Azure DevOps API so that I can quickly register it as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include an Azure DevOps template with `name=azure-devops`, `display_name=Azure DevOps`, `base_url=https://dev.azure.com`, `auth_type=bearer_token`, `category=ci_cd`.
2. THE Azure DevOps template SHALL reference the OpenAPI specs repository at `https://github.com/Azure/azure-rest-api-specs/tree/main/specification/devops`.
3. THE Azure DevOps template SHALL include a configuration note that the base URL requires an organization name appended (e.g., `https://dev.azure.com/{organization}`).

### Requirement 9: Template Content — Heroku

**User Story:** As an operator, I want a pre-configured template for the Heroku Platform API so that I can quickly register it as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a Heroku template with `name=heroku`, `display_name=Heroku`, `base_url=https://api.heroku.com`, `auth_type=bearer_token`, `category=platform`.
2. THE Heroku template SHALL reference the platform API schema at `https://devcenter.heroku.com/articles/platform-api-reference`.
3. THE Heroku template SHALL include a configuration note that the API uses JSON Schema (not OpenAPI) as its machine-readable spec format, and requires `Accept: application/vnd.heroku+json; version=3` header.

### Requirement 10: Template Content — Brave Search

**User Story:** As an operator, I want a pre-configured template for the Brave Search API so that I can quickly register it as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a Brave Search template with `name=brave-search`, `display_name=Brave Search`, `base_url=https://api.search.brave.com/res/v1`, `auth_type=api_key_header`, `category=search`.
2. THE Brave Search template SHALL reference the API documentation at `https://api.search.brave.com/app/documentation/web-search/get-started`.
3. THE Brave Search template SHALL include a configuration note that the API key is passed via the `X-Subscription-Token` header.

### Requirement 11: Template Content — SendGrid

**User Story:** As an operator, I want a pre-configured template for the SendGrid API so that I can quickly register it as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a SendGrid template with `name=sendgrid`, `display_name=SendGrid`, `base_url=https://api.sendgrid.com/v3`, `auth_type=bearer_token`, `category=communications`.
2. THE SendGrid template SHALL reference the OpenAPI spec at `https://raw.githubusercontent.com/sendgrid/sendgrid-oai/main/oai.json`.
3. THE SendGrid template SHALL include a description stating that the API covers email sending, templates, contacts, and analytics.

### Requirement 12: Template Content — Twilio

**User Story:** As an operator, I want a pre-configured template for the Twilio API so that I can quickly register it as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a Twilio template with `name=twilio`, `display_name=Twilio`, `base_url=https://api.twilio.com/2010-04-01`, `auth_type=basic_auth`, `category=communications`.
2. THE Twilio template SHALL reference the official OpenAPI specs at `https://github.com/twilio/twilio-oai/tree/main/spec/json`.
3. THE Twilio template SHALL include a configuration note that authentication uses Account SID as username and Auth Token as password (HTTP Basic Auth).

### Requirement 13: Template Content — Stripe

**User Story:** As an operator, I want a pre-configured template for the Stripe API so that I can quickly register it as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a Stripe template with `name=stripe`, `display_name=Stripe`, `base_url=https://api.stripe.com/v1`, `auth_type=bearer_token`, `category=payments`.
2. THE Stripe template SHALL reference the official OpenAPI spec at `https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json`.
3. THE Stripe template SHALL include a description stating that the API covers payments, subscriptions, invoicing, and financial reporting.

### Requirement 14: Template Content — Cloudflare

**User Story:** As an operator, I want a pre-configured template for the Cloudflare API so that I can quickly register it as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a Cloudflare template with `name=cloudflare`, `display_name=Cloudflare`, `base_url=https://api.cloudflare.com/client/v4`, `auth_type=bearer_token`, `category=infrastructure`.
2. THE Cloudflare template SHALL reference the OpenAPI schemas at `https://github.com/cloudflare/api-schemas/tree/main/openapi.json`.
3. THE Cloudflare template SHALL include a description stating that the API covers DNS management, CDN configuration, security rules, and Workers deployment.

### Requirement 15: Template Content — Datadog

**User Story:** As an operator, I want a pre-configured template for the Datadog API so that I can quickly register it as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a Datadog template with `name=datadog`, `display_name=Datadog`, `base_url=https://api.datadoghq.com/api/v2`, `auth_type=api_key_header`, `category=observability`.
2. THE Datadog template SHALL reference the API documentation at `https://docs.datadoghq.com/api/latest/`.
3. THE Datadog template SHALL include a configuration note that authentication requires both `DD-API-KEY` and `DD-APPLICATION-KEY` headers, and the base URL varies by region (e.g., `api.us5.datadoghq.com`).

### Requirement 16: Template Content — PagerDuty

**User Story:** As an operator, I want a pre-configured template for the PagerDuty API so that I can quickly register it as a backend service.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a PagerDuty template with `name=pagerduty`, `display_name=PagerDuty`, `base_url=https://api.pagerduty.com`, `auth_type=bearer_token`, `category=incident_management`.
2. THE PagerDuty template SHALL reference the official OpenAPI spec at `https://github.com/PagerDuty/api-schema/tree/main/reference`.
3. THE PagerDuty template SHALL include a description stating that the API covers incident management, on-call scheduling, escalation policies, and service health.

### Requirement 17: Admin Console Template Browser

**User Story:** As an operator, I want to browse and select service templates from the Admin Console so that I can register services without using the API directly.

#### Acceptance Criteria

1. WHEN an operator navigates to the service registration page in the Admin_Console, THE Admin_Console SHALL display a "From Template" option alongside manual registration.
2. WHEN an operator selects "From Template", THE Admin_Console SHALL display the template catalog grouped by category with search functionality.
3. WHEN an operator selects a template, THE Admin_Console SHALL pre-fill the service registration form with the template values and allow the operator to override any field before submitting.
4. WHEN an operator submits a template-based registration, THE Admin_Console SHALL call the `POST /v1/tenants/{tid}/services/from-template` endpoint.

### Requirement 18: Template Versioning

**User Story:** As an operator, I want templates to be versioned so that I know when template content has been updated between Mintkey releases.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a `version` field on each template following semantic versioning (e.g., `1.0.0`).
2. WHEN a template's content changes between Mintkey releases (base URL, auth type, or OpenAPI spec URL), THE Template_Registry SHALL increment the template version.
3. WHEN an operator lists templates, THE Admin_API SHALL include the `version` field in the response.


### Requirement 19: OAuth2 Password Grant Auth Scheme Definition and Credential Storage

**User Story:** As an operator, I want to register a service that authenticates via username/password-to-JWT exchange so that the proxy can automatically obtain bearer tokens without exposing credentials to agents.

#### Acceptance Criteria

1. THE Admin_API SHALL support a new `auth_type` value `oauth2_password_grant` in the service registration and template schemas.
2. WHEN an operator registers a service with `auth_type=oauth2_password_grant`, THE Admin_API SHALL require a structured credential payload containing: `token_url` (required), one or more Credential_Fields for the token request body (required), and an optional `token_response_path` (default: `$.access_token`).
3. THE Vault_Adapter SHALL store the OAuth2_Password_Grant credential as a JSON-encoded structured payload containing `token_url`, `credential_fields` (a map of operator-defined field names to values), `token_response_path`, and optional `token_request_headers` (a map of header names to values).
4. THE Admin_API SHALL validate that `token_url` is a valid HTTPS URL and passes the existing SSRF allowlist check (S-SEC-1).
5. THE Admin_API SHALL allow operator-defined field names in `credential_fields` without hardcoding to `username` or `password` (supporting arbitrary field names such as `client_id`, `client_secret`, `grant_type`, `scope`).
6. WHEN an operator does not provide `token_response_path`, THE Admin_API SHALL default it to `$.access_token`.

### Requirement 20: Token Exchange Flow in the Proxy Plugin

**User Story:** As a system operator, I want the proxy to automatically exchange stored credentials for a bearer token so that upstream APIs receive a valid JWT without the agent knowing the underlying credentials.

#### Acceptance Criteria

1. WHEN the Proxy_Plugin receives a request for a service with `auth_scheme=oauth2_password_grant`, THE Proxy_Plugin SHALL retrieve the structured credential from the Vault_Adapter.
2. WHEN the Proxy_Plugin has no cached valid token for the service, THE Proxy_Plugin SHALL perform a Token_Exchange by sending an HTTP POST to the stored `token_url` with the `credential_fields` as the JSON request body and any configured `token_request_headers`.
3. WHEN the token endpoint returns a successful response (HTTP 2xx), THE Proxy_Plugin SHALL extract the access token from the response JSON using the configured `token_response_path`.
4. WHEN the Proxy_Plugin obtains a valid token, THE Proxy_Plugin SHALL inject it as `Authorization: Bearer <token>` on the upstream request.
5. IF the token endpoint returns a non-2xx response, THEN THE Proxy_Plugin SHALL return HTTP 502 to the caller with error code `token_exchange_failed` and log the failure (without logging credential values).
6. IF the token endpoint is unreachable (connection timeout, DNS failure), THEN THE Proxy_Plugin SHALL return HTTP 502 to the caller with error code `token_endpoint_unreachable`.
7. THE Proxy_Plugin SHALL set a request timeout of 10 seconds for the Token_Exchange HTTP call.

### Requirement 21: Token Caching and Automatic Refresh

**User Story:** As a system operator, I want the proxy to cache exchanged tokens and refresh them before expiry so that upstream latency is minimized and token endpoints are not overwhelmed.

#### Acceptance Criteria

1. WHEN the Proxy_Plugin successfully exchanges credentials for a token, THE Token_Cache SHALL store the token keyed by `(tenant_id, service_id)`.
2. THE Proxy_Plugin SHALL determine token expiry by: (a) decoding the `exp` claim from the JWT payload if the token is a valid JWT, or (b) reading the `expires_in` field from the token response body, or (c) defaulting to 300 seconds if neither is available.
3. WHILE a cached token exists and its expiry is more than 30 seconds in the future, THE Proxy_Plugin SHALL use the cached token without performing a new Token_Exchange.
4. WHEN a cached token's expiry is 30 seconds or fewer in the future, THE Proxy_Plugin SHALL perform a new Token_Exchange to obtain a fresh token before injecting it on the upstream request.
5. THE Token_Cache SHALL store tokens in memory only and SHALL NOT persist tokens to disk, database, or any durable storage.
6. WHEN the Proxy_Plugin restarts, THE Token_Cache SHALL be empty (no warm-up from persisted state).
7. IF a Token_Exchange for refresh fails, THEN THE Proxy_Plugin SHALL use the existing cached token if it has not yet expired, and return HTTP 502 only after the cached token has fully expired.

### Requirement 22: Audit and Security for Token Exchange

**User Story:** As a security-conscious operator, I want token exchanges to be audited and credentials to remain contained so that I have visibility into token lifecycle without risking credential exposure.

#### Acceptance Criteria

1. WHEN the Proxy_Plugin performs a Token_Exchange, THE Proxy_Plugin SHALL emit an audit event of type `token.exchanged` containing: `tenant_id`, `service_id`, `agent_id`, `token_url` (redacted to host only), `success` (boolean), and `latency_ms`.
2. THE Proxy_Plugin SHALL NOT include the stored username, password, or any Credential_Fields values in audit events, logs, or OTel span attributes.
3. THE Proxy_Plugin SHALL NOT include the exchanged bearer token value in audit events, logs, or OTel span attributes.
4. THE Token_Cache SHALL hold tokens in request-scoped or short-lived memory; the exchanged JWT SHALL NOT be persisted to any durable store.
5. THE Vault_Adapter SHALL NOT return the `token_url` credential fields to any caller other than the Proxy_Plugin (enforced by gRPC scope `vault.read`).
6. WHEN an agent makes a proxied request through a service using `oauth2_password_grant`, THE agent SHALL NOT receive the exchanged bearer token or the underlying credentials in any response header, body, or error message.
7. IF the Proxy_Plugin logs a token exchange failure, THEN THE Proxy_Plugin SHALL log the HTTP status code and a generic error message without including request body content or response body content.

### Requirement 23: Template Support for OAuth2 Password Grant Services

**User Story:** As an operator, I want a pre-configured template for APIs that use username/password-to-JWT authentication so that I can quickly register such services with the correct auth scheme and credential structure.

#### Acceptance Criteria

1. THE Template_Registry SHALL include a template with `name=azure-dashboard-api`, `display_name=Azure Dashboard API`, `base_url=https://dashboard-api-ps-prod.azurewebsites.net/api`, `auth_type=oauth2_password_grant`, `category=platform`.
2. THE Azure Dashboard API template SHALL reference the OpenAPI spec at `https://dashboard-api-ps-prod.azurewebsites.net/swagger/v1/swagger.json`.
3. THE Azure Dashboard API template SHALL include a `credential_hint` specifying: `token_url=https://dashboard-api-ps-prod.azurewebsites.net/api/auth/login`, `credential_fields` with keys `username` and `password`, and `token_response_path=$.token`.
4. THE Azure Dashboard API template SHALL include a configuration note stating that the login endpoint accepts `{username, password}` as JSON body and returns `{token}` containing a JWT.
5. WHEN an operator instantiates the Azure Dashboard API template, THE Admin_API SHALL pre-populate the credential structure with the correct `token_url`, field names, and `token_response_path` so the operator only needs to supply the actual username and password values.
