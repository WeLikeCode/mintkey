# Spec Delta

## Purpose
A publisher agent writes the credential of a service it owns and never reads it back. The credential is bound to the service's target and stored so that the proxy connects only to public addresses. The audit contract lists the events these routes write.

## ADDED Requirements

### Requirement: Unknown agent keys on the agent routes cannot slow the MCP server's key checks — feedback FB-001
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: Unknown agent keys on the agent routes cannot slow the MCP server's key checks
- **WHEN** requests to /v1/agent/ carry well-formed but unknown agent keys faster than they can be verified, or carry a bearer that is not mk_agent_ followed by the exact length and alphabet of a real key
- **THEN** /v1/internal/validate-agent-key is not delayed by them: the agent routes verify keys with a bounded capacity of their own, a request that finds that capacity full answers 503 mintkey:auth_unavailable at once instead of waiting, and a bearer of the wrong shape answers 401 mintkey:auth_required wit...

### Requirement: The target check of an agent-supplied URL is bounded in time and holds no database connection — feedback FB-002
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: The target check of an agent-supplied URL is bounded in time and holds no database connection
- **WHEN** an agent creates or updates a service whose base_url or openapi_url names a host that resolves slowly or not at all
- **THEN** the check finishes within a bounded time and answers mintkey:target_not_allowed (unresolvable) when it runs out, and the request holds no database connection or transaction while it waits for the resolver

### Requirement: service.credential.set matches its schema — feedback FB-003
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: service.credential.set matches its schema
- **WHEN** an agent sets the credential of a service it owns
- **THEN** the service.credential.set audit event has target_type service and target_id the service's id, and the emitted event validates against its definition in audit-event.schema.json

### Requirement: Invalid field values answer 422, never 500 or a silent 200 — feedback FB-004
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: Invalid field values answer 422, never 500 or a silent 200
- **WHEN** an agent creates or updates a service with a display_name, description, base_url or openapi_url longer than the stored column allows, an empty display_name, or a PATCH that sets a field to null
- **THEN** the answer is 422 with the agent error body naming the field, the service is unchanged, and no answer is a 500 or a 200 that changed nothing
