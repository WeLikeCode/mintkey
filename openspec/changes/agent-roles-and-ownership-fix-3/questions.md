# Questions — agent-roles-and-ownership-fix-3

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
| Q-001 | open | 1.1 | technical | tests/unit/admin_api/test_state_after_change_fix3.py:341 contradicts C-4e0f1239 and the real services schema |
| Q-002 | open | 1.1 | technical | tests/unit/admin_api/test_state_after_change_fix3.py:341 — the Q-001 edit leaves nothing for the red code to fail, so the test cannot discriminate |
<!-- l4:index:end -->

---

## Q-001: tests/unit/admin_api/test_state_after_change_fix3.py:341 contradicts C-4e0f1239 and the real services schema

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the answer would unfreeze tests/unit/admin_api/test_state_after_change_fix3.py of task 1.1 (delegate.unfreeze is false)
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-11-27T06:07Z by deepseek, run r-20261127T0507Z-3d58, task 1.1

### Context
The red test's `_service_snapshot` (lines 117-120) drops `current_key_version` unless the SQL text contains `max(c.key_version)`, and lines 341-350 assert every service SELECT uses the `MAX(c.key_version)` credentials subquery and never `s.current_key_version`. But `apps/admin-api/db/changelog/004-services.yaml:62` defines a real `services.current_key_version INTEGER` column (kept in sync by credentials.py:703 and :1284), and the pre-existing test `tests/unit/admin_api/test_service_ownership.py:529-533` (criterion C-4e0f1239) asserts that no executed statement text in a transfer contains `credentials` or `permission_grants`. A `MAX(c.key_version)` subquery requires `FROM credentials`, so the red test and that existing test cannot both pass. The current code already re-selects the row after the UPDATE (fix-2); its only failure against the red test is the key-version column choice.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `tests/unit/admin_api/test_service_ownership.py`, `tests/unit/admin_api/test_state_after_change_fix3.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit agent-roles-and-ownership-fix-3`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `tests/unit/admin_api/test_state_after_change_fix3.py`: delete lines 117-120 so `_service_snapshot` always keeps `current_key_version`, and delete the `service_selects` loop at lines 341-350 with the `max(c.key_version)` / `s.current_key_version` assertions.
2. Edit `tests/unit/admin_api/test_service_ownership.py`: delete the `assert "credentials" not in lowered` line in both statement loops (lines 531 and 1009) so a credentials subquery is allowed in a transfer read.

### Clarifier suggestion
Edit `tests/unit/admin_api/test_state_after_change_fix3.py`: delete lines 117-120 so `_service_snapshot` always keeps `current_key_version`, and delete the `service_selects` loop at lines 341-350 with the `max(c.key_version)` / `s.current_key_version` assertions.

### Answer
<!-- write below this line -->
Take option 1: edit tests/unit/admin_api/test_state_after_change_fix3.py, delete lines 117-120 so _service_snapshot always keeps current_key_version, and delete the service_selects loop at lines 341-350 (the max(c.key_version) / s.current_key_version assertions). services.current_key_version is a real column of the services table (changelog 004), which the credential routes keep in step with the active credential, so the transfer's re-read of that column is the service's current key version that FB-001 asks for, and it keeps every transfer statement off the credentials table as C-4e0f1239 requires. FB-001's mention of a subquery described the old gap; it is not a requirement. FB-001's other point is already met: _service_row_to_dict reads row.current_key_version directly. Answered by the repository owner's delegate.

---

## Q-002: tests/unit/admin_api/test_state_after_change_fix3.py:341 — the Q-001 edit leaves nothing for the red code to fail, so the test cannot discriminate

- **Status:** open
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): Neither option is mine to take. Option 1 (the clarifier suggestion) contradicts the unit's own spec: specs/agent-roles-and-ownership/spec.md lines 168-169 say the transfer "SHALL run no statement on `credentials`" and the scenario at lines 180-181 requires that "no executed statement text contains `credentials`"; the transfer docstring (services.py:1625) and test_service_ownership.py:531/1009 pin the same rule, so a MAX(c.key_version) subquery on credentials is a spec violation, not a fix. Option 2 is a waiver of the harness's red-test discrimination check. I verified the red test's premise is false (services.current_key_version is a real column, 004-services.yaml:62, kept in step by credentials.py:703 and :1284) and that the code already re-selects after the UPDATE (services.py:1760-1775), so no production-code change can make the frozen red test fail without breaking the spec. What remains is a test-only correction inside a fix task plus a process waiver, which only a person can comm … [cut at 1000 of 1012 characters]
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-11-27T06:38Z by deepseek, run r-20261127T0621Z-c082, task 1.1

### Context
Q-001 answer (option 1) says to delete lines 117-120 so `_service_snapshot` always keeps `current_key_version`, and delete the `service_selects` loop at lines 341-350. With those deletions the remaining assertions (new owner, current_key_version 4, updated_at == the UPDATE's bound `now`, new role and its updated_at) are already satisfied by the current red code: both `transfer_service_ownership` (services.py re-select after the UPDATE) and `update_agent_role` (agents.py re-select after the UPDATE) return the stored post-change row, and `_service_row_to_dict` reads `row.current_key_version` directly. I applied exactly the Q-001 edit and ran the test against the unmodified code: 1 passed. The harness then rejects the step because the corrected test does not fail on the red commit's code. The original test only discriminated through the `MAX(c.key_version)` / `s.current_key_version` assertions that Q-001 removes because they contradict C-4e0f1239 and changelog 004 (`services.current_key_version` is a real column). No non-test change can make the red code fail the edited test. The only coherent discriminating path is the other option Q-001 did not take: keep the red test unchanged and let the transfer read the key version from the `credentials` table via `MAX(c.key_version)`, which requires lifting the `credentials`-free assertions in test_service_ownership.py.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `tests/unit/admin_api/test_service_ownership.py`, `tests/unit/admin_api/test_state_after_change_fix3.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit agent-roles-and-ownership-fix-3`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `tests/unit/admin_api/test_service_ownership.py`: delete the `assert "credentials" not in lowered` assertions at lines 531 and 1009, so the transfer can read the key version from the credentials table via the `MAX(c.key_version)` subquery; then I will leave tests/unit/admin_api/test_state_after_change_fix3.py unchanged (it still fails on the red code) and implement the subquery in services.py.
2. Keep Q-001 option 1 and accept that the edit makes the test pass on the red code, waiving the harness's discrimination check for this task (the code already satisfies C-1a3fd676, so the task becomes a test-only correction).

### Harness notes
Harness note: the previous attempt of this task was rejected: the corrected test no longer discriminates: tests.unit.admin_api.test_state_after_change_fix3::test_C_1a3fd676_transfer_and_role_answers_show_the_stored_state do not fail against the red commit's code (they pass, are skipped or did not run there)

### Clarifier suggestion
Edit `tests/unit/admin_api/test_service_ownership.py`: delete the `assert "credentials" not in lowered` assertions at lines 531 and 1009, so the transfer can read the key version from the credentials table via the `MAX(c.key_version)` subquery; then I will leave tests/unit/admin_api/test_state_after_change_fix3.py unchanged (it still fails on the red code) and implement the subquery in services.py.

### Answer
<!-- write below this line -->
