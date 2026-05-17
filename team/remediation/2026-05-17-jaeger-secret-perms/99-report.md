# Jaeger Secret Perms — Closing Report

**Session:** `2026-05-17-jaeger-secret-perms`
**Status:** CLOSED (merged via PR #49)
**Closed by:** Documentation reconstruction in `2026-05-17-doc-state-sync` (this report's content was placeholder text at session close on 2026-05-17; rewritten with PR/commit anchors only — verification was not freshly rerun in this doc-state-sync session)

---

## Summary

PR #49 addressed two related problems in the bootstrap pipeline: (1) `seed-job` was not writing the `jaeger_oauth2_cookie_secret` file at all, leaving jaeger-auth unable to start, and (2) all bootstrap secrets were written with permissions 0o600 or 0o640 owned by root, which blocked non-root jaeger-auth from reading them. The fix made `seed-job` write `jaeger_oauth2_cookie_secret` and flattened all secret file modes to 0o644 (world-readable). Once the permissions gate cleared, oauth2-proxy surfaced the next issue in the cascade: the cookie secret content format was wrong (too small / wrong encoding), which was addressed in PRs #50, #51, and #52.

---

## What landed

- Files changed: `seed-job` bootstrap script — `_ensure_jaeger_cookie_secret` function added; all `_write_secret` calls updated to use mode `0o644` instead of `0o600`/`0o640`
- Commit SHA: `6364923`
- Merge commit: `e3f7665`
- Cascade context: First in the four-PR jaeger-cookie cascade. This PR is standalone — its permissions fix was not superseded. PRs #50, #51, #52 built on top of it to resolve secret format and shell-transport issues that only became visible after the permissions gate cleared.

---

## Verification

> Not freshly rerun in the 2026-05-17 doc-state-sync session that wrote this closing report. The original session at the time of merge relied on:
> - The PR's CI run on commit `6364923` (GitHub Actions — see PR #49 page)
> - For session-local builds: see the session's `00-plan.md` / `02-matrix.md` if those were filled.
> - Final integration verification for the whole cascade landed in PR #53's session (`2026-05-17-seed-job-idempotency-and-sso/99-report.md`) and on the v0.1.0-prealpha tagged commit (CI 13/13 green on `5f397b7`).

---

## Residuals / supersession notes

Not superseded. The 0o644 permissions fix and `jaeger_oauth2_cookie_secret` write are the surviving state. Downstream residuals:

- Docker named volumes default to root-owned on first creation; any service running as a non-root UID needs secrets written with 0o644 (or ACL-controlled) to be readable. This pattern should be enforced for any future bootstrap secrets added to `seed-job`.
- The secret *content* written by this PR (initial placeholder / empty) was superseded by PR #50 (32 raw bytes) and ultimately PR #52 (base64-encoded 44-char ASCII).

---

## Lessons learned

- Docker named volumes are initialised root-owned; downstream containers running as non-root (e.g., `USER 65532:65532`) cannot read files written with 0o600/0o640 by a root seed-job. World-readable (0o644) is the correct posture for non-secret bootstrap material that does not need confidentiality from other containers in the same compose project.
- Bootstrap "write once" jobs should both create the secret file AND set its content in the same step; leaving the file absent causes a hard startup failure rather than a graceful config error.
- Fixing permissions alone unblocked the next layer of failures — cascade debugging should expect multiple sequential PRs once the first gate clears.
