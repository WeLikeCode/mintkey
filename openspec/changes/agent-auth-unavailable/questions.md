# Questions — agent-auth-unavailable

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
| Q-001 | open | 1.1 | technical | Refresh the stale cached baseline so pre-existing admin-ui tests are not counted as new |
<!-- l4:index:end -->

---

## Q-001: Refresh the stale cached baseline so pre-existing admin-ui tests are not counted as new

- **Status:** open
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-10-25T09:29Z by deepseek-free, run r-20261025T0835Z-88e7, task 1.1

### Context
The cached baseline for base commit 1b49049 (run r-20261025T0835Z-88e7, ledger seq 19) captured apps/admin-ui/tests/test_auth_scheme.test.ts as one file-level failure, so its 30 individual tests are absent from the base report (2638 = 2667 - 30 + 1). A clean gate run now collects all 30 and they pass, so l4's new_test_ids() treats them as new and classify_red rejects every red attempt with 'new tests passed before implementation', before the task's own mcp-server tests can matter. This is an environment/harness flake; the cached baseline is in memory and the step cannot invalidate it or edit .l4/gates.

### Options
1. Restart the unit/run so a new base commit forces the harness to recompute the baseline (the admin-ui suite collects correctly now).
2. Invalidate the cached baseline for base 1b49049 and re-dispatch task 1.1's red step without changing the worktree.

### Answer
<!-- write below this line -->
