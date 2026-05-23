# Jaeger Cookie Secret Size — Closing Report (superseded by PR #52)

**Session:** `2026-05-17-jaeger-cookie-size`
**Status:** CLOSED (merged via PR #50; superseded — see PR #52 for the surviving fix)
**Closed by:** Documentation reconstruction in `2026-05-17-doc-state-sync` (this report's content was placeholder text at session close on 2026-05-17; rewritten with PR/commit anchors only — verification was not freshly rerun in this doc-state-sync session)

---

## Summary

PR #50 changed `seed-job._ensure_jaeger_cookie_secret` to write 32 raw bytes (`os.urandom(32)`) to satisfy oauth2-proxy's AES-256 key-length requirement. The 32-byte value technically met the size check, but raw binary bytes include null bytes (`\x00`) which are treated as string terminators in POSIX shells. When `jaeger-auth/entrypoint.sh` exported the secret into a shell variable via `$(cat /path/to/secret)`, null bytes caused silent truncation, causing oauth2-proxy to report "missing setting: cookie-secret" on the next deployment. PR #51 attempted a binary-safe transport path via `--cookie-secret-file`; PR #52 then converged on base64 string encoding as the surviving approach.

---

## What landed

- Files changed: `seed-job` bootstrap script — `_ensure_jaeger_cookie_secret` updated to write `os.urandom(32)` (32 raw bytes) instead of the prior placeholder
- Commit SHA: `e6c84fc`
- Merge commit: `a1cf0f3`
- Cascade context: Second in the four-PR jaeger-cookie cascade. Landed after PR #49 cleared the permissions gate. Superseded by PR #52 — the raw-bytes approach survives only as an intermediate step; the 0o644 permissions stance from PR #49 remains in effect.

---

## Verification

> Not freshly rerun in the 2026-05-17 doc-state-sync session that wrote this closing report. The original session at the time of merge relied on:
> - The PR's CI run on commit `e6c84fc` (GitHub Actions — see PR #50 page)
> - For session-local builds: see the session's `00-plan.md` / `02-matrix.md` if those were filled.
> - Final integration verification for the whole cascade landed in PR #53's session (`2026-05-17-seed-job-idempotency-and-sso/99-report.md`) and on the v0.1.0-prealpha tagged commit (CI 13/13 green on `5f397b7`).

---

## Residuals / supersession notes

Superseded by PR #52. The raw-bytes approach introduced a latent shell null-truncation bug: POSIX shell `$(cat file)` strips null bytes and truncates the string at the first `\x00`, producing a shorter-than-expected key that oauth2-proxy rejects. PR #51 attempted to work around this by switching to `--cookie-secret-file` (file-based flag), but that flag does not exist in oauth2-proxy v7.6.0. PR #52 resolved both issues by encoding the 32 bytes as base64 (44 ASCII characters, no null bytes, shell-safe).

---

## Lessons learned

- Raw binary secrets written to files are not shell-safe: `$(cat)` substitution in POSIX shells silently truncates at null bytes, producing a cryptographically shorter key without any error message.
- Size-only validation (`len(secret) == 32`) passes at write time but the content becomes invalid when read back through a shell pipeline — integration tests that exercise the full startup path are required to catch this class of bug.
- Stub/runtime drift in oauth2-proxy: documentation or older blog posts may reference `--cookie-secret-file` which is absent in v7.6.0; always validate flags against the specific version's `--help` or source before coding a dependency on them.
