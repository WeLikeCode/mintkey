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
| Q-001 | answered | 1.1, 2.1, 3.1 | ambiguous | The stack-level acceptance (concurrency 16 at the stock 128m limit, wrong-token callers) is a perso… |
<!-- l4:index:end -->

---

## Q-001: The stack-level acceptance (concurrency 16 at the stock 128m limit, wrong-token callers) is a perso…

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
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
Yes: the stack-level acceptance (300 proxied calls at concurrency 16 against the vault adapter at its stock 128m compose limit, and 16 parallel wrong-token callers for 60 s without a restart) is not part of this unit's tasks or gates. It is a person's check after the merge, as the proposal's Impact section states and the tasks file requires (no test may need Docker or a network beyond 127.0.0.1). The three tasks proceed as written: their tests prove the per-call bound the stack-level check rests on, namely under 1 MiB of allocation for thirty validations and five registrations, one accepted connection for sequential and concurrent GetCredential calls, and package initialisation under 32 MiB in the broker. Do not add a Docker-based or compose-based test, and do not change the compose files' 128m limit; nothing in the spec, proposal or design asks for either.
