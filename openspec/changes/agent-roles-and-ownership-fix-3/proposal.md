# Proposal: fix 3 for agent-roles-and-ownership

## Why
Requested by CiprianSpot, 2026-11-27T05:05:11Z in FB-001 (behaviour): transfer_service_ownership answers with the row it selected before its UPDATE, so the body still shows the previous owner, the previous updated_at and current_key_version 0 (the transfer SELECT lacks the key-version subquery). The role PATCH patches only role into the old row, so its updated_at is the previous one. Build both answers from the stored state after the update (for example select the row again in the same transaction). In _service_row_to_dict, read row.current_key_version again instead of getattr(..., 0), so a SELECT without that column fails instead of answering 0.

The verifier found problems in `agent-roles-and-ownership` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-c49d6468 (major): FB-001 not addressed: The diff re-selects after the UPDATE in services.py and agents.py. Nothing...

## Impact
The code and the tests of `agent-roles-and-ownership`.
