# HTTP Digest Auth

## ADDED Requirements

### Requirement: A new http_digest auth scheme exists across the contracts
The system SHALL define an `http_digest` auth scheme as `AUTH_SCHEME_HTTP_DIGEST = 17` in `vault.proto`, mirrored as `http_digest` in the OpenAPI `AuthScheme` enum and the MCP tools enum, with a matching Go `AuthScheme` constant. The credential payload SHALL be `{public_key, private_key}`.

#### Scenario: Enum parity holds for the new scheme
- **WHEN** the auth-scheme parity test runs against the `AuthScheme` enum in `vault.proto`
- **THEN** every value — including `http_digest` (17) — has a corresponding Go constant and an MCP injection-hint entry, and the OpenAPI snapshot includes `http_digest`

### Requirement: Proxy authenticates http_digest upstreams via RFC 2617
The egress proxy SHALL, for an `http_digest` credential, perform an HTTP Digest (RFC 2617) challenge-response against the upstream using the stored `public_key` as the username and `private_key` as the password, via a per-request Digest transport on the reverse proxy. The proxy MUST strip the agent's `Authorization` header and MUST NOT inject a static credential header; the Digest handshake supplies the upstream `Authorization`.

#### Scenario: Programmatic API Key call completes the digest handshake
- **WHEN** an agent calls the proxy for a service whose credential is `http_digest`
- **THEN** the proxy responds to the upstream's `401` Digest challenge with a computed response using the stored key pair and the upstream request succeeds, without the agent supplying any credential

#### Scenario: Agent Authorization is never forwarded
- **WHEN** an agent includes its own `Authorization` header on an `http_digest` proxy call
- **THEN** the proxy strips it before contacting the upstream

### Requirement: http_digest payloads are validated without echoing secrets
The Admin REST API SHALL validate an `http_digest` credential at registration: `public_key` and `private_key` must be non-empty. On validation failure the response MUST NOT contain any submitted credential value.

#### Scenario: Missing private key is rejected
- **WHEN** an operator registers an `http_digest` credential with an empty `private_key`
- **THEN** the API returns a 4xx error and the response body contains no submitted key material
