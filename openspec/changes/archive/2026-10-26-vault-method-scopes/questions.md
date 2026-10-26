# Questions — vault-method-scopes

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
| Q-001 | answered | 1.1, 2.1 | ambiguous | None that block. The tenant check on the caller (an identity reads every tenant's credentials) is a… |
<!-- l4:index:end -->

---

## Q-001: None that block. The tenant check on the caller (an identity reads every tenant's credentials) is a…

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
- **Blocking tasks:** 1.1, 2.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
None that block. The tenant check on the caller (an identity reads every tenant's credentials) is a separate concern.

Listed under "Open questions" in design.md.
Open-question-hash: d5b97cdffa1f2101

### Answer
<!-- write below this line -->
This entry is not an open question: the design's Open questions section says nothing blocks, and the proposal's Impact section lists tenant checks on the caller as out of scope for this change, stating that an identity with vault.read still reads any tenant's credential after it. Tasks 1.1 and 2.1 proceed exactly as the spec, design and tasks describe. Do not add a tenant check on the caller to the interceptor, the handlers or the method table, and do not change the behaviour that a scoped identity reads credentials of any tenant; that remains a separate change to be proposed on its own.
