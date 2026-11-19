# Questions — audit-queue-durable-fix-1

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
| Q-001 | answered | 1.1 | ambiguous | Base TestDeadLetterMetrics (500 -> dead-letter) contradicts criterion C-f33bec22 and Q-002 (500 -> retried, no dead-letter) |
<!-- l4:index:end -->

---

## Q-001: Base TestDeadLetterMetrics (500 -> dead-letter) contradicts criterion C-f33bec22 and Q-002 (500 -> retried, no dead-letter)

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): The head test at packages/go/auditq/compact_test.go:328-358 already uses 422 and the committed isRejected (queue.go:809) retries 500, matching spec requirement "An event the sink refuses goes to the dead-letter file on its first answer" and design D3. The base version of the test is not in the workt
- **Blocking tasks:** 1.1
- **Kind:** ambiguous
- **Asked:** 2026-10-26T22:57Z by deepseek, run r-20261026T2243Z-71a7, task 1.1

### Context
packages/go/auditq/compact_test.go at the unit's base returns HTTP 500 and waits (up to 30 s) for DeadLetterTotal() == 3 and <wal>.dead to exist. The unit's criterion C-f33bec22, design D3 and the answer to Q-002 require every status other than 400/413/422 (explicitly including 500, 502, 503 and 504) to be retried with no dead-letter record, and the committed queue.go implements exactly that. The head version of the same test already uses 422, but the verifier's pre-existing-test check reverts the unit's five test files to base, so it fails deterministically with 'dead-letter counter: want 3 got 0' after 30 s. A fix chore may not change test or test-support files (any edit is put back), and adding a bounded give-up for 5xx in production code would contradict Q-002/D3. The current gate (`CI=true GITHUB_ACTIONS=true sh .l4/gates/test.sh`) passes on the head test files. Which resolution do you want: a person commits the head compact_test.go change (500 -> 422) on the unit branch so the old test is superseded, or the retry requirement is relaxed so 5xx eventually dead-letters after a bounded time?

### Options
1. A person commits the head TestDeadLetterMetrics change (500 -> 422) on the unit branch and treats the base test as superseded.
2. Relax C-f33bec22/Q-002/D3 so a 5xx answer dead-letters the event after a bounded retry period, and update the design accordingly.

### Answer
<!-- write below this line -->
Option 1. The reviewed spec settles it: criterion C-f33bec22, design D3 and the answer to Q-002 make only 400, 413 and 422 a refusal and retry every other status, 500 included, with no dead-letter record. The base TestDeadLetterMetrics (packages/go/auditq/compact_test.go), which answered 500 and waited for retries to run out, tests the behaviour this change removes, so it is superseded. A person's commit (35dea71, by the owner's delegate) is now the last change to compact_test.go: the sink answers 422 and the comment says why, which clears the pre-existing-test blocker (L4-IMP-081). The fix chore changes no test file and no production code for this finding. Option 2 is rejected: a bounded give-up for 5xx would drop events during a long outage, which the change exists to prevent.
