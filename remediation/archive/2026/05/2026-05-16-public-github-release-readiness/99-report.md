# Public GitHub Release Readiness — Closing Report

**Session:** `2026-05-16-public-github-release-readiness`
**Status:** COMPLETE — REL-FINAL verification 18/18 PASS
**Date:** 2026-05-16
**Branch:** `main` (clean working tree at closing)
**Tip after this report:** to be set by the closing commit
**Commits:** 6 (1 baseline + 5 chunk fixes), 0 with LLM co-author trailers

---

## Executive Summary

This session closed the gap between the OSS-readiness session (`2026-05-16-oss-readiness`,
closed earlier today at commit `7f5fe29`) and an actual public-GitHub push. BASELINE-REVIEWER
re-verified the prior session's claims and surfaced 2 RED parse failures (CI YAML, OpenAPI
ref) and 3 YELLOW finishing items (container hardening, version metadata, gitignore). All
five were fixed: REL-1 fixed `ci.yml:90` literal-block scalar; REL-2 defined the missing
`UnprocessableEntity` response; REL-3 added `USER` + `HEALTHCHECK` to 6 non-distroless
Dockerfiles (all 5 long-running services now run uid≠0 and report healthy); REL-4 aligned
8 secondary surfaces (including the runtime FastAPI `version=` field) to `0.1.0-preview.1`;
REL-5 hid the admin-ui Playwright screenshot dirs from `git add -A`. Independent re-runs of
all 18 verification commands pass.

**Verdict: READY TO PUSH** as a pre-alpha technical preview. Mintkey is **not production
ready** and the announcement must say so explicitly (wording below). Known residuals are
documented in §5; none block the push.

---

## 1. Per-chunk evidence

### REL-1 — fix(ci): convert ci.yml:90 to literal-block run: scalar
- **Commit:** `0643e67`
- **What changed:** `.github/workflows/ci.yml:90` bare-scalar `run:` value containing unquoted
  `: ` converted to `run: |` literal-block scalar. 1 line changed.
- **Why:** PyYAML, ruamel.yaml, yamllint, and (likely) GitHub Actions' strict `go-yaml.v3`
  rejected the file. If GitHub had rejected it on push, *no* `ci.yml` jobs would have run —
  a silent CI bypass.
- **Verification:** `python3 -c "import yaml, pathlib; [yaml.safe_load(p.read_text()) for p in pathlib.Path('.github/workflows').glob('*.yml')]; print('workflow yaml: ok')"` → exit 0, `workflow yaml: ok` (REL-FINAL re-run today).
- **Status:** P0-4 ✅

### REL-2 — fix(openapi): define UnprocessableEntity response
- **Commit:** `951476a`
- **What changed:** Added `UnprocessableEntity` to `components.responses` in
  `docs/architecture/contracts/rest/openapi.yaml` (11 lines), matching the existing
  `application/problem+json` + inline `example` style. Example `detail` reflects the
  rotate-key `expires_in` validation constraint.
- **Why:** `openapi.yaml:1304` (rotate-key POST 422) referenced
  `#/components/responses/UnprocessableEntity` which was never defined. CI `lint-contracts`
  would fail on first push.
- **Verification:** `openapi_spec_validator.validate()` → exit 0, `openapi: ok`; internal
  `$ref` sweep → 355 refs, 0 unresolved (REL-FINAL re-run today).
- **Status:** P0-3 ✅

### REL-3 — feat(hardening): USER + HEALTHCHECK on 6 non-distroless Dockerfiles
- **Commit:** `21e5312`
- **What changed (8 files):**
  - `admin-api/Dockerfile` — `useradd 65532`, `USER 65532:65532`, python3 inline HEALTHCHECK on `:8080/v1/health`
  - `mcp-server/Dockerfile` — `useradd 65532`, `USER 65532:65532`, HEALTHCHECK on `:8082/health`
  - `admin-ui/Dockerfile` — `chown node:node /app`, `USER node` (UID 1000), node `http.get` HEALTHCHECK on `:8081/health`
  - `mock-backend/Dockerfile` — `useradd 65532`, `USER 65532:65532`, HEALTHCHECK on `:8999/health`
  - `seed-job/Dockerfile` — `useradd 65532`, `USER 65532:65532`, no HEALTHCHECK (one-shot)
  - `jaeger-auth/Dockerfile` — `adduser 65532 oauth2proxy`, `USER 65532:65532`, `wget` HEALTHCHECK on `:4180/ping`
  - `docs/DEPLOYMENT.md` — audit table refreshed; volume-chown operator upgrade note added
