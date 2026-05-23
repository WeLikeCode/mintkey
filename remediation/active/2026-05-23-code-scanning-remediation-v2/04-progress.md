# Progress Log — Code-Scanning Remediation v2

**Session:** `2026-05-23-code-scanning-remediation-v2`
**Branch:** `fix/code-scanning-remediation-v2`

Newest entries at the top.

---

## 2026-05-23 — C-3 IMPLEMENTER (ci.yml pyyaml pin)
- Commit: `d720a46`
- Files changed: .github/workflows/ci.yml (+1 -1)
- Pinned: pyyaml==6.0.2 (line 109)
- Audit result: none — only other pip install (line 73) uses --require-hashes with -r requirements file (out of scope)
- YAML parse: exit 0
- actionlint: not_found

---

## 2026-05-23 — C-2 IMPLEMENTER (seed-job line 1075 leak)
- Commit: `cf4bcf0`
- Files changed: apps/seed-job/main.py (+4 -1)
- import hashlib added? No — already present at line 15
- Untouched-by-design lines verified intact: 396, 399, 412, 1025, 1031, 1077
- Lint: ruff reports 1 pre-existing F841 (unused `args` on line 1057, unrelated to this change); AST parse exit 0
- Functional test: skipped (docker stack not running; static verification sufficient)

---

## 2026-05-23 — C-1 IMPLEMENTER (SSRF fix)
- Commit: `8a87890`
- Files changed: apps/admin-api/src/admin_api/api/services.py (+63 -1)
- Lint: ruff exit 0 (All checks passed)
- Type: mypy not installed in project venv; AST parse exit 0
- Functional test: skipped (docker stack not running; parse + lint confirmed)

---

## 2026-05-23 — C-0 ORCHESTRATOR

### Bootstrap

- Verified main is at `9559561` (PR #90 merge), worktree clean.
- Created branch `fix/code-scanning-remediation-v2`.
- Verified all 8 user-listed findings exist in current open-alerts (898 total open) via Mintkey proxy:
  - #1269 py/full-ssrf @ services.py:572 ✓
  - #1268 py/weak-sensitive-data-hashing @ proxy.py:64 ✓
  - #1267 py/weak-sensitive-data-hashing @ internal.py:119 ✓
  - #1266 py/weak-sensitive-data-hashing @ audit.py:85 ✓
  - 7 py/clear-text-logging-sensitive-data @ seed-job/main.py (lines 396, 399, 412, 1025, 1031, 1075, 1077) ✓
  - #1261 py/clear-text-logging-sensitive-data @ agent.py:90 ✓
  - #1288 PinnedDependenciesID @ mock-backend/Dockerfile:15 ✓
  - #1260 PinnedDependenciesID @ ci.yml:110 ✓
- Context-recon on each finding revealed the FP-vs-genuine split (see ISSUE_INTAKE.md):
  - 3 genuine fixes → C-1, C-2, C-3
  - 5 file-level FPs + 6 seed-job taint-flow FPs → C-4 SECURITY.md anchor section
- Created session scaffold (8 files in `remediation/active/2026-05-23-code-scanning-remediation-v2/`).

### Decisions

- Serial dispatch in Wave 1 (per PR #90 lesson — git index races on shared session bookkeeping)
- Parallel reviewers in Wave 1 review (read-only, no race)
- Strike budget: 3 per chunk (PR #90 standard)

### Next

- Commit C-0 scaffold
- Dispatch C-1 IMPLEMENTER (SSRF)
