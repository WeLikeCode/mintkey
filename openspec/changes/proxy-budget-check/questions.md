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
| Q-001 | open | 1.1 | ambiguous | The SQL (the grant lookup, the counter upsert under row-level security with `set_config`) is checke… |
| Q-002 | open | 1.1 | ambiguous | That `mintkey_app` holds `SELECT, INSERT, UPDATE` on `budget_counters` is inferred from `019-grants… |
<!-- l4:index:end -->

---

## Q-001: The SQL (the grant lookup, the counter upsert under row-level security with `set_config`) is checke…

- **Status:** open
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
---

## Q-002: That `mintkey_app` holds `SELECT, INSERT, UPDATE` on `budget_counters` is inferred from `019-grants…

- **Status:** open
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
