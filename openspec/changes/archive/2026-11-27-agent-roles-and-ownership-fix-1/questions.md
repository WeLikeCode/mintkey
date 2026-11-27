# Questions — agent-roles-and-ownership-fix-1

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
| Q-001 | open | 1.1 | technical | A person must commit the Q-002 edit to test_C_2e9cfe5e_unsuitable_targets |
<!-- l4:index:end -->

---

## Q-001: A person must commit the Q-002 edit to test_C_2e9cfe5e_unsuitable_targets

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): Confirmed in the repository: tests/unit/admin_api/test_service_ownership.py lines 545, 553 and 561 expect mintkey:code agent_not_publisher / agent_not_active, while apps/admin-api/src/admin_api/api/services.py (lines 1698-1709) answers mintkey:code invalid_transfer_target with the reason, as the spec's error requirement and its "the error bodies" scenario pin. The "unsuitable targets" scenario in the spec names the reasons as the 422 codes, so the spec itself is inconsistent and the resolution lies in the test file, not in production code: aligning production with the test would break the error requirement and test_C_cdc7f907. This is a fix task whose only remedy is an edit to a frozen test file, which a person must commit on the unit branch; I cannot answer with a test-file change or reclassify the finding. The referenced Q-002 is not among this unit's earlier answers, so I could not verify it either.
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-11-27T04:26Z by deepseek, run r-20261127T0221Z-dae9, task 1.1

### Context
tests/unit/admin_api/test_service_ownership.py:594 (test_C_2e9cfe5e_unsuitable_targets) still expects the three 422 transfer cases to answer mintkey:code agent_not_publisher, agent_not_active, agent_not_active. Answered Q-002 decided the opposite: an unsuitable target answers 422 invalid_transfer_target keeping that reason, and apps/admin-api/src/admin_api/api/services.py already returns exactly that (test_C_cdc7f907 in the same file passes). This fix task cannot change the test file, so a person must commit the change. Q-002 option 1: in that test's case list, change the fifth tuple element of the three 422 cases (lines 545, 553, 561) from agent_not_publisher, agent_not_active, agent_not_active to invalid_transfer_target for all three, leaving the sixth element (the reason) unchanged.

Harness note: this is a fix task. It cannot unfreeze a test or test-support file (a test, `conftest.py`, a fixture), whatever the answer says: a fix step's change to one is put back. A person must commit the change on the unit branch themselves, then answer this question (`l4 questions answer Q-NNN --unit openspec:agent-roles-and-ownership-fix-1 --text "..."`).

### Options
1. A person commits the edit to tests/unit/admin_api/test_service_ownership.py described above on the unit branch, then answers this question.
2. Reclassify the finding as a test chore so a fix step may edit the test file.

### Harness notes
Harness note: the verifier recorded these failures for the tests of this task's findings:
tests.unit.admin_api.test_service_ownership::test_C_2e9cfe5e_unsuitable_targets (assertion, test):
  >           assert body.get("mintkey:code") == code, (name, body)
  E           AssertionError: ('active consumer', {'mintkey:code': 'invalid_transfer_target', 'title': 'Transfer target not allowed', 'reason': 'agent_not_publisher'})
  E           assert 'invalid_transfer_target' == 'agent_not_publisher'
  E             - agent_not_publisher
  E             + invalid_transfer_target
  ../../tests/unit/admin_api/test_service_ownership.py:594: AssertionError

Harness note: the previous attempt of this task was rejected: nothing changed: the guard put back every edit (tests/unit/admin_api/test_service_ownership.py)

### Answer
<!-- write below this line -->
Done, option 1: commit ae2b28d8 on this branch, by a person, changes the three 422 cases of test_C_2e9cfe5e_unsuitable_targets to expect mintkey:code invalid_transfer_target, each keeping its reason, as Q-002 decided; the test file passes as a whole (18 tests) with the production code unchanged. No production change is needed for this task. Answered by the repository owner's delegate.
