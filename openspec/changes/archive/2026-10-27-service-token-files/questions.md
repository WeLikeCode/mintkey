# Questions — service-token-files

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
| Q-001 | answered | 1.1, 2.1, 3.1, 4.1 | ambiguous | None that block. The Python services keep reading their tokens from the environment. |
<!-- l4:index:end -->

---

## Q-001: None that block. The Python services keep reading their tokens from the environment.

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
- **Blocking tasks:** 1.1, 2.1, 3.1, 4.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
None that block. The Python services keep reading their tokens from the environment.

Listed under "Open questions" in design.md.
Open-question-hash: 6d4103f998c1eff7

### Answer
<!-- write below this line -->
There is nothing to decide here. The design's Open questions section states that no question blocks the change and that the Python services keep reading their tokens from the environment; the proposal lists the Python services (admin-api, MCP server) under Out of scope for the same reason, and none of tasks 1.1 to 4.1 touches a Python file. Proceed with the tasks as written: the Go services read their tokens through svcid.FromEnv, and the admin-api and MCP server are left unchanged by this unit.
