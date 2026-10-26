# Spec Delta

## Purpose
How an audit event's hash is formed from the values stored in `audit_events`, and how the verify job and the verify-chain endpoint check a tenant's chain with that same form, so that an intact chain verifies and a change to any stored field of any event is reported.

## ADDED Requirements

### Requirement: task 2.1: tests/unit/audit_verify/test_chain_verify.py set-up not changed — finding F-0b7e7198
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: task 2.1: tests/unit/audit_verify/test_chain_verify.py set-up not changed
- **WHEN** tests/unit/audit_verify/test_chain_verify.py is run against the rewritten verify.py
- **THEN** its set-up puts packages/python/mintkey-models on sys.path and _build
