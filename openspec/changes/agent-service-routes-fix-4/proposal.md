# Proposal: fix 4 for agent-service-routes

## Why
Requested by CiprianSpot, 2026-11-27T23:02:12Z in FB-002 (behaviour): Today the check runs after set_tenant_context (create) or after the FOR UPDATE (update), so a slow resolver holds a pooled connection, and resolve_host has no timeout.

The verifier found problems in `agent-service-routes` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-ba544c61 (major): FB-002 not addressed: not in this part: the resolver timeout is in egress.py (part 2). This part...

## Impact
The code and the tests of `agent-service-routes`.
