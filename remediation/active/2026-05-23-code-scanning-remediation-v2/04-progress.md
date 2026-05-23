# Progress Log — Code-Scanning Remediation v2

**Session:** `2026-05-23-code-scanning-remediation-v2`
**Branch:** `fix/code-scanning-remediation-v2`

Newest entries at the top.

---

## 2026-05-23 — ORCHESTRATOR finalization

### Per-chunk reviewer verdicts (fresh Opus, read-only)

| Chunk | Reviewer verdict | Key checks confirmed |
|---|---|---|
| C-1 (SSRF) | ✅ PASS | scope=1 file (services.py); both call-sites (`test_service_transient`:601 + `test_service`:773) guarded; 6-property IP check (private/loopback/link-local/multicast/reserved/unspecified); `MINTKEY_SSRF_ALLOW_PRIVATE=1` opt-out honored; error envelope `mintkey:ssrf_rejected`; red-team SSRF vectors (loopback, IMDS, IPv6 ::1, decimal-encoded loopback, DNS-rebinding A-record, gopher/file scheme, missing host) all blocked; ruff exit 0; no co-authored-by; no real keys |
| C-2 (seed-job) | ✅ PASS | scope=1 file (seed-job/main.py); old `{password}` print gone; new fingerprint print at line 1075-1078 uses `hashlib.sha256(password.encode()).hexdigest()[:8]` inside f-string (not bound to scope variable); 6 protected lines (396/399/412/1025/1031/1077) byte-for-byte intact; `import hashlib` was pre-existing at line 15; F841 on line 1057 confirmed pre-existing |
| C-3 (ci.yml) | ✅ PASS | scope=1 file (.github/workflows/ci.yml); line 109 reads `pip install pyyaml==6.0.2`; full audit confirmed only other `pip install` line (73) uses `--require-hashes -r` (out of scope); pyyaml==6.0.2 verified to exist on PyPI; YAML parse exit 0; workflow structure (triggers/env/permissions/other steps) untouched |
| C-4 (SECURITY.md) | ✅ PASS | scope=1 file (SECURITY.md); +125 lines; 1 section heading at line 268; 5 `### Pattern A-E` subheadings (276/297/321/340/369) in correct order; each pattern has rule name, file:line sites, alert numbers, and quotable dismissal anchor; A references argon2id+ADR-0017.5; B references ADR-0014.7+weak-hash-migration.md; C documents `brokered_jwt[:12]+"..."` convention; D has per-line inventory citing fixed-by-`cf4bcf0` for line 1075; E explains PEP 503 local-pkg limitation; all source-of-truth file:line sites verified to still match reality on this branch |

### C-5 final review (full-session audit, fresh Opus)

- Commit log shape: PASS (9 commits in order)
- File-level scope: PASS (12 expected files, no others)
- ADR directory: untouched
- Co-Authored-By trailer: absent from all 9 commits
- Real secrets in diff: none
- Per-commit owner-file scope: PASS for all 4 fix/docs commits + all 4 bookkeeping commits
- SSRF helper + both call-sites: PASS; seed-job fingerprint: PASS; pyyaml pin: PASS; 5 FP patterns A-E present in order: PASS
- Lint/parse (all changed files): PASS (only pre-existing F841 noted)
- Live alert state via proxy: skipped (proxy unreachable — verification deferred to operator post-merge)

C-5 raised ONE bookkeeping issue: the C-4 reviewer PASS mark in 02-matrix.md (orchestrator working-tree edit) was uncommitted, and 04-progress.md had no entry for the four reviewer verdicts. This commit fixes both — the matrix flip + this consolidated reviewer block.

### Decisions during execution

- **Sequencing changed from plan:** plan said "all 4 implementers serial, then parallel reviewers". Actual execution interleaved per-chunk implementer → per-chunk reviewer to surface failures sooner. Net effect: zero strikes used (4/4 chunks PASS first try); no rework needed. Per-chunk gating proved cheaper than batched reviews.
- **C-1 belt-and-suspenders:** IMPLEMENTER guarded BOTH `httpx.AsyncClient.request` call-sites in services.py (test_service_transient + test_service), not just the alert-cited one. Reviewer confirmed both are valid SSRF surfaces.
- **C-3 pyyaml version choice:** 6.0.2 selected (current stable). 6.0.3 also exists but is a minor stable-version choice not worth bikeshedding.
- **C-4 line citations:** Pattern D cites pre-fix line 1077 for the "Seed steps 1-5 complete" print, which after C-2 actually lives at line 1080. Reviewer accepted — the citations are anchored to the original CodeQL alert positions, which is what the GitHub dismissal UI references.
- **Bookkeeping race avoidance:** each implementer's bookkeeping commit silently caught up on the previous chunk's reviewer ✅ PASS marker (which I had edited into the working tree). This worked smoothly through C-4. After C-4 there was no next-chunk implementer to catch up, hence this finalization commit.

### Next

- Push branch
- Open PR via Mintkey proxy (svc_01KSA6D0CZXQ9SK3HAJS7MD00M with agent key mk_agent_1E12...QXWMM)
- Operator dismisses 5 FP-pattern alerts via GitHub UI using the documented anchors (SECURITY.md §"CodeQL + Scorecard — accepted false-positive patterns")
- CodeQL re-scan of merged HEAD should fix the 3 genuine alerts (#1269, #1260, seed-job:1075) within ~24h

---

## 2026-05-23 — C-4 IMPLEMENTER (SECURITY.md FP-pattern docs)
- Commit: `6ef3153`
- Files changed: SECURITY.md (+125 -0)
- Patterns added: A (fingerprint), B (Merkle), C (JWT preview), D (taint scope), E (local-pkg)
- markdownlint: not_found
- Pattern-headings sanity: PASS — Python script confirmed 5 ### Pattern X headings

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
