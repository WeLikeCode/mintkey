# Questions — proxy-budget-check

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
| Q-001 | answered | 1.1 | ambiguous | The SQL (the grant lookup, the counter upsert under row-level security with `set_config`) is checke… |
| Q-002 | answered | 1.1 | ambiguous | That `mintkey_app` holds `SELECT, INSERT, UPDATE` on `budget_counters` is inferred from `019-grants… |
<!-- l4:index:end -->

---

## Q-001: The SQL (the grant lookup, the counter upsert under row-level security with `set_config`) is checke…

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): The open question asks for a live run on the compose stack (a grant with ceiling 2, three calls, the third answering 429, budget_counters.used = 2) and for confirmation that mintkey_app holds the needed privileges on a real database. I can only read files and cannot run the stack, so I cannot check
- **Blocking tasks:** 1.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
The SQL (the grant lookup, the counter upsert under row-level security with `set_config`) is checked in the gates
only against a fake driver. A person verifies it once on the compose stack: a grant with `ceiling` 2, three calls,
the third answers 429, and `budget_counters.used` is 2.

Listed under "Open questions" in design.md.
Open-question-hash: 2bfcc625ff2d49d0

### Answer
<!-- write below this line -->
None that block. The gates check the SQL (the grant lookup, the counter upsert under row-level security with set_config) against the fake driver; the live check on the compose stack (a grant with ceiling 2, three calls, the third answers 429, budget_counters.used is 2) is a person's check after the merge and is on the owner's list of stack checks. Task 1.1 goes ahead as specified.
---

## Q-002: That `mintkey_app` holds `SELECT, INSERT, UPDATE` on `budget_counters` is inferred from `019-grants…

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
- **Blocking tasks:** 1.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
That `mintkey_app` holds `SELECT, INSERT, UPDATE` on `budget_counters` is inferred from
`019-grants-defensive.yaml`'s default privileges; the same live check confirms it.

Listed under "Open questions" in design.md.
Open-question-hash: ebc46e7ac7244cc3

### Answer
<!-- write below this line -->
Yes: mintkey_app holds SELECT, INSERT and UPDATE (and DELETE) on budget_counters, and the repository establishes it on three independent grounds, so task 1.1 can proceed without a new grant or a new role. First, changeset 019-grants-defensive-public runs ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mintkey_app, and the compose Liquibase job runs the whole changelog as the single user mintkey_migrate, so budget_counters, created later in the same changelog by 029-budget-counters, is created by the role whose default privileges were altered and inherits the grant. Second, that changeset is runAlways: true and also executes GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mintkey_app, so every subsequent Liquibase apply re-grants on budget_counters as well; the only REVOKE in the changelogs against mintkey_app is on audit_events, none on budget_counters. Third, admin-api already connects as mintkey_app in compose and already issues INSERT ... ON CONFLICT DO UPDATE and UPDATE budget_counters SET used = 0 and SELECT ... FROM budget_counters, so the privileges are exercised in production code today. The proxy-plugin's compose DATABASE_URL uses the same mintkey_app role, which matches the proposal's statement that the existing grants give it what it needs. The live check in the design's open question stays useful as confirmation of the SQL under row-level security, but it is not needed to settle the privilege question.
