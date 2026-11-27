# Questions — agent-roles-and-ownership-fix-4

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
| Q-001 | superseded | 1.1 | ambiguous | C-1a3fd676's frozen test requires a credentials subquery that C-4e0f1239 forbids |
<!-- l4:index:end -->

---

## Q-001: C-1a3fd676's frozen test requires a credentials subquery that C-4e0f1239 forbids

- **Status:** superseded by retry
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): The frozen test tests/unit/admin_api/test_state_after_change_fix3.py:347-350 requires every services SELECT of the transfer (including the FOR UPDATE lock at services.py:1652-1657) to contain max(c.key_version) and not s.current_key_version, which needs a credentials subquery. The unit spec (spec.md:168-169, scenario 180-181) and test_service_ownership.py:529-532, 1007-1010 forbid any transfer statement naming credentials. The frozen test's premise that services has no current_key_version column is false: 004-services.yaml:62 defines it and credentials.py:703, 1284 keep it in sync. No production-code change satisfies both the frozen test and the spec. Resolving it means editing a frozen test file, changing the spec, or waiving a test gate, and the question comes from a fix task; a database view built only to make SQL text match an assertion is a schema change outside the spec. These are decisions for a person. The gate also shows an unrelated ImportError (AGENT_ROLES) I did not investi … [cut at 1000 of 1005 characters]
- **Blocking tasks:** 1.1
- **Kind:** ambiguous
- **Asked:** 2026-11-27T07:13Z by deepseek, run r-20261127T0654Z-f5d6, task 1.1

### Context
tests/unit/admin_api/test_state_after_change_fix3.py:341-350 requires every transfer service SELECT to contain MAX(c.key_version) and not s.current_key_version, which needs FROM credentials. tests/unit/admin_api/test_service_ownership.py:529-532 and :1007-1010 (C-4e0f1239) and the unit spec (spec.md:168-169) forbid any transfer statement naming credentials. services.current_key_version is a real column (004-services.yaml:62) kept in sync by credentials.py, so the transfer's current read is correct. Q-001 in fix-3 answered: delete the max assertions from the frozen test, but the harness test path freeze forbids editing tests and reverts it. Baseline: 3021 tests, 1 failed (the fix3 test); C-4e0f1239 is green and a credentials subquery would break it.

### Options
1. Unfreeze tests/unit/admin_api/test_state_after_change_fix3.py and delete the max(c.key_version)/s.current_key_version assertions per Q-001, leaving the transfer reading services.current_key_version.
2. Authorize a production workaround: a database view over services.current_key_version so the transfer SELECT text contains max(c.key_version) without naming credentials.
3. Waive the C-1a3fd676 test gate for this unit and keep the current, spec-compliant code.

### Harness notes
Harness note: the verifier recorded these failures for the tests of this task's findings:
tests.unit.admin_api.test_state_after_change_fix3::test_C_1a3fd676_transfer_and_role_answers_show_the_stored_state (assertion, test):
  >       assert to_publisher.status_code == 200, to_publisher.text
  E       AssertionError: Internal Server Error
  E       assert 500 == 200
  E        +  where 500 = <Response [500 Internal Server Error]>.status_code
  ../../tests/unit/admin_api/test_state_after_change_fix3.py:326: AssertionError

### Answer
<!-- write below this line -->
