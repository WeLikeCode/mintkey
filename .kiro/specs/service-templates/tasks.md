# Implementation Plan: Service Templates + OAuth2 Password Grant

## Overview

This plan implements two major feature areas: (1) a YAML-based service template catalog with list/detail/instantiation APIs and Admin UI browser, and (2) an OAuth2 Password Grant auth scheme with token exchange, caching, and audit in the Proxy Plugin. Implementation follows dependency order: proto extension → vault storage → template catalog → APIs → proxy plugin → Admin UI.

## Tasks

- [x] 1. Proto enum extension and shared Go types
  - [x] 1.1 Add AUTH_SCHEME_OAUTH2_PASSWORD_GRANT = 8 to vault.proto
    - Edit `docs/architecture/contracts/vault-adapter/vault.proto` to add the new enum value
    - Add Go constant `AuthSchemeOAuth2PasswordGrant AuthScheme = 8` in proxy-plugin
    - Define `OAuth2PasswordGrantCredential` struct in `apps/proxy-plugin/internal/credential/types.go`
    - _Requirements: 19.1, 19.3_

- [x] 2. Template catalog and registry (Python)
  - [x] 2.1 Create service_templates.yaml with all 12+1 templates
    - Create `apps/admin-api/src/admin_api/templates/service_templates.yaml`
    - Include all 12 templates: GitLab, Apple App Store Connect, Google Play Developer, Azure DevOps, Heroku, Brave Search, SendGrid, Twilio, Stripe, Cloudflare, Datadog, PagerDuty
    - Include the Azure Dashboard API template with `auth_type: oauth2_password_grant`
    - Each template must have: template_id, name, display_name, description, base_url, auth_type, openapi_spec_url, category, version, config_notes, credential_hint, test_path
    - _Requirements: 1.2, 5.1-5.3, 6.1-6.3, 7.1-7.3, 8.1-8.3, 9.1-9.3, 10.1-10.3, 11.1-11.3, 12.1-12.3, 13.1-13.3, 14.1-14.3, 15.1-15.3, 16.1-16.3, 18.1, 23.1-23.4_

  - [x] 2.2 Implement ServiceTemplate Pydantic model and CredentialHint
    - Create `apps/admin-api/src/admin_api/templates/models.py`
    - Define `ServiceTemplate`, `CredentialHint`, `OAuth2CredentialHint` models
    - Include version field with semver validation
    - _Requirements: 1.3, 18.1_

  - [x] 2.3 Implement TemplateRegistry with load, list, get, filter
    - Create `apps/admin-api/src/admin_api/templates/registry.py`
    - Load and validate YAML at import time
    - Implement `list_all(category, search)` with case-insensitive search across name/display_name/description
    - Implement `get(template_id)` returning `ServiceTemplate | None`
    - Log warnings for malformed entries without failing startup
    - _Requirements: 1.1, 1.3, 1.4, 2.3, 2.4_

  - [x]* 2.4 Write unit tests for TemplateRegistry and ServiceTemplate model
    - Test loading valid YAML exposes all 13 templates
    - Test skipping malformed entries with warning log
    - Test category filtering
    - Test case-insensitive search across name/display_name/description
    - Test ServiceTemplate validates required fields
    - _Requirements: 1.1-1.4, 2.3, 2.4_

