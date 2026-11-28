# Proposal: fix 1 for agent-service-routes

## Why
Requested by CiprianSpot, 2026-11-27T23:02:12Z in FB-001 (behaviour): Today every Bearer mk_agent_* string, of any length, reaches a full Argon2id verify through the same module-level semaphore (4 slots) that /v1/internal/validate-agent-key uses, so a burst on /v1/agent/ queues the MCP server's key checks behind it.

Requested by CiprianSpot, 2026-11-27T23:02:12Z in FB-002 (behaviour): Today the check runs after set_tenant_context (create) or after the FOR UPDATE (update), so a slow resolver holds a pooled connection, and resolve_host has no timeout.

Requested by CiprianSpot, 2026-11-27T23:02:13Z in FB-003 (behaviour): The event is emitted with target_type credential while the definition this unit adds requires service.

Requested by CiprianSpot, 2026-11-27T23:02:13Z in FB-004 (behaviour): Today an over-long display_name reaches the database and raises a DataError (500), and {"description": null} answers 200 with no change.

The verifier found problems in `agent-service-routes` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-f9d5c71b (major): Feedback FB-001 (behaviour): Unknown agent keys on the agent routes cannot slow the MCP server's...
- F-c16d7dab (major): Feedback FB-002 (behaviour): The target check of an agent-supplied URL is bounded in time and hol...
- F-5af045b0 (major): Feedback FB-003 (behaviour): service.credential.set matches its schema
- F-aa8d250f (major): Feedback FB-004 (behaviour): Invalid field values answer 422, never 500 or a silent 200

## Impact
The code and the tests of `agent-service-routes`.