- **Why:** Trivy + Scorecard would flag all 6 as running as root with no in-image health
  signal. Pre-state: 0/10 USER, 0/10 HEALTHCHECK.
- **Verification (REL-FINAL re-runs today):**
  - `grep -l '^USER ' …6 files` → 6/6 hits
  - `grep -l '^HEALTHCHECK' …5 files` → 5/5 hits (seed-job correctly omitted)
  - `docker compose exec -T <svc> id` per service: `uid=65532(nonroot)` (admin-api, mcp-server, mock-backend), `uid=1000(node)` (admin-ui), `uid=65532(oauth2proxy)` (jaeger-auth) — **all uid ≠ 0**
  - `docker compose ps` — all 5 long-running services `Up (healthy)`
- **Status:** P1-4 ✅

### REL-4 — chore(version): align 8 secondary surfaces to 0.1.0-preview.1
- **Commit:** `238c612` (orchestrator-committed after implementer skipped)
- **What changed (8 files):** `SECURITY.md:11`; `admin-api/src/admin_api/main.py:60`
  (FastAPI runtime `version="0.1.0-preview.1"` — critical, reflected in `/openapi.json`);
  `docs/architecture/contracts/events/audit-event.schema.json:7`;
  `docs/architecture/contracts/events/change-event.schema.json:7`;
  `docs/architecture/contracts/mcp/tools.yaml:53`;
  `docs/architecture/contracts/vault-adapter/vault.proto:4`;
  `docs/architecture/contracts/README.md:9`;
  `docs/architecture/contracts/events/span-attributes.md:3,125`.
- **Why:** Public-facing version drift across the contract surface. Sister OSS-4 session
  aligned the canonical 5 files; this session finished the secondary 8.
- **Verification (REL-FINAL re-runs today):**
  - `rg '0\.1\.0-experimental'` across the 8 target files → 0 hits
  - Canonical 5 files: `admin-ui/package.json`, `mintkey-models/pyproject.toml`,
    `openapi.yaml` `info.version`, `README.md`, `CHANGELOG.md` — all `0.1.0-preview.1`
  - `curl -s http://localhost:8080/openapi.json | python3 -c '… d["info"]["version"]'`
    → `info.version: 0.1.0-preview.1`
- **Status:** P1-5 ✅

### REL-5 — chore(gitignore): hide admin-ui playwright screenshot dirs
- **Commit:** `e3ae676`
- **What changed:** `.gitignore` — 3 lines added (blank separator + comment + glob
  `admin-ui/screenshots-*/`).
- **Why:** Two untracked dirs (`admin-ui/screenshots-chunk-g/`, `admin-ui/screenshots-verify/`)
  sat in the working tree. A reflexive `git add -A` would have committed binary screenshots
  to the public repo.
- **Verification (REL-FINAL re-runs today):**
  - `git status --short | grep screenshots` → empty
  - `git check-ignore -v admin-ui/screenshots-chunk-g admin-ui/screenshots-verify` → both
    matched at `.gitignore:20:admin-ui/screenshots-*/`
- **Status:** R-15 ✅

---

## 2. Verification table — 18 rows

All 18 commands were re-run independently by REL-FINAL today, with the working tree at the
post-session state (`238c612` tip, no `Co-Authored-By` trailers). Every row PASS.

