# Issue Intake — 2026-05-18-s11-scorecard-residuals

**Session:** `team/remediation/2026-05-18-s11-scorecard-residuals/`
**Branch:** `fix/s11-scorecard-residuals-2026-05-18` (from main @ `7674d9f`)
**Reported:** 2026-05-18
**Reporter:** OpenSSF Scorecard automated scan (campaign S11)

## Problem statement (required)

OpenSSF Scorecard produces five alert categories for this repository. The owner has reviewed each and decided to ACCEPT them as documented residuals rather than remediate them now. Each accepted residual needs to be (a) documented in `SECURITY.md`, (b) noted in the roadmap, and (c) noted in the session closing report so that future operators and contributors understand what was intentionally deferred and under what conditions it will be revisited.

No source code or ADRs are changed. This session is pure documentation.

## Alert list (all accepted-as-residual)

| Scorecard Check | Severity | Owner decision |
|---|---|---|
| Code-Review | HIGH | Accept — solo-author pre-v1; revisit at v1.0 or second contributor |
| Maintained | HIGH | Accept — auto-resolves at day 90 (2026-07-31) |
| Fuzzing | MEDIUM | Accept — post-v1 hardening item |
| CII-Best-Practices | LOW | Accept — badge is a v1.0 stable goal |
| Vulnerabilities (GO-2026-XXXX) | HIGH | Investigate: govulncheck not available locally; go.mod deps (golang.org/x/net v0.52.0, google.golang.org/grpc v1.80.0, google.golang.org/protobuf v1.36.11) appear current as of 2026-05; no confirmed upstream patch available at time of review; document as deferred pending upstream resolution |

## User-visible symptom (required)

None — these are CI/security posture gaps, not user-facing regressions.

## Expected behavior (required)

After this session:
- `SECURITY.md` has an "Accepted Scorecard Residuals (v0.1.0-prealpha)" section explaining each deferred check.
- `docs/architecture/00-vision/06-roadmap.md` has a row for each residual under Section 3 (Technical Preview residuals).
- The session closing report (`99-report.md`) confirms what was documented and what manual steps remain.

## Evidence (required)

- OpenSSF Scorecard workflow at `.github/workflows/scorecard.yml` — `ossf/scorecard-action@v2.4.3`, publishes SARIF to GitHub Security tab.
- Scorecard alerts surface in the GitHub Security → Code scanning alerts view.
- Go module: `go.mod` lists `golang.org/x/net v0.52.0`, `google.golang.org/grpc v1.80.0`, `google.golang.org/protobuf v1.36.11` — no govulncheck in path to confirm exact GO-2026-XXXX advisory ID at scan time.
- First repo commit: `b216c76` on 2026-05-02 → day-90 = 2026-07-31.

## Scope (required)

- `SECURITY.md`
- `docs/architecture/00-vision/06-roadmap.md`
- `team/remediation/2026-05-18-s11-scorecard-residuals/ISSUE_INTAKE.md` (this file)
- `team/remediation/2026-05-18-s11-scorecard-residuals/99-report.md`

## Out of scope (required)

- All source code (Go, Python, Node, shell scripts).
- All ADRs.
- All other documentation files.
- `.github/workflows/scorecard.yml` — the Scorecard action itself is correct and stays.
- No `.scorecard.yml` config file — Scorecard (as of v2.4.x) does not support per-check ignore overrides via repo config. Dismissal must be done manually in the GitHub Security → Code scanning alerts UI with a rationale comment.

## Risk level (required)

`docs` — documentation only; no code changed; no security posture change.

## Verification target (required)

```bash
cd /Users/alexandruiacobescu/gooseProjects/mintkey-s11-scorecard-residuals
rg -n "Accepted Scorecard Residuals" SECURITY.md
rg -n "Scorecard" docs/architecture/00-vision/06-roadmap.md | head -5
git status --short
git diff --stat origin/main..HEAD
git log --oneline origin/main..HEAD
```

## Owner decisions needed (if any)

- **GO-2026-XXXX exact advisory**: govulncheck was not available to confirm the exact advisory ID. Once the Scorecard scan results are available in the GitHub Security tab, the owner should confirm the affected dependency and check whether an upstream patch is now available. If patched: file a follow-up session to upgrade the dep. If not patched: the "deferred pending upstream" documentation in SECURITY.md stands.
- **Scorecard alert dismissals**: owner must manually dismiss each accepted alert in GitHub Security → Code scanning alerts with a brief rationale ("Accepted residual per SECURITY.md §Accepted Scorecard Residuals").
