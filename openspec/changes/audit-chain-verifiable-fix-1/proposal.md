# Proposal: fix 1 for audit-chain-verifiable

## Why
The verifier found problems in `audit-chain-verifiable` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-0b7e7198 (major): task 2.1: tests/unit/audit_verify/test_chain_verify.py set-up not changed: Decided by delegate in Q-005: The finding holds. Task 2.1 is ticked but the existing verify-job chain test file was not changed: its _build_chain still builds each AuditEvent from id, event_type, tenant_id, payload, hash and prev_hash only, so at stays None, and the rewritten verify.py raises ValueError("event has no at") from _chain_event, which compute_event_hash calls on the first event of every chain. The file also does not put packages/python/mintkey-models on sys.path itself, as task 2.1 requires, although the shared tests/conftest.py does so when it is collected through pytest from the repository. All four chain tests in that file therefore fail at set-up, and the task's own instruction (only the set-up changes: add the mintkey-models path, pass at=datetime(2026, 1, 1, tzinfo=timezone.utc) to each AuditEvent, test bodies stay) was not carried out. WHEN tests/unit/audit_verify/test_chain_verify.py is run against the rewritten verify.py THEN its set-up puts packages/python/mintkey-models on sys.path and _build. Task 2.1 requires putting mintkey-models on sys.path and passing at=datetime(...

## Impact
The code and the tests of `audit-chain-verifiable`.
