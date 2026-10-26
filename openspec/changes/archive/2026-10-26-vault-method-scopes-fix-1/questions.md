# Questions — vault-method-scopes-fix-1

<!-- l4:questions v1
How to answer: write under "### Answer" and set **Status** to `answered`.
To accept the clarifier's suggestion as-is, set **Status** to `accepted`.
Status values: open · answered · accepted · answered-by-clarifier · dismissed · superseded
Kind values: technical · product · ambiguous · verdict · harness. For a `verdict` question, start the answer with `accept` or
`reject`, then give your reason; for a `harness` question, with `accept` or `retry`.
Do not change question IDs. Commit and push to the l4/… branch to resume the run. -->

<!-- l4:index:start -->
| ID | Status | Blocking | Kind | Question |
|----|--------|----------|------|----------|
| Q-001 | answered | 1.1 | ambiguous | Pre-existing ValidateServiceIdentity test contradicts the new requirement |
<!-- l4:index:end -->

---

## Q-001: Pre-existing ValidateServiceIdentity test contradicts the new requirement

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): The project documents settle the behaviour, not the blocker. design.md D3/D9, proposal.md "Changed tests" and tasks.md 1.1 all say TestGRPCValidateServiceIdentity_MissingToken is changed in place to expect PermissionDenied, and head grpc.go:139-141 refuses missing metadata with PermissionDenied for
- **Blocking tasks:** 1.1
- **Kind:** ambiguous
- **Asked:** 2026-10-26T05:31Z by deepseek, run r-20261026T0313Z-8028, task 1.1

### Context
At base cd7f5e7, TestGRPCValidateServiceIdentity_MissingToken (apps/vault-adapter/internal/server/grpc_test.go) calls ValidateServiceIdentity through newTestGRPCServerWithAuth, which installs scopeInterceptor, and asserts codes.Unauthenticated. The spec's scenario C-08b38088 and the direct-interceptor test C-c547eb9c assert codes.PermissionDenied for the identical call (ValidateServiceIdentity, no metadata) through that same scopeInterceptor. The unit made the base test pass by editing it, but verification restores base test files and reports F-2813828d. Both expectations cannot hold at once: they are the same WHEN and method with different THEN, so the requirement and the pre-existing test are mutually exclusive.

### Options
1. Allow updating the pre-existing TestGRPCValidateServiceIdentity_MissingToken expectation to PermissionDenied (treat it as intentionally superseded by this change and exclude it from the base-test freeze).
2. Change the requirement/criteria so ValidateServiceIdentity without metadata keeps answering Unauthenticated (drop it from methodScopes enforcement), and update C-08b38088/C-c547eb9c/C-8c1bdc49 accordingly.
3. Keep the pre-existing test and add a production exception that only the buildGRPCServer-constructed server enforces ValidateServiceIdentity, leaving manually built servers on the old Unauthenticated path (not recommended; security behaviour then depends on construction).

### Answer
<!-- write below this line -->
Option 1. The reviewed spec settles the behaviour: proposal.md "Changed tests" and tasks.md 1.1 of vault-method-scopes (design D3 and D9) change `apps/vault-adapter/internal/server/grpc_test.go::TestGRPCValidateServiceIdentity_MissingToken` in place to expect `codes.PermissionDenied`, and change the helper `newTestSSHGRPCServer` in apps/vault-adapter/internal/server/grpc_ssh_test.go to build its server with `grpc.NewServer(grpc.UnaryInterceptor(scopeInterceptor(svc)))` and register `svcid_ssh_proxy` with `[]string{"vault.read", "vault.hostkey.put"}`. Both base-test failures are those intended changes. This answer unfreezes exactly two files for this fix task: apps/vault-adapter/internal/server/grpc_test.go and apps/vault-adapter/internal/server/grpc_ssh_test.go. In grpc_test.go, TestGRPCValidateServiceIdentity_MissingToken asserts `codes.PermissionDenied` unconditionally: remove the `methodScopes` lookup that picks the expected code at run time, and keep a comment that says why. In grpc_ssh_test.go, the helper registers exactly the two scopes above (drop `vault.put`), and TestSSHVault_GetAgentByFingerprint_MissingToken itself stays unchanged: it passes through the interceptor. Change nothing else in those two files and no other test. Options 2 and 3 are rejected: they weaken the default-deny design that this change exists for.
