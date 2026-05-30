# Plan — Code-Scanning Remediation v2

**Session:** `2026-05-23-code-scanning-remediation-v2`
**Branch:** `fix/code-scanning-remediation-v2`

## Execution waves

```
Wave 0 (ORCHESTRATOR, this turn):
  C-0  Session scaffold + branch + commit

Wave 1 (serial — disjoint owner files but shared 02-matrix/04-progress):
  C-1  SSRF fix (services.py)           [IMPLEMENTER Sonnet]
  C-2  seed-job line 1075 leak          [IMPLEMENTER Sonnet]
  C-3  ci.yml pip install pin           [IMPLEMENTER Sonnet]
  C-4  SECURITY.md FP-pattern docs      [IMPLEMENTER Sonnet]

Wave 1 review (parallel — read-only):
  C-1 fresh REVIEWER (Opus)
  C-2 fresh REVIEWER (Opus)
  C-3 fresh REVIEWER (Opus)
  C-4 fresh REVIEWER (Opus)

Wave 2:
  C-5  Final fresh REVIEWER (Opus, full session audit)

Wave 3:
  PR open via Mintkey proxy
```

## Why serial in Wave 1

The 4 implementer chunks touch disjoint OWNER files (services.py / seed-job/main.py / ci.yml / SECURITY.md), but each implementer also updates the shared `02-matrix.md` + `04-progress.md` session bookkeeping. Running 4 implementers in parallel without worktree isolation would cause git index race conditions on those shared files. Serial dispatch trades some wall-clock time for reliability — same lesson as PR #90.

## Reviewers can run parallel

Reviewers are READ-ONLY (no commits). 4 parallel fresh-Opus reviewers (one per chunk) have no git index contention.

## Per-chunk DoD (full detail in 01-orchestrator-chunks.md)

| Chunk | One-line DoD |
|---|---|
| C-1 | SSRF helper added; `curl` against private-IP → 400 ssrf_rejected; `curl` against public host → still 200 |
| C-2 | `docker compose logs seed-job` shows `fingerprint sha256:` not plaintext; `make admin-password` still returns the decrypted password |
| C-3 | `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` exit 0; pyyaml is `==`-pinned |
| C-4 | SECURITY.md adds the 4 FP patterns with dismissal anchors; renders cleanly; no other content touched |
| C-5 | Per-chunk reviewer PASS + alert-state delta documented in 99-report |

## Strike budget

Per chunk: 3 strikes max. After strike-3 failure: HARD STOP, escalate to architect via `03-escalations.md`.

## PR opening (after C-5 PASS)

Open via Mintkey proxy (current agent key `mk_agent_1E12...QXWMM`, svc `svc_01KSA6D0...`):

```
POST $PROXY/v1/call/$SVC/repos/WeLikeCode/mintkey/pulls
{
  "title": "fix(security): code-scanning remediation v2 — SSRF, seed-job leak, pyyaml pin, FP docs",
  "head":  "fix/code-scanning-remediation-v2",
  "base":  "main",
  "body":  "<see 99-report.md>"
}
```

## What this PR is NOT

- NOT a re-take of PR #90's backup/restore work (that's done)
- NOT a Tier-3 Trivy Debian-base CVE sweep (out-of-scope per SECURITY.md "Trivy on Debian-base images" policy)
- NOT a re-design of the audit hash chain (would require ADR work; out-of-scope per `weak-hash-migration.md`)
- NOT a re-design of the fingerprint-for-indexed-lookup pattern (Pattern A in C-4; argon2id is already the security boundary per ADR-0017.5)

## Open dependencies

- PR #122 (housekeeping) may merge in parallel. Its diff is `remediation/` only; no conflict with this PR's owner files.
- No other open PRs touching `apps/admin-api/`, `apps/seed-job/`, `.github/workflows/ci.yml`, or `SECURITY.md` (verified at C-0 time).
