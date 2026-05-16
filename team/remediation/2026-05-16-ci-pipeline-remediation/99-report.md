# CI Pipeline Remediation — Closing Report

**Session:** `2026-05-16-ci-pipeline-remediation`
**Branch:** `fix/ci-pipeline-remediation`
**Status:** CLOSED-LOCAL-PASS_ALL (PR open pending owner approval to merge)
**Closed by:** Final REVIEWER subagent (Opus, fresh)

---

## Summary

Restored CI on `github.com/WeLikeCode/mintkey` from chronic red to expected-green. 4 distinct workflow defects identified, 5 implementers dispatched in parallel, 1 reviewer wave returned PASS_ALL with reproducible evidence. 3 atomic commits land on `fix/ci-pipeline-remediation`. Trivy CVE allow-list documents 33 individually-justified CVEs with 2026-08-16 expiry; no severity downgrade. No product code touched, no Dockerfiles touched, no accepted ADRs touched.

---

## Verification commands and exit codes

All commands below were run by the final REVIEWER (Opus, fresh):

```
$ grep "ossf/scorecard-action" .github/workflows/scorecard.yml
uses: ossf/scorecard-action@4eaacf0543bb3f2c246792bd56e8cdeffafb205a # v2.4.3
exit code: 0
# Cross-verified: GitHub API releases/latest → tag_name: "v2.4.3"
# Annotated tag → commit SHA matches the pin.

$ grep -n "cache:" .github/workflows/ci.yml
52:          cache: false
exit code: 0
# Verified: cache:false is on the lint-go job's setup-go step ONLY; test-go-unit unchanged.

$ docker build -f admin-api/Dockerfile -t test-admin-api .
... naming to docker.io/library/test-admin-api done
exit code: 0
# Verified: previously-failing `COPY mintkey-models/mintkey_models/` now resolves.

$ docker build -f services/vault-adapter/Dockerfile -t test-vault-adapter .
... naming to docker.io/library/test-vault-adapter done
exit code: 0
# Second sibling-COPY service verified.

$ cd admin-ui && pnpm install --frozen-lockfile
Already up to date. Done in 168ms using pnpm v11.0.9
exit code: 0

$ docker build --no-cache -f admin-ui/Dockerfile -t test-admin-ui admin-ui/
... [5/8] RUN pnpm install --frozen-lockfile  Done in 4.4s using pnpm v11.1.2
... naming to docker.io/library/test-admin-ui done
exit code: 0
# Verified: pnpm v11 (local + Docker corepack-resolved) accepts the current lockfile.
# Implementer's "no regen needed" conclusion confirmed.

$ grep -cE "^CVE-" .trivyignore
33
exit code: 0
# Each CVE has individual comment with package + mitigation; 2026-08-16 expiry header.

$ git diff --name-only HEAD~3 HEAD | sort
.github/workflows/ci.yml
.github/workflows/container-scan.yml
.github/workflows/scorecard.yml
.gitignore
.trivyignore
exit code: 0
# Scope: workflows + ignore files ONLY. No product code, no Dockerfiles, no ADRs.
```

---

## Chunks completed

| Chunk | Commit | Reviewer verdict | Rounds |
|---|---|---|---|
| CI-A: pin ossf/scorecard-action to v2.4.3 SHA | `38893f0` | PASS | 1 |
| CI-B: cache: false on Lint Go's setup-go | `9957bbc` | PASS | 1 |
| CI-C1: container-scan build context (matrix dockerfile + file:) | `0fd33bf` | PASS | 1 |
| CI-C2: pnpm lockfile regen | (no commit — investigation showed lockfile already consistent under pnpm v11) | PASS | 1 |
| CI-D: .trivyignore allow-list + workflow trivyignores reference | `0fd33bf` (bundled with CI-C1 in container-scan commit; .trivyignore + .gitignore in same commit) | PASS | 1 |

Total: 3 atomic commits on `fix/ci-pipeline-remediation` over the session-scaffold commit `4c5a68e`.

---

## DoD checklist — final state

