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
| Q-001 | open | 1.1 | ambiguous | Pre-existing ValidateServiceIdentity test contradicts the new requirement |
<!-- l4:index:end -->

---

## Q-001: Pre-existing ValidateServiceIdentity test contradicts the new requirement

- **Status:** open
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