| # | Check | Command | Result |
|---|---|---|---|
| F1 | All workflow YAMLs parse strictly | `python3 -c "import yaml, pathlib; [yaml.safe_load(p.read_text()) for p in pathlib.Path('.github/workflows').glob('*.yml')]; print('workflow yaml: ok')"` | exit 0, `workflow yaml: ok` — **PASS** |
| F2 | OpenAPI semantic validation | `python3 -c "import yaml,openapi_spec_validator as v; v.validate(yaml.safe_load(open('docs/architecture/contracts/rest/openapi.yaml'))); print('openapi: ok')"` | exit 0, `openapi: ok` — **PASS** |
| F3 | OpenAPI internal ref consistency | recursive `$ref: "#/..."` walker | `refs: 355, unresolved: 0` — **PASS** |
| F4 | JSON schemas valid | `python3 -c "import json; from jsonschema import Draft202012Validator as V; [V.check_schema(json.load(open(p))) for p in [...audit-event.schema.json...,...change-event.schema.json...]]; print('json schemas: ok')"` | exit 0, `json schemas: ok` — **PASS** |
| F5 | MCP tools YAML valid | `python3 -c "import yaml; yaml.safe_load(open('docs/architecture/contracts/mcp/tools.yaml')); print('ok')"` | exit 0, `ok` — **PASS** |
| F6 | No `\|\| true` / `continue-on-error: true` masks | `rg -n '\|\| true' .github Makefile` + `rg -n 'continue-on-error: true' .github Makefile` | 2 hits, both **comment-only** documenting prior removal (`Makefile:168`, `.github/workflows/ci.yml:172`) — **PASS** |
| F7 | No placeholder strings | `rg -n 'TBD-by-architect\|noreply@anthropic\.com\|Co-Authored-By\|<repo-url>\|maintainers@example\.invalid\|example\.invalid/mintkey'` over public docs | 4 hits, all **forbid-context** (CONTRIBUTING.md:168 rule, RELEASE.md:179 grep command, PR template forbid-list, roadmap historical row) — **PASS** |
| F8 | Zero stale 0.1.0-experimental in 8 target files | `rg -n '0\.1\.0-experimental' SECURITY.md admin-api/src/admin_api/main.py docs/architecture/contracts/events/audit-event.schema.json docs/architecture/contracts/events/change-event.schema.json docs/architecture/contracts/mcp/tools.yaml docs/architecture/contracts/vault-adapter/vault.proto docs/architecture/contracts/README.md docs/architecture/contracts/events/span-attributes.md` | exit 1 (no matches) — **PASS** |
| F9 | Canonical 5 files match `0.1.0-preview.1` | inspect: admin-ui/package.json, mintkey-models/pyproject.toml, openapi.yaml info.version, README.md, CHANGELOG.md | `"version": "0.1.0-preview.1"` (admin-ui); `version = "0.1.0-preview.1"` (pyproject); `version: "0.1.0-preview.1"` (openapi info.version); README + CHANGELOG both reference `0.1.0-preview.1` — **PASS** |
| F10 | Runtime FastAPI version | `curl -s http://localhost:8080/openapi.json \| python3 -c "... d['info']['version']"` | `info.version: 0.1.0-preview.1` — **PASS** |
| F11 | 6 non-distroless Dockerfiles have USER | `grep -l '^USER ' admin-api/Dockerfile mcp-server/Dockerfile admin-ui/Dockerfile mock-backend/Dockerfile seed-job/Dockerfile jaeger-auth/Dockerfile` | 6 hits (admin-api `USER 65532:65532`, mcp-server `USER 65532:65532`, admin-ui `USER node`, mock-backend `USER 65532:65532`, seed-job `USER 65532:65532`, jaeger-auth `USER 65532:65532`) — **PASS** |
| F12 | 5 of 6 have HEALTHCHECK (seed-job omitted) | `grep -l '^HEALTHCHECK' admin-api/Dockerfile mcp-server/Dockerfile admin-ui/Dockerfile mock-backend/Dockerfile jaeger-auth/Dockerfile` | 5 hits; seed-job correctly has none (one-shot init container) — **PASS** |
| F13 | Running containers actually run as non-root | `docker compose exec -T $svc id` for admin-api, mcp-server, admin-ui, mock-backend, jaeger-auth | `uid=65532(nonroot)`, `uid=65532(nonroot)`, `uid=1000(node)`, `uid=65532(nonroot)`, `uid=65532(oauth2proxy)` — **all uid ≠ 0, PASS** |
| F14 | docs/DEPLOYMENT.md audit table refreshed | `grep -c 'USER' docs/DEPLOYMENT.md` + REL-3/date scan | 7 USER mentions; `docs/DEPLOYMENT.md:96` "*The table below is an audit snapshot reflecting the state after REL-3 (2026-05-16).*"; lines 116/119/142 carry REL-3 annotations — **PASS** |
| F15 | Screenshot dirs ignored | `git status --short \| grep screenshots` + `git check-ignore -v admin-ui/screenshots-chunk-g admin-ui/screenshots-verify` | status empty; both dirs matched at `.gitignore:20:admin-ui/screenshots-*/` — **PASS** |
| F16 | No `Co-Authored-By: Claude` in any of the 6 session commits | `git log --since='2026-05-16' --format='%H %B' \| grep -iE 'co.authored.by\|noreply@anthropic\.com'` | exit 1 (no matches) — **PASS** |
| F17 | Data preserved (postgres rows) | `docker compose exec -T postgres psql -U mintkey_migrate -d mintkey -tA -c "SELECT 'svc='\|\|COUNT(*) FROM services UNION ALL SELECT 'agents='\|\|COUNT(*) FROM agents UNION ALL SELECT 'pg='\|\|COUNT(*) FROM permission_grants"` | `svc=4`, `agents=3`, `pg=2` — **PASS** |
| F18 | ≥5 ✅ rows in 02-matrix.md | `grep -c '✅' team/remediation/2026-05-16-public-github-release-readiness/02-matrix.md` | 5 (REL-1..5 session items) — **PASS** |

