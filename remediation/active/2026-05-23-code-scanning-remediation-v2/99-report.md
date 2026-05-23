# 99-report — Code-Scanning Remediation v2

**Session:** `2026-05-23-code-scanning-remediation-v2`
**Branch:** `fix/code-scanning-remediation-v2`
**Base:** `main @ 9559561` (post-PR-#90 merge)
**Status:** **READY TO OPEN PR** (all 4 chunks PASS individually + C-5 full-session PASS pending the bookkeeping consolidation in this commit).

---

## Summary (1-paragraph)

Addressed 8 CodeQL/Scorecard alerts on the open-alerts list. After context-recon, the 8 split into 3 genuine fixes (real SSRF, real plaintext password leak to stdout, real unpinned dependency) and 5 false-positive patterns where the flagged code is intentional and the actual security boundary lies elsewhere. Genuine fixes ship as 3 atomic commits to their respective owner files (services.py, seed-job/main.py, ci.yml). FP patterns documented in SECURITY.md as a new "CodeQL + Scorecard — accepted false-positive patterns" section (A: SHA-256 fingerprint for indexed DB lookup; B: SHA-256 Merkle-chain audit hash per ADR-0014.7; C: already-redacted JWT preview variable; D: function-scope taint-flow artifact in seed-job; E: Dockerfile editable-local install). Each FP pattern includes a quotable dismissal anchor the operator pastes into GitHub's "Dismiss with comment" UI post-merge. Zero strikes used (4/4 chunks PASS first try).

## Commit list

| # | SHA | Subject | Files |
|---|---|---|---|
| 1 | `85b596a` | chore(repo): C-0 — session scaffold for code-scanning-remediation-v2 | 8 session files |
| 2 | `8a87890` | fix(admin-api): reject SSRF in services test endpoint (alert #1269) | services.py |
| 3 | `e8f0936` | chore(remediation): mark C-1 PASS in matrix + progress | 02-matrix.md, 04-progress.md |
| 4 | `cf4bcf0` | fix(seed-job): redact plaintext bootstrap password from stdout | seed-job/main.py |
| 5 | `b1f85a2` | chore(remediation): mark C-2 PASS in matrix + progress | 02-matrix.md, 04-progress.md |
| 6 | `d720a46` | fix(ci): pin pip install pyyaml in workflow (Scorecard #1260) | ci.yml |
| 7 | `8be511c` | chore(remediation): mark C-3 PASS in matrix + progress | 02-matrix.md, 04-progress.md |
| 8 | `6ef3153` | docs(security): add CodeQL + Scorecard accepted FP-pattern section | SECURITY.md |
| 9 | `cf1120e` | chore(remediation): mark C-4 PASS in matrix + progress | 02-matrix.md, 04-progress.md |
| 10 | _this commit_ | chore(remediation): final session report — all chunks PASS, ready for PR | 02-matrix.md, 04-progress.md, 99-report.md, EVIDENCE_LEDGER.md |

## What this PR does

### Genuine fixes (3 alerts → expected state=fixed after CodeQL re-scan)

1. **SSRF in `/v1/admin/services/test` (alert #1269 py/full-ssrf)** — operator-supplied URL was forwarded to `httpx.AsyncClient.request` with zero validation. Added `_validate_test_url(url)` helper (urlsplit + ipaddress + socket.getaddrinfo) that rejects non-http(s) schemes, missing hosts, unresolvable hosts, and any URL whose hostname resolves to private/loopback/link-local/multicast/reserved/unspecified IPs (v4 and v6). Operators may set `MINTKEY_SSRF_ALLOW_PRIVATE=1` to opt out for dev workflows. Both `test_service_transient` and `test_service` endpoints guarded. Rejection returns HTTP 400 with code `mintkey:ssrf_rejected`.

2. **Plaintext bootstrap password to stdout (subset of #1276/#1287 at seed-job/main.py:1075)** — S6 closed the on-disk write side; this print was the remaining stdout leak. Replaced with a sha256[:8] fingerprint message. Operator can still confirm "the seed-job wrote a password" without the plaintext leaving the host; the actual password is recoverable via `make admin-password` (Fernet decrypt).

3. **Unpinned pyyaml install in CI (alert #1260 PinnedDependenciesID)** — pinned to `pyyaml==6.0.2`. Audit confirmed only one other `pip install` line in ci.yml, which uses `--require-hashes -r requirements`.

### False-positive documentation (5 alert sites — operator dismisses post-merge)

New SECURITY.md section "CodeQL + Scorecard — accepted false-positive patterns" with 5 patterns, each carrying a quotable dismissal anchor:

- **Pattern A** (#1267, #1268): SHA-256 truncated fingerprint for indexed DB lookup. Argon2id at `agents.api_key_hash` is the actual credential boundary per ADR-0017.5; the SHA-256 is just a deterministic 64-bit search key.
- **Pattern B** (#1266): SHA-256 Merkle-chain audit hash per ADR-0014.7. Tamper-evidence primitive, not confidentiality. Migration out-of-scope per `docs/security/weak-hash-migration.md`.
- **Pattern C** (#1261): Already-redacted JWT preview variable. `jwt_preview = brokered_jwt[:12] + "..."` upstream — the convention is that any `*_preview` variable is pre-truncated.
- **Pattern D** (subset of #1276/#1287 — seed-job lines 396/399/412/1025/1031/1077): Function-scope taint-flow artifact. Per-line inventory verified — each print emits a label/path/exception/UUID, never the password variable. The genuine leak at line 1075 was fixed by commit `cf4bcf0` in this PR.
- **Pattern E** (#1288): Dockerfile editable-local install. `pip install --require-hashes` cannot apply to local-path installs (PEP 503 limitation); the Dockerfile IS fully pinned along the dimensions that matter (digest-pinned base image + hash-pinned third-party deps).

## Tests not run + why

- **Functional curl trio against SSRF endpoints** (services.py): docker stack was not running during the session; static analysis + reviewer red-team reasoning substituted. Recommend ops verifies on staging or a smoke-test environment after merge.
- **Cold-start docker compose for seed-job redaction**: same reason. The fingerprint message will appear in `docker compose logs seed-job` after the next bootstrap run.
- **CI "Validate Test Override" job for ci.yml change**: will run as part of this PR's CI check; no manual trigger needed.
- **markdownlint on SECURITY.md**: tool not on PATH locally; the Python pattern-headings sanity check substituted.
- **Live alert state query via Mintkey proxy in C-5**: proxy was unreachable from the orchestrator's shell at finalization time; the 8 alert numbers were verified valid at C-0 bootstrap time (898 total open).

## Residual risks

1. **DNS rebinding TOCTOU in SSRF guard**: between `socket.getaddrinfo` in the helper and httpx's own resolve at request time, a malicious DNS resolver could rebind the hostname from a public IP to a private one. Mitigating this requires a custom httpx transport that pins the resolved address — out of scope for alert #1269 which specifies the `getaddrinfo` pattern. Filed as a follow-up consideration.
2. **Fingerprint truncation collision** (Pattern A & C-2): 64-bit (or 32-bit for the seed-job print's [:8] hex) collision space is appropriate for our key population sizes; argon2 verify catches collisions. Not a security regression.
3. **pyyaml==6.0.2 vs 6.0.3**: chose 6.0.2 (current stable, definitely released). 6.0.3 is also available. Bumping is mechanical if needed.
4. **F841 unused `args` on seed-job/main.py:1057**: pre-existing (verified on `main`), unrelated to this PR. Can be cleaned up in a separate housekeeping commit.

## Follow-up

- Operator dismisses 5 FP alerts via GitHub UI using documented anchors after merge.
- Optional: separate housekeeping PR to clean up pre-existing F841 in seed-job/main.py.
- Optional: ADR work to plan the audit-hash-chain migration (Pattern B) if pre-alpha exits without addressing.
- Optional: custom httpx transport for DNS-rebinding-resistant SSRF guard.

## Sign-off

ORCHESTRATOR finalization: PASS. Branch is clean, 9 fix/docs/scaffold commits + 1 final bookkeeping commit, ready for `gh pr create` (via Mintkey proxy per CLAUDE.md).
