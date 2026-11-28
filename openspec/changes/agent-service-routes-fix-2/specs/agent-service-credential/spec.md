# Spec Delta

## Purpose
A publisher agent writes the credential of a service it owns and never reads it back. The credential is bound to the service's target and stored so that the proxy connects only to public addresses. The audit contract lists the events these routes write.

## ADDED Requirements

### Requirement: The target check of an agent-supplied URL is bounded in time and holds no database connection — feedback FB-002
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: The target check of an agent-supplied URL is bounded in time and holds no database connection
- **WHEN** an agent creates or updates a service whose base_url or openapi_url names a host that resolves slowly or not at all
- **THEN** the check finishes within a bounded time and answers mintkey:target_not_allowed (unresolvable) when it runs out, and the request holds no database connection or transaction while it waits for the resolver