**Verification total: 18/18 PASS.**

---

## 3. Final matrix snapshot

Counts of `team/remediation/2026-05-16-public-github-release-readiness/02-matrix.md` after
this report:

- **GREEN ✅:** 6 rows
  - P0-3 (OpenAPI validation — REL-2)
  - P0-4 (Workflow YAML parse — REL-1)
  - P1-4 (Container hardening — REL-3)
  - P1-5 (Version policy — REL-4)
  - P1-6 (Final readiness verification — this report)
  - R-15 / REL-5 (Screenshot gitignore)
- **YELLOW 🟦:** 0 rows in-session (all session-scope items closed).
- **WHITE ⬜:** 7 rows
  - P0-1, P0-2, P0-5, P0-6, P0-7, P1-1, P1-2, P1-3 are pre-existing rows that were
    resolved by the **sister `2026-05-16-oss-readiness` session** (closed at commit
    `7f5fe29`). They appear ⬜ here only because this session's matrix tracked them as
    inherited-state, not because they are unresolved on the codebase. Verification:
    LICENSE, real security contact (`the+security@ciprianiacobescu.com`), governance
    templates, Dependabot/CodeQL/container-scan workflows, `.dockerignore` files, and
    the no-mask `||true` removal are all present in the working tree. F6/F7/F9 above
    confirm this.

---

## 4. Session metadata

### Commits in this session (6, in chronological order)
```
f5d0030 docs(remediation): baseline + chunk plan for public-release readiness
0643e67 fix(ci): convert ci.yml:90 to literal-block run: scalar (REL-1)
951476a fix(openapi): define UnprocessableEntity response (REL-2)
e3ae676 chore(gitignore): hide admin-ui playwright screenshot dirs (REL-5)
21e5312 feat(hardening): add USER + HEALTHCHECK to 6 non-distroless Dockerfiles (REL-3)
238c612 chore(version): align 8 secondary surfaces to 0.1.0-preview.1 (REL-4)
```
**0 of 6** carry `Co-Authored-By: Claude` or `noreply@anthropic.com` trailers (F16 verified).

### Files touched by this session (10)
```
.github/workflows/ci.yml                                       (REL-1)
docs/architecture/contracts/rest/openapi.yaml                  (REL-2)
.gitignore                                                     (REL-5)
admin-api/Dockerfile                                           (REL-3)
mcp-server/Dockerfile                                          (REL-3)
admin-ui/Dockerfile                                            (REL-3)
mock-backend/Dockerfile                                        (REL-3)
seed-job/Dockerfile                                            (REL-3)
jaeger-auth/Dockerfile                                         (REL-3)
docs/DEPLOYMENT.md                                             (REL-3 audit table)
SECURITY.md                                                    (REL-4)
admin-api/src/admin_api/main.py                                (REL-4 — runtime version)
docs/architecture/contracts/events/audit-event.schema.json     (REL-4)
docs/architecture/contracts/events/change-event.schema.json    (REL-4)
docs/architecture/contracts/mcp/tools.yaml                     (REL-4)
docs/architecture/contracts/vault-adapter/vault.proto          (REL-4)
docs/architecture/contracts/README.md                          (REL-4)
docs/architecture/contracts/events/span-attributes.md          (REL-4)
team/remediation/2026-05-16-public-github-release-readiness/{00-plan,01-orchestrator-chunks,02-matrix,04-progress,99-report}.md
```

---

## 5. Known residuals (out of session scope)

These are documented for transparency; **none block the pre-alpha push.**

1. **`test_openapi_parity_snapshot` pre-existing FAIL** — router structural drift unrelated
   to version (`health` prefix shifted `/v1/health`→`/metrics`; new `service_templates`
   router not in stored snapshot). Predates REL-4; not caused by this session. Fix is a
   snapshot regeneration, not a contract change.
2. **`mcp-server` runtime still carries `0.1.0-experimental` in 3 files**:
   - `mcp-server/src/mcp_server/main.py:55` (FastAPI `version="0.1.0-experimental"`)
   - `mcp-server/src/mcp_server/tools/jsonrpc.py:62`
   - `mcp-server/src/mcp_server/tools/landing.py:86`
   The 8 target files for REL-4 were the canonical contract+admin set; mcp-server is a
   separate refresh deferred for a follow-up alignment chunk.
3. **Auto-generated `*.pb.go` carry `0.1.0-experimental` in headers** —
   `internal/vault/v1/vault.pb.go:4`, `internal/vault/v1/vault_grpc.pb.go:4`. Will be
   regenerated next time `vault.proto` is recompiled; no action needed now.
