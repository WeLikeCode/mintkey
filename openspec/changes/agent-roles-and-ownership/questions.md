# Questions — agent-roles-and-ownership

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
| Q-001 | open | 1.1, 2.1, 3.1, 3.2, 4.1, 5.1 | ambiguous | Scenarios "the contract lists both events" and "the contract names them" conflict |
<!-- l4:index:end -->

---

## Q-001: Scenarios "the contract lists both events" and "the contract names them" conflict

- **Status:** open
- **Blocking tasks:** 1.1, 2.1, 3.1, 3.2, 4.1, 5.1
- **Kind:** ambiguous
- **Asked:** intake lint (L4-ODD-004)
- **Criteria:** C-c807e49c (agent-roles-and-ownership › The new events are in the audit contract › the contract lists both events), C-29874427 (grant-expiry › The audit contract records the grantor and the expiry › the contract names them)

### Context
These two scenarios have the same GIVEN and WHEN and different THEN, so the implementer cannot satisfy both.
- agent-roles-and-ownership › The new events are in the audit contract › the contract lists both events (specs/agent-roles-and-ownership/spec.md:215)
  WHEN the schema file is loaded as JSON
  THEN both definitions exist with exactly those payload property names, the two types are keys of
- grant-expiry › The audit contract records the grantor and the expiry › the contract names them (openspec/specs/grant-expiry/spec.md:261)
  WHEN the schema file is loaded as JSON
  THEN the three definitions list those properties and that enum value, and the `required` lists they had are
Which behaviour is wanted? Answer below and set Status to answered. If one scenario is wrong, delete it from the spec on this unit branch in the same commit; a change on the base branch does not reach this unit.

### Answer
<!-- write below this line -->
