# Questions — audit-queue-durable

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
| Q-001 | answered | 1.1, 2.1, 3.1, 3.2 | ambiguous | The tests compress an outage of minutes into milliseconds (retry delays of 5 to 50 ms, 1,500 events… |
| Q-002 | answered | 1.1, 2.1, 3.1, 3.2 | ambiguous | Which statuses an audit sink other than admin-api (an embedding application) uses for a final refus… |
| Q-003 | answered | 1.1, 2.1, 3.1, 3.2 | ambiguous | `sh .l4/gates/lint-go.sh` (golangci-lint) was not run against the new code; the linter set may ask … |
| Q-004 | answered | none | verdict | Criterion C-fad8c50f (audit-queue › An event the sink refuses goes to the dead-letter file on its first answer › the dead-letter metrics follow refused events): accept as satisfied? |
<!-- l4:index:end -->

---

## Q-001: The tests compress an outage of minutes into milliseconds (retry delays of 5 to 50 ms, 1,500 events…

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the reply was discarded: checked .l4/gates/test.sh:44 cites a harness-written file (questions.md, verification.md, .l4/): not evidence
- **Blocking tasks:** 1.1, 2.1, 3.1, 3.2
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
The tests compress an outage of minutes into milliseconds (retry delays of 5 to 50 ms, 1,500 events); a run
against a real admin-api that is stopped for ten minutes was not made here.

Listed under "Open questions" in design.md.
Open-question-hash: d1fe919dc28f6e38

### Answer
<!-- write below this line -->
None that block. A run against a real admin-api that is stopped for ten minutes needs the compose stack, so it is a person's check after the merge, not part of this unit. This unit's acceptance is its tests, which compress the outage into short retry delays as design.md says. Implement the tasks as written. (Answered by the owner's delegate.)
---

## Q-002: Which statuses an audit sink other than admin-api (an embedding application) uses for a final refus…

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
- **Blocking tasks:** 1.1, 2.1, 3.1, 3.2
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
Which statuses an audit sink other than admin-api (an embedding application) uses for a final refusal is not
known; D3 assumes 400, 413 and 422 and retries the rest.

Listed under "Open questions" in design.md.
Open-question-hash: 2f0ecd0234c979f4

### Answer
<!-- write below this line -->
The unit's specification already settles what the code must do, so the tasks are not blocked. Implement the refusal set exactly as the requirement "An event the sink refuses goes to the dead-letter file on its first answer" states: a sink answer of 400, 413 or 422 is a refusal and goes to the dead-letter file on its first answer, a 2xx answer delivers the event, and every other status is retried without limit. The scenario "which statuses are a refusal" fixes the retried set explicitly (401, 403, 404, 409, 429, 500, 502, 503 and 504 must be retried, with no dead-letter record), so the package must not treat any other 4xx as final. What a sink other than admin-api actually answers for a final refusal is not recorded anywhere in the repository and cannot be known from it; design.md lists the refusal set under "Decisions taken without the owner" as reversible without a format change, so it stays an open note for the owner rather than something the implementation must resolve. Do not add a configuration variable or widen the set to accommodate hypothetical sinks: the spec allows only the four named drain settings and no new exported name.
---

## Q-003: `sh .l4/gates/lint-go.sh` (golangci-lint) was not run against the new code; the linter set may ask …

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the reply was discarded: checked .l4/gates/lint-go.sh:11 cites a harness-written file (questions.md, verification.md, .l4/): not evidence
- **Blocking tasks:** 1.1, 2.1, 3.1, 3.2
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
`sh .l4/gates/lint-go.sh` (golangci-lint) was not run against the new code; the linter set may ask for small
changes (for example a checked `Close` error).

Listed under "Open questions" in design.md.
Open-question-hash: a4a95d3732942618

### Answer
<!-- write below this line -->
None that block. golangci-lint is one of this repository's lint gates (gates.lint in .l4/config.yaml runs sh .l4/gates/lint-go.sh, go vet and golangci-lint over every go.work module), so it runs on the new code at every gate run of this unit; whatever it asks for (for example a checked Close error) is fixed in the step whose gate reports it. Implement the tasks as written. (Answered by the owner's delegate.)

---

## Q-004: Criterion C-fad8c50f (audit-queue › An event the sink refuses goes to the dead-letter file on its first answer › the dead-letter metrics follow refused events): accept as satisfied?

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 3, verifier
- **Criteria:** C-fad8c50f (audit-queue › An event the sink refuses goes to the dead-letter file on its first answer › the dead-letter metrics follow refused events)

### Context
Criterion C-fad8c50f (audit-queue › An event the sink refuses goes to the dead-letter file on its first answer › the dead-letter metrics follow refused events) is needs human after round 3.

Scenario:
\- **WHEN** the sink answers 422 to every request and 3 events are enqueued
\- **THEN** `DeadLetterTotal()` is 3, `DeadLetterFileSizeBytes()` equals the size of `<wal>.dead`, and each of its
  lines is JSON without the keys `credential`, `api_key`, `secret` and `token_value`

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
To set the check the fix must pass, end the reason with one sentence WHEN <the situation> THEN <the behaviour you expect>, with WHEN and THEN in capitals: it becomes a scenario of the fix unit. Without one, the fix is checked against the scenario above as it is written.

### Options
1. accept
2. reject: <reason>, then WHEN ... THEN ... to set the check

### Answer
<!-- write below this line -->
accept The criterion is satisfied as it stands. TestDeadLetterMetrics in packages/go/auditq/compact_test.go runs the scenario word for word: an httptest sink that answers 422 to every request, 3 events enqueued on a started queue with compaction disabled, then it waits until DeadLetterTotal reaches 3, fails the test with t.Fatalf when the counter is not exactly 3, stats the dead-letter file next to the WAL and fails when DeadLetterFileSizeBytes differs from its size, and decodes every line of that file as JSON, failing when a line does not parse or holds any of the keys credential, api_key, secret or token_value. The production code behind it matches the requirement: isRejected returns true for 400, 413 and 422 only, settleRejected writes the record with last_err rejected: HTTP <status> through deadLetterWAL, which appends one JSON line to <wal>.dead, adds 1 to the dead-letter counter and stores the file's size in the gauge after each append. The judge passed the criterion; the only gap was that no test was traced to it, and this test discriminates it.
