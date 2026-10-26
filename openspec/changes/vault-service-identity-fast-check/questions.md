# Questions — vault-service-identity-fast-check

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
| Q-001 | open | 1.1, 2.1, 3.1 | ambiguous | The stack-level acceptance (concurrency 16 at the stock 128m limit, wrong-token callers) is a perso… |
<!-- l4:index:end -->

---

## Q-001: The stack-level acceptance (concurrency 16 at the stock 128m limit, wrong-token callers) is a perso…

- **Status:** open
- **Blocking tasks:** 1.1, 2.1, 3.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
The stack-level acceptance (concurrency 16 at the stock 128m limit, wrong-token callers) is a person's check after
the merge, since the gates have no Docker.

Listed under "Open questions" in design.md.
Open-question-hash: 871abf1b08a3741c

### Answer
<!-- write below this line -->