- [x] Scorecard action pinned to a real semver tag (SHA-pinned with comment).
- [x] ci.yml `Lint Go` job no longer suffers Go-toolchain cache collision.
- [x] container-scan.yml builds with correct context for every Dockerfile in the matrix.
- [x] admin-ui pnpm install with `--frozen-lockfile` succeeds (local + Docker).
- [x] Trivy gate passes for seed-job and jaeger-auth with documented allow-list.
- [x] No `Co-Authored-By` trailer in any new commit (per `~/.claude/CLAUDE.md`).
- [x] No `--no-verify` used.
- [x] No product code changed.
- [x] No Dockerfiles changed.
- [x] No accepted ADRs changed.

---

## Residual risks / deferred items

- **Floating-major action versions** still present in scorecard.yml (`actions/checkout@v4`, `github/codeql-action/upload-sarif@v3`) and likely elsewhere. The OpenSSF Scorecard `pinned-dependencies` check will still flag these; out-of-scope for this session (each was a fresh-target if needed). Track as a follow-up workflow-hardening session.
- **`.trivyignore` expires 2026-08-16**. The 33 allow-listed CVEs need to be re-evaluated then. Three concrete fixes for that follow-up:
  1. seed-job: rebase to a Debian base with patched ncurses/systemd/libcap2 or switch to distroless Python.
  2. jaeger-auth: upgrade oauth2-proxy v7.6.0 → ≥ v7.10.0 (MINTKEY-412) — closes the auth-bypass cluster AND drags in newer Go stdlib (24 of the 30 jaeger-auth CVEs are stdlib).
  3. jaeger-auth: bump Alpine 3.19 (EOL warning during scan) → 3.21.
- **Dependabot PRs**: 32 PRs approved on 2026-05-16 in bulk. Merging is owner-driven; this PR's green CI signal will unblock them. Consider ordering: action-version bumps (#7, #9, #10, #11, #14) FIRST because they may affect CI itself, then runtime deps.
- **`required_status_checks` matrix names** (from branch protection setup): once this PR runs, container-scan job names (e.g., `Build + Trivy scan (admin-api)`) will appear in run history; consider adding the matrix-expanded job names to required checks. Deferred to a separate small ops task.
- **Pinned-dependencies and Scorecard score**: the SHA pin in CI-A satisfies the pinned-deps check for `ossf/scorecard-action` only; the overall workflow score will improve once the residuals above are pinned too.

---

## Escalation resolutions

None during this session. Owner answered the 3 intake-gate forks pre-dispatch:
1. Trivy CVE-gate handling → allow-list with documented IDs
2. pnpm lockfile fix → regenerate; keep --frozen-lockfile
3. Session scope → workflows + lockfile bundled

---

## Lessons learned / notes for next session

- **Verify "no diff" implementer claims rigorously.** CI-C2 returned with zero file changes (current pnpm-lock.yaml was already consistent under pnpm v11). Reviewer's re-verification via fresh Docker build (--no-cache) was essential; without it we'd be uncertain whether the historical failure could recur. The pnpm v11 vs v9 overrides-validation behavior change is the actual root cause; if Dependabot ever proposes `packageManager: pnpm@9.x`, refuse.
- **Trivy allow-list discipline.** Each CVE got an individual mitigation note tied to Mintkey's actual topology (Kong header stripping, mTLS, no SSH server, IPv4-only, etc.). This is what `.trivyignore` should look like — a security-review artifact, not a mute button. Future re-evaluations should preserve this format.
- **Workflow build-context bugs travel together.** CI-C1 caught 6 services with the same `COPY mintkey-models/` / `go.work` pattern. Two of those (broker, kong-syncer) weren't in the failure evidence yet — but the implementer fixed them proactively. Worth keeping the practice: when one matrix entry is wrong for a structural reason, audit the whole matrix.
- **3-strike hard-stop unused.** All 5 chunks passed first review. The orchestrator pattern's overhead was modest given the disjoint file ownership; parallel dispatch saved time. Consider this evidence that the pattern scales well for tightly-scoped multi-file remediations.
