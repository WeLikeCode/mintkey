# Jaeger Entrypoint Binary-Safe Cookie Pass — Closing Report (superseded by PR #52)

**Session:** `2026-05-17-jaeger-entrypoint-binary`
**Status:** CLOSED (merged via PR #51; superseded by PR #52)
**Closed by:** Documentation reconstruction in `2026-05-17-doc-state-sync` (this report's content was placeholder text at session close on 2026-05-17; rewritten with PR/commit anchors only — verification was not freshly rerun in this doc-state-sync session)

---

## Summary

PR #51 changed `jaeger-auth/entrypoint.sh` to pass the cookie secret via `--cookie-secret-file=/path/to/secret` instead of `--cookie-secret="$VAR"`, intending to bypass the shell null-truncation problem introduced by PR #50's raw-bytes approach. On CI rebuild, oauth2-proxy v7.6.0 returned `unknown flag: --cookie-secret-file` — the flag does not exist in v7.6.0 (it is present in a newer major version or a different fork of oauth2-proxy). This caused jaeger-auth startup to fail outright. PR #52 then reverted the entrypoint back to `--cookie-secret="$VALUE"` and resolved the null-truncation problem at the source by changing `seed-job` to write base64-encoded bytes (44 ASCII characters, no null bytes, shell-safe).

---

## What landed

- Files changed: `jaeger-auth/entrypoint.sh` — `--cookie-secret="$VAR"` replaced by `--cookie-secret-file=/run/secrets/jaeger_oauth2_cookie_secret` (or equivalent path)
- Commit SHA: `abc80c4`
- Merge commit: `3c8fd3a`
- Cascade context: Third in the four-PR jaeger-cookie cascade. This change was reverted in substance by PR #52, which restored value-passing via `--cookie-secret` and fixed encoding at the `seed-job` level instead.

---

## Verification

> Not freshly rerun in the 2026-05-17 doc-state-sync session that wrote this closing report. The original session at the time of merge relied on:
> - The PR's CI run on commit `abc80c4` (GitHub Actions — see PR #51 page)
> - For session-local builds: see the session's `00-plan.md` / `02-matrix.md` if those were filled.
> - Final integration verification for the whole cascade landed in PR #53's session (`2026-05-17-seed-job-idempotency-and-sso/99-report.md`) and on the v0.1.0-prealpha tagged commit (CI 13/13 green on `5f397b7`).

---

## Residuals / supersession notes

Superseded by PR #52. Specifically:

- `--cookie-secret-file` is not a valid flag in oauth2-proxy v7.6.0. The flag appears in documentation or source for a different major version (v8+) or an alternative fork. Using it causes an immediate fatal startup error.
- PR #52 reverted `entrypoint.sh` to `--cookie-secret="$(cat /run/secrets/...)"` (value-passing) and resolved shell null-truncation by changing the secret to base64 ASCII at the `seed-job` write step.
- The surviving entrypoint shape from PR #52 is the current canonical state; PR #51's change did not survive into the final codebase.

---

## Lessons learned

- Flag availability must be verified against the specific pinned version in use (`docker run --rm <image>:<tag> --help`), not against generic documentation or newer-version changelogs. oauth2-proxy v7.6.0 lacks `--cookie-secret-file`.
- When a shell-safety problem exists at the read site (shell variable truncation), fixing the write site (encoding) is more robust than changing the transport (file-based flag), because the file-flag approach depends on the runtime supporting a specific CLI interface.
- Intermediate fixes that introduce new failure modes (unknown flag) can still serve a useful diagnostic purpose by narrowing the search space — PR #51 confirmed that the flag path was not viable for v7.6.0, which directly informed PR #52's encoding-based solution.
