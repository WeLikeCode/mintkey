# Questions — audit-chain-verifiable-fix-1

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
| Q-001 | open | 1.1 | technical | Unfreeze tests/unit/audit_verify/test_chain_verify.py (lines 25 and 50): the red test C-9e5600b1 requires editing this frozen test file |
<!-- l4:index:end -->

---

## Q-001: Unfreeze tests/unit/audit_verify/test_chain_verify.py (lines 25 and 50): the red test C-9e5600b1 requires editing this frozen test file

- **Status:** open
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): The question comes from the fix unit audit-chain-verifiable-fix-1 and its only possible answer is an edit to the frozen test file tests/unit/audit_verify/test_chain_verify.py. The red test (tests/unit/admin_api/test_audit_verify_chain_setup.py:37-75) runs that file in a fresh interpreter with the mo
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-10-26T19:15Z by deepseek, run r-20261026T1842Z-289d, task 1.1

### Context
tests/unit/admin_api/test_audit_verify_chain_setup.py::test_C_9e5600b1_chain_verify_setup_adds_model_path_and_builds_events_with_at runs tests/unit/audit_verify/test_chain_verify.py in a fresh interpreter with packages/python/mintkey-models stripped from sys.path, then asserts that the file itself puts packages/python/mintkey-models on sys.path and that _build_chain(1)[0].at == 2026-01-01T00:00:00+00:00. This matches Q-005 and task 2.1 (`_build_chain` passes `at=datetime(2026, 1, 1, tzinfo=timezone.utc)` to each AuditEvent, and the file also puts the model path on sys.path; test bodies stay). However, the green phase froze test files and restored exactly this file after the previous attempt, so the required edit cannot be made. It cannot be moved into production code either: design D6 keeps AuditEvent's new fields defaulting to None (so a six-field event still has at=None and compute_event_hash raises ValueError) and states 'No sys.path change in production code'. The test currently fails at line 25 with ModuleNotFoundError: No module named 'mintkey_models'.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `tests/unit/admin_api/test_audit_verify_chain_setup.py`, `tests/unit/audit_verify/test_chain_verify.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit audit-chain-verifiable-fix-1`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `tests/unit/audit_verify/test_chain_verify.py`: add `from datetime import datetime, timezone`; after the VERIFY_JOB_DIR sys.path block insert `MODELS_DIR = os.path.join(REPO_ROOT, "packages/python/mintkey-models")` followed by `if MODELS_DIR not in sys.path:` / ` sys.path.insert(0, MODELS_DIR)`; and add `at=datetime(2026, 1, 1, tzinfo=timezone.utc),` to the `AuditEvent(...)` call in `_build_chain`. Test bodies stay unchanged.

### Clarifier suggestion
Edit `tests/unit/audit_verify/test_chain_verify.py`: add `from datetime import datetime, timezone`; after the VERIFY_JOB_DIR sys.path block insert `MODELS_DIR = os.path.join(REPO_ROOT, "packages/python/mintkey-models")` followed by `if MODELS_DIR not in sys.path:` / `    sys.path.insert(0, MODELS_DIR)`; and add `at=datetime(2026, 1, 1, tzinfo=timezone.utc),` to the `AuditEvent(...)` call in `_build_chain`. Test bodies stay unchanged.

### Answer
<!-- write below this line -->
