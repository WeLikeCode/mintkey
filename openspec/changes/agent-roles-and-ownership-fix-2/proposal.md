# Proposal: fix 2 for agent-roles-and-ownership

## Why
Requested by CiprianSpot, 2026-11-27T05:05:11Z in FB-001 (behaviour): transfer_service_ownership answers with the row it selected before its UPDATE, so the body still shows the previous owner, the previous updated_at and current_key_version 0 (the transfer SELECT lacks the key-version subquery). The role PATCH patches only role into the old row, so its updated_at is the previous one. Build both answers from the stored state after the update (for example select the row again in the same transaction). In _service_row_to_dict, read row.current_key_version again instead of getattr(..., 0), so a SELECT without that column fails instead of answering 0.

Requested by CiprianSpot, 2026-11-27T05:05:12Z in FB-002 (behaviour): update_agent_role writes the path id as given into the payload; service.ownership_transferred already converts with db_uuid_to_wire, and agent.role.changed should do the same.

The verifier found problems in `agent-roles-and-ownership` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-f0928bd4 (major): Feedback FB-001 (behaviour): The transfer and role answers show the state after the change
- F-10d2d4d0 (major): Feedback FB-002 (behaviour): agent.role.changed names the agent in its wire form

## Impact
The code and the tests of `agent-roles-and-ownership`.
