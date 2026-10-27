# Questions — audit-queue-durable-fix-2

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
| Q-001 | answered | 1.1 | ambiguous | F-2813828d: the acceptance meta-test still runs the reverted base TestDeadLetterMetrics |
<!-- l4:index:end -->

---

## Q-001: F-2813828d: the acceptance meta-test still runs the reverted base TestDeadLetterMetrics

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): Every option needs something outside production code: a person committing a change to the acceptance meta-test (a test file, frozen for a fix task), a harness change to how base_tests treats superseded tests, or relaxing criterion C-f33bec22 against the specification, which requires 5xx to be retrie
- **Blocking tasks:** 1.1
- **Kind:** ambiguous
- **Asked:** 2026-10-26T23:50Z by deepseek, run r-20261026T2310Z-1139, task 1.1

### Context
At the parent base (3e404e1) packages/go/auditq/compact_test.go::TestDeadLetterMetrics answers 500 and waits 30 s for DeadLetterTotal()==3 and <wal>.dead. Criterion C-f33bec22 and the answer to Q-002 require 500 to be retried without limit, with no dead-letter record, so the base test is superseded; the human commit 35dea71 (last change to compact_test.go) makes the direct test count as human-covered, but the verifier still reverts compact_test.go to its base version (base_tests.kept_files uses only-people, and commit 50bf0da introduced the 500->422 change as a harness commit). The meta-test tests/acceptance/test_async_audit_emission.py::test_auditq_unit_tests_pass is unchanged and therefore not human-covered: it invokes `go test ./packages/go/auditq/...` without -short, so it executes the reverted base TestDeadLetterMetrics and exits 1. No production change can satisfy both that base test and C-f33bec22/Q-002, and a fix task may not edit tests. This needs a person or a harness decision.

### Options
1. A person commits a change to tests/acceptance/test_async_audit_emission.py so it is the last change to that file (base_tests.split_allowed then counts the meta-test as human-covered, as it already does for TestDeadLetterMetrics); ideally the change also stops that meta-test from requiring the superseded TestDeadLetterMetrics to pass.
2. The harness treats a meta-test that fails only because it runs a human-approved superseded test as covered (harness fix), and the fix unit is retried with no production change.
3. Reject and relax C-f33bec22/Q-002 so a 5xx dead-letters after a bounded retry (already rejected in the Q-001 answer because it would drop events during a long outage).

### Answer
<!-- write below this line -->
Option 2, done in the harness. L4 0.4.36 (pinned on staging in cdfdc23) keeps a test module whose last change in base..head is a person's commit at head for step 1's run of the base tests. 35dea71 is the last change to packages/go/auditq/compact_test.go (no harness commit after it), so the run uses the head version of that file, and tests/acceptance/test_async_audit_emission.py::test_auditq_unit_tests_pass, which runs `go test ./packages/go/auditq/...`, runs that version. Checked on this branch (fe29b70): with the unit's code, compact_test.go at head and the unit's added test files set aside, `go test ./...` in packages/go/auditq passes; with compact_test.go at its base version, TestDeadLetterMetrics fails as in round 2. No production change and no person's commit to the meta-test are needed: retry task 1.1 as it is.
