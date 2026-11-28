# Feedback — agent-service-routes

<!-- l4:feedback v1
Ask for changes here while the unit's branch is open. The easy way is `l4 feedback add` (see `l4 feedback --help`).
An item is read only when its **Status** is `submitted`; `draft` items wait and `withdrawn` items are ignored.
Kinds: refactor · duplication · tests · config · behaviour (see docs/feedback.md).
Do not change item IDs. Commit and push to the l4/… branch: the harness takes submitted items at its next
verification round, turns them into a fix unit and checks that each one was addressed. -->

<!-- l4:feedback-index:start -->
| ID | Status | Kind | Where | Feedback |
|----|--------|------|-------|----------|
| FB-001 | taken | behaviour |  | Unknown agent keys on the agent routes cannot slow the MCP server's key checks |
| FB-002 | taken | behaviour |  | The target check of an agent-supplied URL is bounded in time and holds no database connection |
| FB-003 | taken | behaviour |  | service.credential.set matches its schema |
| FB-004 | taken | behaviour |  | Invalid field values answer 422, never 500 or a silent 200 |
<!-- l4:feedback-index:end -->

---

## FB-001: Unknown agent keys on the agent routes cannot slow the MCP server's key checks

- **Status:** taken
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-27T23:02:12Z

### Feedback
Today every Bearer mk_agent_* string, of any length, reaches a full Argon2id verify through the same module-level semaphore (4 slots) that /v1/internal/validate-agent-key uses, so a burst on /v1/agent/ queues the MCP server's key checks behind it.

### When / Then
- **When:** requests to /v1/agent/ carry well-formed but unknown agent keys faster than they can be verified, or carry a bearer that is not mk_agent_ followed by the exact length and alphabet of a real key
- **Then:** /v1/internal/validate-agent-key is not delayed by them: the agent routes verify keys with a bounded capacity of their own, a request that finds that capacity full answers 503 mintkey:auth_unavailable at once instead of waiting, and a bearer of the wrong shape answers 401 mintkey:auth_required without a password-hash verification

### Outcome
<!-- written by the harness -->
Taken in round 2 into agent-service-routes-fix-1

---

## FB-002: The target check of an agent-supplied URL is bounded in time and holds no database connection

- **Status:** taken
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-27T23:02:12Z

### Feedback
Today the check runs after set_tenant_context (create) or after the FOR UPDATE (update), so a slow resolver holds a pooled connection, and resolve_host has no timeout.

### When / Then
- **When:** an agent creates or updates a service whose base_url or openapi_url names a host that resolves slowly or not at all
- **Then:** the check finishes within a bounded time and answers mintkey:target_not_allowed (unresolvable) when it runs out, and the request holds no database connection or transaction while it waits for the resolver

### Outcome
<!-- written by the harness -->
Taken in round 3 into agent-service-routes-fix-2

---

## FB-003: service.credential.set matches its schema

- **Status:** taken
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-27T23:02:13Z

### Feedback
The event is emitted with target_type credential while the definition this unit adds requires service.

### When / Then
- **When:** an agent sets the credential of a service it owns
- **Then:** the service.credential.set audit event has target_type service and target_id the service's id, and the emitted event validates against its definition in audit-event.schema.json

### Outcome
<!-- written by the harness -->
Taken in round 2 into agent-service-routes-fix-1

---

## FB-004: Invalid field values answer 422, never 500 or a silent 200

- **Status:** taken
- **Kind:** behaviour
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-27T23:02:13Z

### Feedback
Today an over-long display_name reaches the database and raises a DataError (500), and {"description": null} answers 200 with no change.

### When / Then
- **When:** an agent creates or updates a service with a display_name, description, base_url or openapi_url longer than the stored column allows, an empty display_name, or a PATCH that sets a field to null
- **Then:** the answer is 422 with the agent error body naming the field, the service is unchanged, and no answer is a 500 or a 200 that changed nothing

### Outcome
<!-- written by the harness -->
Taken in round 2 into agent-service-routes-fix-1