- [x] 3. OAuth2PasswordGrantPayload validation (Python)
  - [x] 3.1 Implement OAuth2PasswordGrantPayload Pydantic model
    - Create or extend `apps/admin-api/src/admin_api/services/credential_service.py`
    - Define `OAuth2PasswordGrantPayload` with `token_url` (HTTPS validation), `credential_fields` (non-empty), `token_response_path` (default `$.access_token`), `token_request_headers`
    - Integrate with existing SSRF allowlist check (S-SEC-1)
    - _Requirements: 19.2, 19.4, 19.5, 19.6_

  - [x]* 3.2 Write property test for credential payload validation (Property 1)
    - **Property 1: Credential payload validation**
    - Generate arbitrary payloads; verify acceptance iff token_url is HTTPS and credential_fields is non-empty
    - Use `hypothesis` for Python PBT
    - **Validates: Requirements 19.2, 19.5**

  - [x]* 3.3 Write property test for token_url HTTPS and SSRF validation (Property 3)
    - **Property 3: token_url HTTPS and SSRF validation**
    - Generate arbitrary URL strings; verify acceptance iff HTTPS scheme and passes SSRF allowlist
    - **Validates: Requirements 19.4**

  - [x]* 3.4 Write unit tests for OAuth2PasswordGrantPayload
    - Test rejects non-HTTPS token_url
    - Test rejects empty credential_fields
    - Test defaults token_response_path to $.access_token
    - Test accepts arbitrary field names in credential_fields
    - Test SSRF check rejects private IPs and loopback
    - _Requirements: 19.2, 19.4, 19.5, 19.6_

- [x] 4. Checkpoint - Ensure all Python tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Template API endpoints (Python)
  - [x] 5.1 Implement GET /v1/service-templates list endpoint
    - Create or replace `apps/admin-api/src/admin_api/api/service_templates.py`
    - Support `category` and `search` query parameters
    - Return template list with all required fields including `version`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 18.3_

  - [x] 5.2 Implement GET /v1/service-templates/{template_id} detail endpoint
    - Return full template definition including config_notes and credential_hint
    - Return 404 with `mintkey:code=template_not_found` for unknown IDs
    - _Requirements: 3.1, 3.2_

  - [x] 5.3 Implement POST /v1/tenants/{tid}/services/from-template endpoint
    - Add endpoint to existing services router at `apps/admin-api/src/admin_api/api/services.py`
    - Accept `{template_id, overrides?}` body
    - Merge template values with overrides
    - Delegate to existing service creation flow (audit, change-channel, RLS)
    - Record `template_id` as metadata on the created service
    - Return 404 for unknown template_id, 409 for duplicate name, 422 for SSRF violation
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 23.5_

  - [x]* 5.4 Write integration tests for template API endpoints
    - Test GET /v1/service-templates returns all 13 templates
    - Test GET with category filter returns correct subset
    - Test GET with search filter (case-insensitive)
    - Test GET /v1/service-templates/{id} returns full detail
    - Test GET /v1/service-templates/nonexistent returns 404
    - Test POST from-template creates service with template values
    - Test POST from-template with overrides applies them
    - Test POST from-template emits service.registered audit event with template_id
    - Test POST from-template emits change-channel notification
    - Test POST from-template with duplicate name returns 409
    - Test POST from-template with unknown template_id returns 404
    - _Requirements: 2.1-2.4, 3.1-3.2, 4.1-4.5_

- [x] 6. TokenExchanger (Go)
  - [x] 6.1 Implement TokenExchanger with HTTP POST and JSONPath extraction
    - Create `apps/proxy-plugin/internal/credential/exchanger.go`
    - Implement `Exchange(ctx, ExchangeRequest) (*ExchangeResult, error)`
    - POST to token_url with credential_fields as JSON body
    - Apply token_request_headers
    - Extract token using token_response_path (JSONPath)
    - Enforce 10-second HTTP client timeout
    - Return typed errors: ErrTokenExchangeFailed, ErrTokenEndpointUnreachable, ErrTokenParseFailed
    - _Requirements: 20.1, 20.2, 20.3, 20.5, 20.6, 20.7_

  - [ ]* 6.2 Write property test for token exchange request construction (Property 4)
    - **Property 4: Token exchange request construction**
    - Generate arbitrary credential_fields and token_request_headers
    - Verify POST body is JSON encoding of credential_fields and all headers are present
    - Use `pgregory.net/rapid`
    - **Validates: Requirements 20.2**

  - [ ]* 6.3 Write property test for JSONPath token extraction (Property 5)
    - **Property 5: JSONPath token extraction**
    - Generate arbitrary JSON response bodies with known string values at known paths
    - Verify extraction returns exactly that string value
    - Use `pgregory.net/rapid`
    - **Validates: Requirements 20.3**

  - [ ]* 6.4 Write property test for non-2xx error mapping (Property 6)
    - **Property 6: Non-2xx status maps to 502**
    - Generate arbitrary HTTP status codes outside 2xx range
    - Verify ErrTokenExchangeFailed is returned
    - Use `pgregory.net/rapid`
    - **Validates: Requirements 20.5**

  - [ ]* 6.5 Write unit tests for TokenExchanger
    - Test ErrTokenEndpointUnreachable on connection timeout
    - Test ErrTokenEndpointUnreachable on DNS failure
    - Test HTTP client has 10-second timeout configured
    - _Requirements: 20.6, 20.7_

