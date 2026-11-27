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
<!-- l4:index:end -->

---

## Q-001: tests/unit/admin_api/test_state_after_change_fix3.py:341 contradicts C-4e0f1239 and the real services schema

- **Status:** open
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
