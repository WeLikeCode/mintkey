# Proposal: fix 2 for audit-queue-durable

## Why
The verifier found problems in `audit-queue-durable` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-2813828d (blocker): a pre-existing test fails on the unit's code: tests.acceptance.test_async_audit_emission::test_auditq_unit_tests_pass (AssertionError: auditq unit tests failed (exit 1):)

## Impact
The code and the tests of `audit-queue-durable`.
