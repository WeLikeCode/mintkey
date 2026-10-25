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
| Q-001 | answered | 1.1 | technical | Refresh the stale cached baseline so pre-existing admin-ui tests are not counted as new |
| Q-002 | open | 3.1 | technical | tests/acceptance/test_admin_api_verify_capacity.py:92 needs the infra/compose limits at 512 MiB, but infra/** is harness-protected |
<!-- l4:index:end -->

---

## Q-001: Refresh the stale cached baseline so pre-existing admin-ui tests are not counted as new

- **Status:** answered
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
Answered by Claude as the owner's delegate (the owner: 'do it as my delegate', 2026-10-25). Neither option: the baseline was not stale, the L4 harness broke it. L4 0.4.30 and earlier mount node_modules read-only in test gates, and Vitest 5's default module cache (fsModuleCache, node_modules/.vitest-cache) does an mkdir there that nothing catches, so in every gate run exactly one admin-ui test file failed at file level, a different file each run (the baseline lost tests/test_auth_scheme.test.ts, red attempt 1 lost tests/test_budget_bff.test.ts, attempt 2 lost tests/test_agent_secret_grants.test.ts). L4 0.4.31 makes .vitest-cache a tool cache that is empty and writable in every gate, and staging pins it (2bdc6c7). The next run computes the baseline again under 0.4.31, so every admin-ui file is in the base report and its tests are not new. Do not change the Vitest configuration (no fsModuleCache: false) or any admin-ui file. Continue task 1.1 as written: the new tests in apps/mcp-server/tests/test_rest_auth_unavailable.py, failing by assertion before the implementation.

---

## Q-002: tests/acceptance/test_admin_api_verify_capacity.py:92 needs the infra/compose limits at 512 MiB, but infra/** is harness-protected

- **Status:** open
- **Blocking tasks:** 3.1
- **Kind:** technical
- **Asked:** 2026-10-25T12:50Z by deepseek, run r-20261025T1115Z-b78d, task 3.1

### Context
The frozen test asserts to_mib(services.admin-api.mem_limit) == 512 for infra/compose/docker-compose.yml and infra/compose/docker-compose.ghcr.yml (test line 92), and the requirement and design D4 say both must change from 256m to 512m. The harness default odd.forbidden_paths contains infra/** (l4/config/defaults.py FORBIDDEN_PATHS), so the previous attempt's edits were restored as guard.violation and the test still sees 256m. admin_api.capacity is implemented, deploy/helm/mintkey/values.yaml is 512Mi, and the other four capacity tests pass; this one cannot pass while infra/** is protected.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `tests/acceptance/test_admin_api_verify_capacity.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit agent-auth-unavailable`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `infra/compose/docker-compose.yml`: set `services.admin-api.mem_limit` from `256m` to `512m`.
2. Edit `infra/compose/docker-compose.ghcr.yml`: set `services.admin-api.mem_limit` from `256m` to `512m`.
3. Edit `.l4/config.yaml`: add `odd: {forbidden_paths: [".github/workflows/**", ".gitlab-ci.yml", "**/migrations/**"]}` so `infra/**` is no longer protected, then re-run the green step.

### Clarifier suggestion
Edit `infra/compose/docker-compose.yml`: set `services.admin-api.mem_limit` from `256m` to `512m`.

### Answer
<!-- write below this line -->
