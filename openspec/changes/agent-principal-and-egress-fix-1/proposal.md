# Proposal: fix 1 for agent-principal-and-egress

## Why
The verifier found problems in `agent-principal-and-egress` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-6eb0cc43 (major): an inline suppression was not declared: tests/unit/admin_api/test_agent_role_refusal.py:32 # noqa: E402, tests/unit/admin_api/test_agent_role_refusal.py:33 # noqa: E402, tests/unit/admin_api/test_agent_role_refusal.py:38 # noqa: E402. Remove each comment by fixing what it hides; declare one only if it cannot be removed

## Impact
The code and the tests of `agent-principal-and-egress`.
