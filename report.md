# Delivery plan hardening

- Status: stopped
- Repository: https://github.com/WeLikeCode/mintkey
- Target: staging at cd7f5e7cb59b4187ea03e78b0511d4983a2252e3
- Merge: auto
- No promotion target is set. Promotion was not performed.
- Written: 2026-10-26T06:33:09Z
- Stopped: unit_escalated (openspec:vault-method-scopes): round 3 failed the same way as round 2: finding F-2813828d

## Units

### openspec:broker-service-token-required
- Result: integrated at 7881e9190adf933ddd6a17bffed5d47a741b8aca
- Pull request: 371
- Merge commit: 7881e9190adf933ddd6a17bffed5d47a741b8aca
- Post-merge check: pass with profile all (13 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $2.00, 2 run(s), 1 attempt(s)

### openspec:vault-service-identity-fast-check
- Result: integrated at 54368c1145d71340de9ae5a8fa3fed8ccf52feeb
- Pull request: 373
- Merge commit: 54368c1145d71340de9ae5a8fa3fed8ccf52feeb
- Post-merge check: pass with profile all (13 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $2.06, 2 run(s), 1 attempt(s)

### openspec:vault-method-scopes
- Result: not integrated
- Pull request: <forge>/WeLikeCode/mintkey/pull/375
- Merge commit: none
- Post-merge check: not run
- Usage: $2.71, 3 run(s), 1 attempt(s)
- Delegate decisions:
  - Q-001 (ambiguous): answer by the delegate (claude-fable-5-1 via claude-code), $0.93
  - vault-method-scopes-fix-1/Q-001 (ambiguous): escalated by the delegate (claude-fable-5-1 via claude-code), $1.19: The project documents settle the behaviour, not the blocker. design.md D3/D9, proposal.md "Changed tests" and tasks.md 1.1 all say TestGRPCValidateServiceIdentity_MissingToken is changed in place to expect PermissionDenied, and head grpc.go:139-141 refuses missing metadata with PermissionDenied for

### openspec:proxy-revocation-enforced
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### openspec:token-request-scope-claims
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### openspec:audit-chain-verifiable
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### openspec:audit-queue-durable
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### openspec:proxy-budget-check
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### openspec:proxy-data-plane-paths
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### openspec:service-token-files
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

## Batches

- p0-auth (profile none): not checked
- p1-proxy-audit (profile none): not checked
- p2-cleanup (profile none): not checked

## Usage

- Cost: $11.17
- Of which the readiness review: $4.39
- Runs that dispatched a unit: 7
