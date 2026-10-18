# OAuth2 Client-Credentials Auth

## ADDED Requirements

### Requirement: Proxy exchanges client credentials for a bearer token
The egress proxy SHALL, for a credential with `auth_scheme` `oauth2_client_credentials` whose stored payload is JSON containing a non-empty `token_url`, perform an OAuth 2.0 client-credentials token exchange and inject the resulting access token as `Authorization: Bearer <token>` on the upstream request. The exchange MUST POST `grant_type=client_credentials` (plus `scope` when present) as `application/x-www-form-urlencoded`, authenticate with HTTP Basic `client_id:client_secret`, and extract the token via `token_response_path` (default `$.access_token`). The agent MUST NOT send its own upstream `Authorization` header; the proxy strips it.

#### Scenario: Service Account call injects an exchanged bearer token
- **WHEN** an agent calls the proxy for a service whose credential is `oauth2_client_credentials` with `token_url` `https://cloud.mongodb.com/api/oauth/token`
- **THEN** the proxy obtains an access token from that endpoint and forwards the upstream request with `Authorization: Bearer <access_token>`, and the agent never sees the token or the client secret

#### Scenario: Exchange uses form body and Basic auth
- **WHEN** the proxy performs the token exchange
- **THEN** the request to `token_url` has `Content-Type: application/x-www-form-urlencoded`, a body of `grant_type=client_credentials` (and `scope` if configured), and an `Authorization: Basic base64(client_id:client_secret)` header

### Requirement: Exchanged tokens are cached, refreshed, and degrade gracefully
The proxy SHALL cache the exchanged token per `(tenant_id, service_id)`, reuse it while valid, coalesce concurrent cache-miss exchanges via singleflight, and on a failed refresh continue serving a not-yet-fully-expired cached token. This reuses the existing password-grant cache/singleflight/degradation machinery; the password-grant path is unchanged.

#### Scenario: Token reused within its lifetime
- **WHEN** two agent calls arrive for the same service within the token's validity window
- **THEN** the proxy performs at most one token exchange and reuses the cached token for the second call

#### Scenario: Concurrent misses coalesce
- **WHEN** multiple requests for the same `(tenant_id, service_id)` miss the cache simultaneously
- **THEN** exactly one upstream token exchange fires and all waiters share its result

### Requirement: Client-credentials payloads are validated without echoing secrets
The Admin REST API SHALL validate an `oauth2_client_credentials` credential at registration: `token_url` must be HTTPS and pass the forbidden-destination (SSRF) check, and `client_id`/`client_secret` must be non-empty. On validation failure the response MUST NOT contain any submitted credential value.

#### Scenario: Non-HTTPS token_url is rejected
- **WHEN** an operator registers an `oauth2_client_credentials` credential whose `token_url` is not HTTPS or resolves to a private/loopback address
- **THEN** the API returns a 4xx error and the response body contains no `client_secret` or other submitted value

#### Scenario: Valid Service Account credential is accepted
- **WHEN** an operator registers a credential with HTTPS `token_url`, non-empty `client_id` and `client_secret`
- **THEN** the API stores the encrypted canonical envelope via the Vault Adapter and returns metadata only