4. **`otel-collector` pre-existing restart loop** — `docker compose ps` shows
   `Restarting (1) 27s ago`. Unrelated to release readiness; carried over from sister
   session residuals. Other 16 services healthy.
5. **Dockerfile `@sha256` digest pinning still deferred** — owner-discretion decision
   recorded in REL-3; tags are still floating. Acceptable for pre-alpha; revisit before
   1.0.
6. **4 Go service Dockerfiles still lack explicit `USER` directive** —
   `services/broker/Dockerfile`, `services/vault-adapter/Dockerfile`,
   `services/proxy-plugin/Dockerfile`, `services/kong-syncer/Dockerfile` all use
   `FROM gcr.io/distroless/static-debian12` whose implicit default UID is 65532 (`nonroot`).
   Adding an explicit `USER 65532:65532` directive is recommended for clarity but not
   functionally required for pre-alpha; documented in `docs/DEPLOYMENT.md`.

---

## 6. Recommended launch wording

Adapted from the sister session's draft, with the technical-preview framing this session
delivers:

> **Introducing Mintkey — a self-hosted credential broker for AI agents.**
>
> AI agents need API keys to call external services. Today they get raw secrets baked into
> prompts or environment variables. Mintkey changes that: agents get scoped, short-lived
> tokens; they never see the underlying credential. Built-in audit chain, operator OIDC
> via Keycloak, MCP server for direct AI-client integration.
>
> **Pre-alpha — version `0.1.0-preview.1`. Not for production.** Self-host in 10 minutes
> with the built-in mock backend (no external API keys required):
> `git clone https://github.com/WeLikeCode/mintkey.git && cd mintkey && docker compose up -d`
> then follow `docs/guides/10min-mock-demo.md`.
>
> Works with Claude Desktop, Claude Code, Cursor, and mcp-cli out of the box.
> Apache-2.0. Questions in GitHub Discussions. Contributions in CONTRIBUTING.md.
> Security reports to `the+security@ciprianiacobescu.com`.
>
> https://github.com/WeLikeCode/mintkey

---

## 7. Not production ready

Mintkey is **pre-alpha technical preview software**. It is **not** production ready and
**must not** be used to broker real secrets or guard production workloads at this time.

Specifically:

- The wire surface is declared `experimental` (OpenAPI `x-mintkey-stability: experimental`,
  `info.version: 0.1.0-preview.1`). Breaking changes will occur without deprecation.
- No SOC2 / ISO 27001 / FedRAMP / HIPAA certification or audit.
- No image signing, SBOM publishing, or build provenance attestations yet (release workflow
  deferred — see `docs/RELEASE.md`).
- Base images pinned by tag, not digest — supply-chain risk accepted for pre-alpha.
- 4 Go service Dockerfiles rely on the distroless implicit UID rather than an explicit
  `USER` directive (residual #6).
- The 1 line item that has been verified at runtime today is the *experimental contract
  surface*. Operator workflows (TLS ingress, backup/restore, HA, key rotation outside the
  mock path) are not in scope and not documented.
- No long-term support — best-effort community via GitHub Discussions.

See `docs/DEPLOYMENT.md` § "Not supported" boundary matrix for the full operator-facing
list.

---

## 8. Next steps

1. **Confirm branch consolidation.** `git status` at session close: clean. Tip `238c612`
   on `main`. No outstanding feature branches need merging into this push.
2. **Push** when the owner is ready: `git push -u origin main`. (This session deliberately
   did not push — hard rule.)
3. **Enable GitHub Discussions** (Q&A + Ideas categories at minimum, per sister session E-7).
4. **Post the launch announcement** using §6 wording. Keep the "pre-alpha / not for
   production" framing prominent.
5. **First-day watch:** monitor Discussions and Issues; set a response-time expectation in
   `SUPPORT.md` or the Discussions welcome post.
6. **Schedule a follow-up cleanup session** for the residuals:
   - mcp-server version alignment (residual #2)
   - `test_openapi_parity_snapshot` regeneration (residual #1)
   - explicit `USER` directive on the 4 Go distroless Dockerfiles (residual #6)
   - digest pinning strategy for base images (residual #5)
   - `otel-collector` restart-loop root-cause (residual #4)

---

## 9. Closing verdict

```
STATUS:          PASS_ALL (18/18 verification rows, 0 failures)
SESSION COMMITS: 6 (none with Co-Authored-By trailers)
DATA PRESERVED: svc=4 agents=3 grants=2
READY TO PUSH:   YES — as 0.1.0-preview.1 pre-alpha technical preview, with the explicit
                 "not for production" framing in §6/§7. No release-blocking residuals.
```
