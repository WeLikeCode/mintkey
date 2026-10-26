# Questions — token-request-scope-claims

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
| Q-001 | answered | 1.1, 2.1, 3.1 | ambiguous | Whether the MCP server should later derive `path_prefix` from a grant's `request_path_prefix` const… |
<!-- l4:index:end -->

---

## Q-001: Whether the MCP server should later derive `path_prefix` from a grant's `request_path_prefix` const…

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the reply was discarded: checked spec:spec.md#requirement-the-mcp-server-passes-the-limits-to-the-broker does not resolve
- **Blocking tasks:** 1.1, 2.1, 3.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
Whether the MCP server should later derive `path_prefix` from a grant's `request_path_prefix` constraint (enforced
today only on the classical-key path) is left to its own change.

Listed under "Open questions" in design.md.
Open-question-hash: f2054b5dfdd00d2a

### Answer
<!-- write below this line -->
None that block. Deriving path_prefix from a grant's request_path_prefix constraint is out of scope for this unit and is left to its own change, as design.md says. In this unit the MCP server only forwards the methods and path_prefix the caller gives (specs/token-scope-claims/spec.md, requirement 'The MCP server passes the limits to the broker'). Implement the tasks as written. (Answered by the owner's delegate.)
