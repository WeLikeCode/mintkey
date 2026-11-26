# Questions — grant-expiry

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
| Q-001 | open | 1.1, 2.1, 2.2, 3.1, 4.1, 4.2, 4.3, 5.1 | ambiguous | Scenarios "the changelog adds the columns" and "the changelog fills empty targets only" conflict |
<!-- l4:index:end -->

---

## Q-001: Scenarios "the changelog adds the columns" and "the changelog fills empty targets only" conflict

- **Status:** open
- **Blocking tasks:** 1.1, 2.1, 2.2, 3.1, 4.1, 4.2, 4.3, 5.1
- **Kind:** ambiguous
- **Asked:** intake lint (L4-ODD-004)
- **Criteria:** C-48b97ae8 (grant-expiry › The schema stores a grant's expiry and grantor › the changelog adds the columns), C-7ac56330 (proxy-stored-target › Stored targets of existing credentials are filled from the service's base URL › the changelog fills empty targets only)

### Context
These two scenarios have the same GIVEN and WHEN and different THEN, so the implementer cannot satisfy both.
- grant-expiry › The schema stores a grant's expiry and grantor › the changelog adds the columns (specs/grant-expiry/spec.md:18)
  WHEN the changelog file is parsed as YAML and the master changelog is read
  THEN the file holds an `addColumn` for each of the three columns with the types above, `expires_at` and
- proxy-stored-target › Stored targets of existing credentials are filled from the service's base URL › the changelog fills empty targets only (openspec/specs/proxy-stored-target/spec.md:55)
  WHEN the changelog file is parsed as YAML and the master changelog is read
  THEN the file holds one SQL change whose text contains `UPDATE vault.credentials`, `SET target_url`, a join on
Which behaviour is wanted? Answer below and set Status to answered. If one scenario is wrong, delete it from the spec on this unit branch in the same commit; a change on the base branch does not reach this unit.

### Answer
<!-- write below this line -->
