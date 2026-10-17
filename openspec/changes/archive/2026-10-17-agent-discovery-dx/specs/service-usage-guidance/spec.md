# Service Usage Guidance

## ADDED Requirements

### Requirement: Every auth scheme has an agent-facing injection hint
The system SHALL maintain a single injection-hint table covering every `AuthScheme` enum value, derived from the proxy-plugin's actual injection behavior. For each scheme the hint MUST state: what the proxy injects and where (header/query/connection), what the agent must NOT send (its own upstream auth), and — for schemes not handled by the HTTP proxy (SSH, email) or not implemented (mtls) — which surface handles them instead. `mintkey_discover` SHALL include the matching hint in each service's `how_to_call.injection_hint`.

#### Scenario: Bearer-token service carries a concrete hint
- **WHEN** an agent calls `mintkey_discover` and a granted service has `auth_scheme: bearer_token`
- **THEN** that service's `how_to_call.injection_hint` states the proxy sets `Authorization: Bearer <secret>` and that the agent must not send its own upstream Authorization header

#### Scenario: Enum coverage is enforced
- **WHEN** the auth-scheme parity test runs against the `AuthScheme` enum in vault.proto
- **THEN** it fails if any enum value lacks an entry in the injection-hint table

#### Scenario: Unimplemented scheme is honest
- **WHEN** an agent discovers a service with `auth_scheme: mtls`
- **THEN** the injection hint states mTLS is not implemented by the proxy and the call will fail, rather than implying it works

### Requirement: describe_service returns what the bootstrap promises
`mintkey_describe_service` SHALL return `auth_scheme_details` (injection point, header or query-param name, value format), `your_constraints` (the calling agent's rate limit, time window, request path prefixes, and source-IP allowlist from its permission grant, each null when unset), and `explicit_proxy_url` (the concrete `{proxy_base}/v1/call/{service_id}` URL). The agent-bootstrap markdown MUST NOT document any response field that the implementation does not return.

#### Scenario: Constraints reflect the calling agent's grant
- **WHEN** agent A has a permission grant with a rate limit on service S and calls `describe_service` for S
- **THEN** the response's `your_constraints.rate_limit` matches A's grant, and an agent with no constraints receives explicit nulls

#### Scenario: Bootstrap-vs-reality parity gate
- **WHEN** the bootstrap parity test extracts response field names promised in agent-bootstrap.md for discovery tools
- **THEN** every promised field is present in the corresponding tool's actual response model, and the test fails on any drift

### Requirement: Discovery surfaces form one linked path
The unauthenticated landing page SHALL point a fresh agent to bootstrap; bootstrap SHALL describe the list → describe → token → call sequence using only fields that exist; `list_services` SHALL state (in its `hint` or per-item) that `describe_service` provides usage detail. An agent following only on-wire hints — never reading repo source or external docs — MUST be able to complete a first successful proxied call.

#### Scenario: Cold-start agent self-serves a first call
- **WHEN** an agent with only an `mk_agent_` key and the MCP base URL follows the landing → bootstrap → discover → request_token → proxy-call chain in a live stack
- **THEN** each step's response names the next step, and the final proxied call succeeds without the agent consulting anything outside the responses
