# Questions — proxy-stored-target-fix-2

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
| Q-001 | open | 1.1 | technical | Unfreeze the four live-stack acceptance files for task 1.1 so the skipped tests can be moved out of the changed files |
<!-- l4:index:end -->

---

## Q-001: Unfreeze the four live-stack acceptance files for task 1.1 so the skipped tests can be moved out of the changed files

- **Status:** open
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-11-25T09:03Z by glm, run r-20261125T0745Z-3966, task 1.1

### Context
F-b0296656 is deterministic: the gate report lists tests.acceptance.test_classical_key::test_classical_key_full_flow, tests.acceptance.test_data_plane_smoke::{test_broker_smoke,test_vault_adapter_smoke,test_proxy_plugin_smoke,test_kong_smoke} and tests.acceptance.test_golden_path::{test_ws8_golden_path_agent_to_upstream,test_ws9_vault_grpc_end_to_end,test_ws10_list_versions_end_to_end} as skipped, and those three files are changed test files. Fixing it requires editing them, but the test-path-freeze guard protects them for this task (lesson L-f63ee119 warns the harness reverts the change; guard.test_tamper events fired for these four files in runs r-20261124T2241Z-cc55, r-20261125T0056Z-9676 and r-20261125T0138Z-75d9, and no task.unfrozen event was recorded for fix-2's task 1.1, unlike fix-1's which was unfrozen by the Q-001/Q-003 answers). No alternative avoids those files: making the tests run is impossible because the gate sandbox has no docker-compose stack (.l4/config.yaml keeps the Docker-stack jobs with the repository's own CI); excluding them requires editing .l4/gates/test.sh or .github/workflows/ci.yml (both protected); leaving them un-gated turns the gate red; reverting fix-1's edits re-breaks C-969b7732 (tests/acceptance/test_live_stack_redaction_assertions.py fails). Proposed fix once unfrozen: move the eight @INTEGRATION tests with their module-level helpers into tests/acceptance/test_e2e_smoke.py — the live-stack file the L4 gate and the CI acceptance job already exclude and which `make smoke` runs with MINTKEY_INTEGRATION_TEST=true — and repoint the Makefile test-golden/test-data-plane-smoke targets and the tools/e2e-isolated.sh golden/data-plane suites so the tests still run against a stack.

Harness note: this is a fix task. It cannot unfreeze a test or test-support file (a test, `conftest.py`, a fixture), whatever the answer says: a fix step's change to one is put back. A person must commit the change on the unit branch themselves, then answer this question (`l4 questions answer Q-NNN --unit openspec:proxy-stored-target-fix-2 --text "..."`).

### Options
1. Unfreeze tests/acceptance/test_classical_key.py, tests/acceptance/test_data_plane_smoke.py, tests/acceptance/test_golden_path.py and tests/acceptance/test_e2e_smoke.py for fix-2 task 1.1 so the eight skipped live-stack tests can be relocated.
2. Waive the finding: the skips are the repository's standing live-stack convention, the modified received_key assertions are already pinned structurally by tests/acceptance/test_live_stack_redaction_assertions.py (which runs in the gate), and the tests run under a stack via the Makefile smoke/golden/data-plane targets.

### Harness notes
Harness note: the previous attempt of this task was rejected: the agent step reached its time limit (30m)

### Answer
<!-- write below this line -->