- [x] 7. TokenCache (Go)
  - [x] 7.1 Implement TokenCache with Get, Put, and DetermineExpiry
    - Create `apps/proxy-plugin/internal/cache/token_cache.go`
    - Implement thread-safe cache keyed by (tenant_id, service_id) using sync.RWMutex
    - Implement `Get(tenantID, serviceID)` returning token if expiry > 30s in future
    - Implement `Put(tenantID, serviceID, token, expiresAt)`
    - Implement `DetermineExpiry(token, responseBody)` with priority: JWT exp → expires_in → 300s default
    - No persistence — empty on restart
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6_

  - [x]* 7.2 Write property test for cache keyed retrieval (Property 7)
    - **Property 7: Cache keyed retrieval**
    - Generate arbitrary (tenant_id, service_id) pairs with stored tokens
    - Verify retrieval by specific key returns only that key's token
    - Use `pgregory.net/rapid`
    - **Validates: Requirements 21.1**

  - [x]* 7.3 Write property test for expiry detection priority chain (Property 8)
    - **Property 8: Expiry detection priority chain**
    - Generate tokens (valid JWT with exp, non-JWT) and response bodies (with/without expires_in)
    - Verify priority: JWT exp → expires_in → 300s default
    - Use `pgregory.net/rapid`
    - **Validates: Requirements 21.2**

  - [x]* 7.4 Write property test for cache hit/refresh threshold (Property 9)
    - **Property 9: Cache hit/refresh threshold at 30 seconds**
    - Generate cached tokens with various expiry times
    - Verify Get returns token iff expiry > 30s in future, else signals miss
    - Use `pgregory.net/rapid`
    - **Validates: Requirements 21.3, 21.4**

  - [x]* 7.5 Write unit tests for TokenCache
    - Test cache is empty on construction
    - Test no persistence (memory-only)
    - _Requirements: 21.5, 21.6_

- [x] 8. Checkpoint - Ensure all Go tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Proxy Plugin integration — orchestration and injection
  - [x] 9.1 Implement Injector enhancement for oauth2_password_grant
    - Edit `apps/proxy-plugin/internal/credential/injector.go`
    - Add case for `AuthSchemeOAuth2PasswordGrant` that sets `Authorization: Bearer <token>`
    - _Requirements: 20.4_

  - [x] 9.2 Implement egress handler orchestration (cache → exchange → inject → audit)
    - Wire the flow in the egress handler: retrieve credential from vault → check cache → exchange if miss → cache result → inject → emit audit
    - Implement graceful degradation: use cached token if refresh fails and token not yet expired
    - Return 502 only after cached token fully expired
    - _Requirements: 20.1, 20.4, 21.3, 21.4, 21.7_

  - [x] 9.3 Implement token.exchanged audit event emission
    - Define `TokenExchangedEvent` struct with tenant_id, service_id, agent_id, token_url_host (host only), success, latency_ms
    - Emit after every exchange attempt (success or failure)
    - Ensure no credential_fields values or token values in the event
    - _Requirements: 22.1, 22.2, 22.3, 22.7_

  - [ ]* 9.4 Write property test for graceful degradation (Property 10)
    - **Property 10: Graceful degradation on refresh failure**
    - Generate scenarios with failed refresh + cached token at various expiry states
    - Verify: use cached token if not expired, return 502 only after full expiry
    - Use `pgregory.net/rapid`
    - **Validates: Requirements 21.7**

  - [ ]* 9.5 Write property test for audit event completeness and host-only redaction (Property 11)
    - **Property 11: Audit event completeness and host-only redaction**
    - Generate arbitrary token_urls; verify emitted event contains only hostname (no path, no query)
    - Verify all required fields present: tenant_id, service_id, agent_id, success, latency_ms
    - Use `pgregory.net/rapid`
    - **Validates: Requirements 22.1**

  - [ ]* 9.6 Write property test for sensitive data exclusion (Property 12)
    - **Property 12: Sensitive data exclusion from all observable outputs**
    - Generate arbitrary credential_fields and tokens
    - Verify neither appears in audit events, log fields, OTel span attributes, or response headers/bodies
    - Use `pgregory.net/rapid`
    - **Validates: Requirements 22.2, 22.3, 22.6, 22.7**

  - [ ]* 9.7 Write integration tests for full OAuth2 password grant flow
    - Test full flow: vault stores credential → proxy retrieves → exchanges → injects Bearer
    - Test cache prevents redundant exchanges within TTL
    - Test refresh triggers new exchange when near-expiry
    - Test audit event emitted with correct fields
    - Use testcontainers-go for vault/token-endpoint mocks
    - _Requirements: 20.1-20.7, 21.1-21.7, 22.1_

