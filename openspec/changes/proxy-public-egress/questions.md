# Questions — proxy-public-egress

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
| Q-001 | open | 1.1, 2.1, 3.1, 4.1 | ambiguous | Scenarios "the changelog adds the column" and "the changelog fills empty targets only" conflict |
<!-- l4:index:end -->

---

## Q-001: Scenarios "the changelog adds the column" and "the changelog fills empty targets only" conflict

- **Status:** open
- **Blocking tasks:** 1.1, 2.1, 3.1, 4.1
- **Kind:** ambiguous
- **Asked:** intake lint (L4-ODD-004)
- **Criteria:** C-09049412 (proxy-public-egress › The vault stores an egress scope with each credential › the changelog adds the column), C-7ac56330 (proxy-stored-target › Stored targets of existing credentials are filled from the service's base URL › the changelog fills empty targets only)

### Context
These two scenarios have the same GIVEN and WHEN and different THEN, so the implementer cannot satisfy both.
- proxy-public-egress › The vault stores an egress scope with each credential › the changelog adds the column (specs/proxy-public-egress/spec.md:19)
  WHEN the changelog file is parsed as YAML and the master changelog is read
  THEN the file holds an SQL change whose text contains `ALTER TABLE vault.credentials`, `ADD COLUMN egress_scope TEXT
- proxy-stored-target › Stored targets of existing credentials are filled from the service's base URL › the changelog fills empty targets only (openspec/specs/proxy-stored-target/spec.md:55)
  WHEN the changelog file is parsed as YAML and the master changelog is read
  THEN the file holds one SQL change whose text contains `UPDATE vault.credentials`, `SET target_url`, a join on
Which behaviour is wanted? Answer below and set Status to answered. If one scenario is wrong, delete it from the spec on this unit branch in the same commit; a change on the base branch does not reach this unit.

### Answer
<!-- write below this line -->
