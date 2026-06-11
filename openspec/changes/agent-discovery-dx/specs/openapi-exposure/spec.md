# OpenAPI Exposure

## ADDED Requirements

### Requirement: get_openapi implements the contracted url and inline modes
`mintkey_get_openapi` SHALL return the discriminated response already defined in tools.yaml: `kind: url` with the registered `openapi_url`, or `kind: inline` with the fetched spec content when the agent requests inline and the document is within the size cap (1 MiB). Fetches MUST use and update the existing `services.openapi_etag` for conditional requests. When no URL is registered the tool returns an explicit `not_registered` status — not a bare null.

#### Scenario: Inline fetch within cap
- **WHEN** a service has a reachable `openapi_url` under 1 MiB and the agent requests inline
- **THEN** the response is `kind: inline` with the spec content and the stored etag is used/updated

#### Scenario: Unregistered spec is explicit
- **WHEN** a service has no `openapi_url`
- **THEN** the response carries status `not_registered` and a hint that the operator can set it at service registration

#### Scenario: Upstream failure is distinguishable
- **WHEN** the registered URL is unreachable or oversized
- **THEN** the response carries status `fetch_failed` (with the url still included) and the tool does not error the whole call

### Requirement: describe_service reports OpenAPI availability
`mintkey_describe_service` SHALL include an `openapi` object with `status` (`available` / `not_registered` / `fetch_failed`-from-last-attempt) and the `url` when registered, so agents know whether `get_openapi` is worth calling.

#### Scenario: Availability surfaced before fetching
- **WHEN** an agent describes a service whose operator registered an `openapi_url`
- **THEN** the response's `openapi.status` is `available` with the URL, without the describe call itself fetching the document

### Requirement: Operators are told to register OpenAPI URLs
Service-registration documentation (HOW-TO) SHALL instruct operators to set `openapi_url`, and the admin-api service-registration response is unchanged (the column already exists). No schema change.

#### Scenario: Documentation names the field and effect
- **WHEN** an operator reads the HOW-TO service-registration section
- **THEN** it states that setting `openapi_url` makes the spec discoverable to agents via `describe_service` and `get_openapi`