- [x] 10. Credential storage round-trip (Go + Python)
  - [x] 10.1 Implement Vault Adapter support for oauth2_password_grant credential storage
    - Ensure PutCredential accepts JSON-encoded OAuth2PasswordGrantCredential payload for auth_scheme=8
    - Ensure GetCredential returns the same JSON structure
    - Enforce gRPC scope `vault.read` for credential retrieval
    - _Requirements: 19.3, 22.5_

  - [ ]* 10.2 Write property test for credential storage round-trip (Property 2)
    - **Property 2: Credential storage round-trip**
    - Generate arbitrary valid OAuth2PasswordGrantCredential payloads
    - Store via PutCredential, retrieve via GetCredential, verify JSON-decoded structure is identical
    - Use `pgregory.net/rapid`
    - **Validates: Requirements 19.3**

- [x] 11. Checkpoint - Ensure all Go and Python tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Admin UI — Enhanced Template Browser (Node)
  - [x] 12.1 Enhance ServiceTemplatePicker with category grouping and search
    - Edit components in `apps/admin-ui/src/components/`
    - Add category grouping with collapsible sections
    - Add search input filtering by name/display_name/description
    - Add template detail panel showing config_notes and version
    - Pre-fill service registration form on template selection
    - Call `POST /v1/tenants/{tid}/services/from-template` on submit
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

  - [ ]* 12.2 Write vitest tests for Admin UI template browser
    - Test template browser renders category groups
    - Test search input filters templates
    - Test template selection pre-fills service form
    - Test submit calls from-template endpoint
    - _Requirements: 17.1-17.4_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1-12)
- Unit tests validate specific examples and edge cases
- Go PBT uses `pgregory.net/rapid`; Python PBT uses `hypothesis`
- Implementation order respects dependency constraints: proto → vault → catalog → APIs → proxy → UI
- The template catalog (Requirements 1-18) has no PBT — it's static CRUD over seed data
- OAuth2 Password Grant (Requirements 19-23) has 12 correctness properties tested with PBT

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["2.2", "2.3", "3.1"] },
    { "id": 2, "tasks": ["2.4", "3.2", "3.3", "3.4"] },
    { "id": 3, "tasks": ["5.1", "5.2", "5.3", "6.1"] },
    { "id": 4, "tasks": ["5.4", "6.2", "6.3", "6.4", "6.5", "7.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "7.4", "7.5", "9.1"] },
    { "id": 6, "tasks": ["9.2", "9.3", "10.1"] },
    { "id": 7, "tasks": ["9.4", "9.5", "9.6", "9.7", "10.2"] },
    { "id": 8, "tasks": ["12.1"] },
    { "id": 9, "tasks": ["12.2"] }
  ]
}
```
