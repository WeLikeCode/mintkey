# CI Bugs Round 2 — Closing Report

**Session:** `2026-05-16-ci-bugs-round2`
**Branch:** `fix/ci-bugs-round2-2026-05-16`
**Status:** CLOSED-LOCAL-PASS_ALL (PR open pending owner action)
**Closed by:** Final REVIEWER subagent (Opus, fresh)

## Summary

Cleared all 5 remaining CI failures on main HEAD AND brought the repo to OpenSSF Scorecard's actionable bar (Token-Permissions, Pinned-Dependencies). 4 atomic commits land on `fix/ci-bugs-round2-2026-05-16`:
- **CB-WORKFLOWS** — SHA-pinned 41 action references; hoisted top-level write perms to job-level; bumped golangci-lint-action v6 → v8 (fixes Lint Go's Go 1.24 vs 1.25 mismatch).
- **CB-PY-ADMIN-API** — Replaced requirements.txt with pyproject.toml + uv.lock; switched Dockerfile from pip to uv.
- **CB-PY-MCP-SERVER** — Same shape for mcp-server.
- **CB-DOCKERFILE-PIN** — SHA-pinned 15 FROM directives across 10 Dockerfiles.

No product code, no Dockerfile logic changes, no accepted ADRs touched.

## Verification commands and exit codes (REVIEWER re-run, fresh Opus)

```
$ python3 -c "import yaml; [yaml.safe_load(open('.github/workflows/'+f+'.yml')) for f in 'ci scorecard codeql container-scan dependency-review playwright'.split()]"
exit code: 0

$ grep -rE "uses: [^@]+@" .github/workflows/ | grep -vE "@[a-f0-9]{40}( |$|#)"
(empty)

$ grep "golangci-lint-action" .github/workflows/ci.yml
uses: golangci/golangci-lint-action@4afd733a84b1f43292c63897423277bb7f4313a9 # v8.0.0

$ cd admin-api && uv sync --frozen
Audited 74 packages in 10ms        # exit 0

$ cd mcp-server && uv sync --frozen
Audited 67 packages in 7ms         # exit 0

$ cd /Users/alexandruiacobescu/gooseProjects/mintkey
$ docker build -f admin-api/Dockerfile -t rev-admin-api .   # exit 0
$ docker build -f mcp-server/Dockerfile -t rev-mcp-server . # exit 0
$ docker build -f admin-ui/Dockerfile -t rev-admin-ui admin-ui/  # exit 0
$ docker build -f services/broker/Dockerfile -t rev-broker .     # exit 0
$ docker build -f jaeger-auth/Dockerfile -t rev-jaeger jaeger-auth/  # exit 0

$ docker run rev-admin-api python3 -c "import fastapi,sqlalchemy,opentelemetry,prometheus_client; print('OK')"
OK

$ docker run rev-mcp-server python3 -c "import fastapi,respx,prometheus_client; print('OK')"
OK

$ find . -name Dockerfile -not -path "*/node_modules/*" -exec grep -nH "^FROM " {} \; | grep -vE "@sha256:[a-f0-9]{64}"
(empty)

$ git diff --name-only HEAD~4 HEAD -- admin-api/src/ mcp-server/src/ admin-ui/src/ services/*/internal/ internal/ seed-job/ mintkey-models/
(empty — only Dockerfile/manifest changes)

$ git diff --name-only HEAD~4 HEAD -- docs/architecture/01-architecture/adr/
(empty — no ADR changes)
```

## Chunks completed

| Chunk | Commit | Closes | Reviewer | Rounds |
|---|---|---|---|---|
| CB-WORKFLOWS | `2fa1bdb` | Lint Go (Go 1.25 typecheck) + Scorecard publish 400 + Token-Permissions check + 41 unpinned actions | PASS | 1 |
| CB-PY-ADMIN-API | `4de5aff` | Lint Python / Architecture / Python Unit / Schema-Gates (admin-api side) | PASS | 1 |
| CB-PY-MCP-SERVER | `5e98812` | Lint Python / Architecture / Python Unit / Schema-Gates (mcp-server side) | PASS | 1 |
| CB-DOCKERFILE-PIN | `373221f` | Scorecard Pinned-Dependencies (containerImage) — 15/15 pinned | PASS | 1 |

4 atomic commits over session scaffold `c888293`.

## DoD checklist — final state

- [x] All 5 CI failures resolved at the manifest/config level (real CI on PR is the integration test).
- [x] OpenSSF Scorecard Token-Permissions: 0 → green (all top-level perms `contents: read`; writes hoisted to job level).
- [x] OpenSSF Scorecard Pinned-Dependencies: 0/15 containers → 15/15 pinned; 0/41 actions → 41/41 pinned.
- [x] golangci-lint-action @v6 → @v8 (SHA-pinned).
- [x] admin-api + mcp-server unified on uv (matches mintkey-models, mock-backend).
- [x] No `Co-Authored-By` trailer.
- [x] No `--no-verify`.
- [x] No product Python source changes.
- [x] No accepted ADR changes.
- [x] All 4 chunks PASS fresh REVIEWER.

## Residual risks / deferred items

- **seed-job and mock-backend Dockerfile pip commands** still flagged by Scorecard's `pipCommand not pinned by hash` check. These services have working pip installs that don't fail CI; converting them to uv (or pinning pip hashes via `--require-hashes`) is tangential and not addressed here.
- **`tools/deps.sh`** has unpinned pip + curl-then-run patterns. Ops dev tool, not CI; deferred to a maintenance pass.
- **Inline `COPY --from=busybox:musl`** in services/broker and services/kong-syncer Dockerfiles — Scorecard's current rule set only flags `^FROM` lines, so these don't currently degrade the score. Worth pinning in a future hardening session.
- **Scorecard score 4.5 → ~7 expected**, NOT 10. Items remaining ⓘ unfixable in this session: Maintained (90-day check), Code-Review (requires CI-blocking review on past PRs), CII-Best-Practices (badge application), Fuzzing (significant work), Signed-Releases (release process), Contributors (multi-org count), Branch-Protection (-1 from fine-grained token internal error).
- **Lockfile maintenance**: admin-api and mcp-server now have `uv.lock`. When deps need bumping, run `uv sync` (regenerates lock) — analogous to pnpm-lock.yaml workflow.
- **Quarterly digest re-pin** for Dockerfile FROMs (comment in each pinned line). Stale digests don't break builds (digests are immutable) but miss security patches; consider Dependabot rules for Docker image bumps.

## Escalation resolutions

None. All 3 owner decisions were pre-answered at intake time:
1. Python tooling → full conversion (pyproject.toml + uv).
2. Scorecard scope → full cleanup (perms + action SHAs + Dockerfile FROM SHAs).
3. (implicit) Same merge-via-orchestrator pattern as prior sessions.

## Lessons learned

- **golangci-lint-action v6 ships a linter binary built with Go 1.24**, which can't typecheck source targeting Go 1.25+. When the `go` directive in go.mod ratchets up (e.g., due to dependency requirements), the linter version must also ratchet. v8 → golangci-lint v2.x built with Go 1.25+. Worth a CI guard: assert Go directive ≤ linter's build Go.
- **OpenSSF Scorecard publish has a strict no-top-level-write-perms requirement** (returns HTTP 400 even when the workflow runs successfully end-to-end). The error is in stderr after the JSON result; easy to miss. Future workflow authors: hoist all write perms to job level from day one.
- **pyproject.toml `version` must be PEP 440 compliant** — `0.1.0-experimental` is rejected by uv; `0.1.0.dev0` or `0.1.0-alpha.1` is accepted. The implementer caught this; orchestrator's original template was wrong. PEP 440 ≠ semver.
- **Docker image digests vary per architecture** for multi-arch manifest lists. Always pin to the linux/amd64 digest for CI runners (or use the multi-arch index digest if the toolchain supports it). Scorecard accepts both forms.
- **Major bumps of unrelated actions (actions/upload-artifact v4 → v7, actions/checkout v4 → v6) carry real breaking-change risk.** This session deliberately deferred them — Dependabot PRs #9, #10 do that work and should be reviewed individually before merge. Pin-to-latest in a `latest` major-version is the conservative path.
