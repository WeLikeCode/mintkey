# Closing Report — S11 scorecard-residuals

**Session:** `2026-05-18-s11-scorecard-residuals`
**Branch:** `fix/s11-scorecard-residuals-2026-05-18`
**Status:** CLOSED-WITH-RESIDUALS (VulnerabilitiesID deferred pending owner action)
**Closed:** 2026-05-18

---

## Summary

OpenSSF Scorecard produces five alert categories for the Mintkey repository. The owner reviewed all five on 2026-05-18 and accepted them as documented residuals for the v0.1.0-prealpha release. This session documents each residual in `SECURITY.md` and `docs/architecture/00-vision/06-roadmap.md`. No source code was changed.

Four alerts are cleanly accepted: Code-Review (solo-author project), Maintained (auto-resolves at day 90 on 2026-07-31), Fuzzing (post-v1 goal), and CII-Best-Practices (badge is a v1.0 goal). The Vulnerabilities alert (GO-2026-XXXX) is documented as deferred pending the owner confirming the advisory ID and upstream patch status — if a patch is available, a follow-up fix session is required.

Scorecard does not support per-check ignore overrides via a repo config file (as of `ossf/scorecard-action@v2.4.3`). Alert dismissals must be done manually in the GitHub Security UI.

---

## Accepted residuals

| Scorecard Check | Severity | Decision | Revisit at |
|---|---|---|---|
| Code-Review | HIGH | Accepted — solo-author, admin-merge stays | v1.0 or contributor #2 |
| Maintained | HIGH | Accepted — auto-resolves 2026-07-31 | No action needed |
| Fuzzing | MEDIUM | Accepted — post-v1 hardening | Post-v1.0 stable |
| CII-Best-Practices | LOW | Accepted — badge is a v1.0 goal | Pre-v1.0 stable release |
| Vulnerabilities (GO-2026-XXXX) | HIGH | **Deferred** — advisory ID unconfirmed; govulncheck unavailable in session | When upstream patch published |

---

## Scorecard config investigation

Investigated whether `ossf/scorecard-action` supports per-check ignore overrides via a repo-level config file (`.scorecard.yml` or `.github/scorecard.yml`).

**Conclusion: NOT supported.** As of Scorecard v4 / `ossf/scorecard-action@v2.4.x`, there is no supported repo-level config that suppresses individual checks. The Scorecard project intentionally does not provide an "ignore" mechanism — the design philosophy is that all checks should surface. Alert dismissal must be done in the GitHub Security → Code scanning alerts UI with a per-alert rationale.

**No `.scorecard.yml` was created.** Creating one would either be ignored silently or would be a schema violation.

---

## Files changed

| File | Change |
|---|---|
| `SECURITY.md` | Added `## Accepted Scorecard Residuals (v0.1.0-prealpha)` section with one subsection per alert (+65 lines approx.) |
| `docs/architecture/00-vision/06-roadmap.md` | Added `### Accepted Scorecard Residuals (v0.1.0-prealpha)` subsection in Section 3, with a 5-row table (+15 lines approx.) |
| `team/remediation/2026-05-18-s11-scorecard-residuals/ISSUE_INTAKE.md` | Session intake (new) |
| `team/remediation/2026-05-18-s11-scorecard-residuals/99-report.md` | This report (new) |

---

## Owner actions required (post-merge)

1. **Dismiss Scorecard alerts in GitHub Security UI** — open GitHub Security → Code scanning alerts → filter by category "scorecard". For each of the four cleanly-accepted alerts (Code-Review, Maintained, Fuzzing, CII-Best-Practices), dismiss with rationale: "Accepted residual per SECURITY.md §Accepted Scorecard Residuals (v0.1.0-prealpha)".

2. **Confirm VulnerabilitiesID advisory** — find the Vulnerabilities alert, note the full `GO-2026-XXXX` advisory ID and the affected Go module version. Check whether an upstream patch is now available:
   - If patched: open a new remediation session to bump the dependency and close the alert.
   - If not patched: dismiss with "Deferred pending upstream patch — per SECURITY.md §Accepted Scorecard Residuals" and monitor Dependabot for the bump PR.

---

## Verification

```
cd /Users/alexandruiacobescu/gooseProjects/mintkey-s11-scorecard-residuals

rg -n "Accepted Scorecard Residuals" SECURITY.md
# Expected: line with "## Accepted Scorecard Residuals (v0.1.0-prealpha)"

rg -n "Scorecard" docs/architecture/00-vision/06-roadmap.md | head -5
# Expected: lines showing "Scorecard workflow" (pre-existing) and "Accepted Scorecard Residuals" (new)

git status --short
# Expected: M SECURITY.md, M docs/architecture/00-vision/06-roadmap.md, new session files

git diff --stat origin/main..HEAD
# Expected: 4 files changed

git log --oneline origin/main..HEAD
# Expected: 1 commit — docs(s11): document accepted Scorecard residuals
```

---

## DoD checklist

- [x] `SECURITY.md` has `## Accepted Scorecard Residuals (v0.1.0-prealpha)` with all 5 checks documented
- [x] `docs/architecture/00-vision/06-roadmap.md` has residuals table in Section 3
- [x] Session ISSUE_INTAKE.md and 99-report.md created
- [x] Scorecard config file NOT created (not supported; documented in this report)
- [x] No source code changed
- [x] No ADRs changed
- [x] No `Co-Authored-By` trailer in any commit
- [x] No `--no-verify` used

---

## Residual risks / deferred items

- **VulnerabilitiesID (GO-2026-XXXX)**: advisory ID not confirmed in this session. Govulncheck was unavailable in the remediation environment. Owner must check GitHub Security for the full advisory and determine patch availability. If a patch exists, this becomes a P1 fix, not a residual.
- **Alert dismissals**: purely a manual UI step; cannot be automated from a git branch.
