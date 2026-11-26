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
| Q-001 | answered | 1.1, 2.1, 2.2, 3.1, 4.1, 4.2, 4.3, 5.1 | ambiguous | Scenarios "the changelog adds the columns" and "the changelog fills empty targets only" conflict |
| Q-002 | open | 4.2 | technical | apps/mcp-server/tests/test_grant_expiry_discovery.py:84 — helper collects email_permission_grants but asserts the pg filter |
<!-- l4:index:end -->

---

## Q-001: Scenarios "the changelog adds the columns" and "the changelog fills empty targets only" conflict

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
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
Both behaviours are wanted; the two scenarios do not conflict. "The changelog file" in each WHEN is the file its own requirement names. In grant-expiry, the requirement "The schema stores a grant's expiry and grantor" names apps/admin-api/db/changelog/030-grant-expiry.yaml, so the scenario "the changelog adds the columns" is about that new file: it must hold the three addColumn changes, the CHECK SQL change and the createIndex, and the master must include 030-grant-expiry.yaml exactly once. In proxy-stored-target, the requirement "Stored targets of existing credentials are filled from the service's base URL" names apps/admin-api/db/changelog/033-credential-target-backfill.yaml, a file that already exists at the base and is left untouched by this unit; its scenario describes that file's UPDATE vault.credentials change. The shared WHEN wording is a coincidence of phrasing across two different capabilities and two different files, not a contradiction. Implement 030-grant-expiry.yaml as the grant-expiry spec says, add one include for it to db.changelog-master.yaml, and do not modify 033-credential-target-backfill.yaml or its include. Delete neither scenario.

---

## Q-002: apps/mcp-server/tests/test_grant_expiry_discovery.py:84 — helper collects email_permission_grants but asserts the pg filter

- **Status:** open
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the answer would unfreeze apps/mcp-server/tests/test_grant_expiry_discovery.py of task 4.2 (delegate.unfreeze is false)
- **Blocking tasks:** 4.2
- **Kind:** technical
- **Asked:** 2026-11-26T19:20Z by deepseek, run r-20261126T1716Z-d1d6, task 4.2

### Context
The red test's helper `_statements_reading(session, "permission_grants")` (line 84) returns every recorded statement containing the substring "permission_grants". That also matches the email query `... JOIN email_permission_grants epg ...` in list_services and discover. The tests at lines 104 and 124 then assert that each such statement contains the exact text `pg.expires_at IS NULL OR pg.expires_at > now()`. This contradicts the task (add the filter to the three permission_grants statements in discovery.py), the spec scenario ("for the grants alias it uses" — the email alias is epg) and the design/proposal (email grants are out of scope; email_permission_grants has no expires_at column, changelog 025). The implementation is already correct for the three real statements; only the helper's over-broad match makes the test unable to pass.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `apps/mcp-server/tests/test_grant_expiry_discovery.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit grant-expiry`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `apps/mcp-server/tests/test_grant_expiry_discovery.py`: change line 84 from `return [statement for statement in session.statements if table in statement]` to `return [statement for statement in session.statements if table in statement and "email_permission_grants" not in statement]`.
2. Edit `apps/mcp-server/tests/test_grant_expiry_discovery.py`: change line 84 to `return [statement for statement in session.statements if f" {table} " in statement]`.

### Clarifier suggestion
Edit `apps/mcp-server/tests/test_grant_expiry_discovery.py`: change line 84 from `return [statement for statement in session.statements if table in statement]` to `return [statement for statement in session.statements if table in statement and "email_permission_grants" not in statement]`.

### Answer
<!-- write below this line -->
