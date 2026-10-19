# Questions — fix-logout-session-fix-1

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
| Q-001 | answered | 1.1 | technical | golangci-lint cache path is on the read-only filesystem |
<!-- l4:index:end -->

---

## Q-001: golangci-lint cache path is on the read-only filesystem

- **Status:** answered
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-10-19T15:46Z by deepseek, run r-20261019T1313Z-104d, task 1.1

### Context
`sh .l4/gates/lint-go.sh` exits 1 in every go.work module with `failed to initialize build cache at /home/runner/.cache/golangci-lint: mkdir /home/runner/.cache/golangci-lint: read-only file system`. The gate exports a writable GOCACHE via the harness but not GOLANGCI_LINT_CACHE, and golangci-lint v1.64.8 only accepts its cache path through GOLANGCI_LINT_CACHE or os.UserCacheDir(). `sh .l4/gates/lint-go.sh` passes (exit 0, no findings) when GOLANGCI_LINT_CACHE points at a writable directory, and this change touches no Go files. `.l4/gates/lint-go.sh` and the harness environment are protected, so I cannot make the gate pass from the repository.

### Options
1. Set GOLANGCI_LINT_CACHE to a writable path (for example .l4-out/golangci-cache or the same directory as GOCACHE) in .l4/gates/lint-go.sh or in the harness gate environment, then rerun verification.
2. Provide a writable /home/runner/.cache/golangci-lint mount in the gate sandbox.
3. Allow this unit to edit .l4/gates/lint-go.sh to export GOLANGCI_LINT_CACHE.

### Answer
<!-- write below this line -->
Option 1, applied by the owner: the lint gate script now exports GOLANGCI_LINT_CACHE=.l4-out/golangci-lint-cache (staging e5d0c8d), and staging is merged into this unit branch. No change in this unit is needed for it; run verification again.
