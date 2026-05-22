# Public GitHub Release Readiness — Progress Log

Append-only. Most recent entry at the top.

---

## 2026-05-16 — REL-FINAL: independent verification + closing report

**Role:** Fresh Opus reviewer + report writer. No prior session context.

**Task:** Re-run all 18 verification rows from the 5 landed chunks independently and produce
`99-report.md` (~200-300 lines).

**Approach:** Read-only verification only. Did not modify code. Did not push. Did not add
`Co-Authored-By` trailers. Captured command output for every row.

**Result — 18/18 PASS:**

- **F1** workflow YAMLs parse: exit 0, `workflow yaml: ok`
- **F2** OpenAPI semantic validation: exit 0, `openapi: ok`
- **F3** OpenAPI internal refs: 355 refs, 0 unresolved
- **F4** JSON schemas valid: exit 0, `json schemas: ok`
- **F5** MCP tools YAML valid: exit 0, `ok`
- **F6** No CI masks: 2 hits, both comment-only (`Makefile:168`, `.github/workflows/ci.yml:172`) — PASS
- **F7** No placeholders: 4 hits, all forbid-context (CONTRIBUTING.md:168, RELEASE.md:179, PR template, roadmap row) — PASS
- **F8** 8 target files free of `0.1.0-experimental`: exit 1 (no matches)
- **F9** Canonical 5 files = `0.1.0-preview.1`: all 5 confirmed
- **F10** Runtime FastAPI: `curl /openapi.json | … info.version` → `0.1.0-preview.1`
- **F11** 6 USER directives: 6/6 hits
- **F12** 5 HEALTHCHECK directives: 5/5 hits (seed-job correctly omitted)
- **F13** Running containers uid≠0: `uid=65532(nonroot)` ×3, `uid=1000(node)`, `uid=65532(oauth2proxy)` — all non-root
- **F14** DEPLOYMENT.md audit: 7 USER mentions; REL-3/2026-05-16 annotations at lines 96/116/119/142
- **F15** Screenshot dirs ignored: status empty; check-ignore matched at `.gitignore:20`
- **F16** No `Co-Authored-By` trailers: 6 session commits clean
- **F17** Data preserved: `svc=4 agents=3 pg=2`
- **F18** Matrix ✅ count: 5 session rows green

**Documented residuals** (out of session scope, do not block push):

1. `test_openapi_parity_snapshot` pre-existing FAIL — router drift, unrelated
2. mcp-server still on `0.1.0-experimental` in `main.py:55`, `tools/jsonrpc.py:62`,
   `tools/landing.py:86` — separate refresh chunk
3. Auto-generated `*.pb.go` carry `0.1.0-experimental` headers — regenerate on next proto change
4. `otel-collector` restart loop — pre-existing, unrelated
5. Dockerfile `@sha256` digest pinning still deferred (owner decision)
6. 4 Go service Dockerfiles use distroless implicit UID 65532 (`broker`,
   `vault-adapter`, `proxy-plugin`, `kong-syncer`) — explicit `USER` directive recommended
   but not required for pre-alpha

**Verdict:** READY TO PUSH as `0.1.0-preview.1` pre-alpha technical preview, with the
explicit "not for production" framing in `99-report.md` §6/§7.

**Matrix:** P1-6 ⬜ → ✅

**Files touched:**
- `team/remediation/2026-05-16-public-github-release-readiness/99-report.md` (NEW)
- `team/remediation/2026-05-16-public-github-release-readiness/02-matrix.md` (P1-6 flipped; inherited-state note added)
- `team/remediation/2026-05-16-public-github-release-readiness/04-progress.md` (this entry)

**Commit:** `docs: close public-github-release-readiness remediation`

**Confirmed:** no `Co-Authored-By: Claude` trailer per global rules and per F16 of this very verification.

---

## 2026-05-16 — Session opened

Session directory created: `team/remediation/2026-05-16-public-github-release-readiness/`

### Pre-state snapshot

- Branch: `main` (consolidated; `feature/developer-install-script` fast-forwarded into main earlier)
- Tip: `46f8707 minor changes`
- Recent context (10 commits):
  - `46f8707` minor changes
  - `80011d1` feat: implement developer install script (install.sh) — Kiro
  - `66372a0` docs(roadmap): apply 5 polish items from reviewer feedback
  - `8dfcce2` docs: update product roadmap with cohort analysis + launch milestones
  - `7f5fe29` docs: close oss readiness remediation
  - `9705c16` docs: add first-user walkthroughs for public preview
  - `65c007d` docs: refine public marketing narrative
  - `a1abb8a` build: define technical preview release pipeline
  - `46e91cf` ci: enforce public readiness gates
  - `e36492c` docs: add open source governance templates
- Working tree: clean except 2 untracked screenshot dirs (`admin-ui/screenshots-chunk-g/`, `admin-ui/screenshots-verify/`)
- Tags: `pre-deeper-scrub-backup`, `pre-scrub-backup` (no release tags yet)
- Remote: `origin = https://github.com/WeLikeCode/mintkey.git` (set, never pushed)
- Version metadata in code: `0.1.0-preview.1` across 5 canonical files (from OSS-4)

### Sister session

`team/remediation/2026-05-16-oss-readiness/` closed earlier today (commit `7f5fe29`). 8 chunks + closing report. DoD items 1–12 of this session map onto OSS-readiness deliverables. **This session does NOT trust those claims** — BASELINE-REVIEWER re-verifies independently.

### Step 0 dispatch

BASELINE-REVIEWER (read-only) being dispatched now with the user's verbatim prompt from `00-plan.md`.

---

## 2026-05-16 — Step 0 BASELINE-REVIEWER returned

**Verdict:** 2 RED / 3 YELLOW / 12 GREEN. Not release-ready.

### RED (must fix)
- **R-4 / REL-2**: `openapi.yaml:1304` references undefined `#/components/responses/UnprocessableEntity`. `openapi_spec_validator.validate()` exits non-zero. CI `lint-contracts` job will fail on first push.
- **R-5 / REL-1**: `.github/workflows/ci.yml:90` — bare-scalar `run:` value contains unquoted `: `. PyYAML + ruamel.yaml + yamllint all reject. GH Actions strict go-yaml.v3 likely rejects the file → ALL ci.yml jobs silently won't run.

### YELLOW (owner-discretion)
- **R-11 / REL-3**: 10 Dockerfiles lack USER/HEALTHCHECK/digest. Trivy + Scorecard will flag. Documented deferral.
- **R-13 / REL-4**: 8 secondary surfaces still say `0.1.0-experimental` (incl. runtime `admin-api/main.py:60` that breaks `test_openapi_parity`).
- **R-15 / REL-5**: 2 untracked screenshot dirs not in `.gitignore`.

### GREEN (12 items already in good shape)
LICENSE, security email, no placeholders, JSON schemas, MCP YAML, CI no-masks, CONTRIBUTING co-author-free, governance files, dep/security automation, .dockerignore, canonical version files, no-Co-Author session-wide.

### Evidence-vs-claim gap from sister session
The prior OSS-readiness `99-report.md:104` claimed "openapi.yaml YAML parse: OK" — accurate for `yaml.safe_load` (structural), but never invoked `openapi_spec_validator.validate()` (semantic). Same blind spot caused the ci.yml issue to slip through. This session's REL-2 verification fixes that by actually running the canonical validators.

### Next
Surfacing YELLOW forks to user for the 3 owner-discretion items; will dispatch Wave 1 (REL-1 + REL-2) regardless since they're RED blockers.

---

## 2026-05-16 — REL-1 IMPLEMENTER: fix ci.yml:90 bare-scalar YAML parse error

**Task:** R-5 / REL-1 — `.github/workflows/ci.yml:90` bare-scalar `run:` value contained unquoted `: ` inside a YAML plain scalar, causing all strict YAML parsers (PyYAML, ruamel.yaml, go-yaml.v3) to reject the file.

**Approach:** Option A — converted bare `run:` scalar to `run: |` literal block, matching the existing pattern used by the OpenAPI and JSON Schema validators in the same job.

**Change:** `.github/workflows/ci.yml` line 90 — 1 line changed (bare scalar → `run: |` + indented command on next line).

**Verification:**
- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml: ok')"` → exit 0, output `ci.yml: ok`
- `python3 -c "import yaml, pathlib; [yaml.safe_load(p.read_text()) for p in pathlib.Path('.github/workflows').glob('*.yml')]; print('workflow yaml: ok')"` → exit 0, output `workflow yaml: ok`
- `yamllint .github/workflows/ci.yml`: no parse errors; only pre-existing warnings (missing `---`, truthy value) and line-length lint on the python3 command (pre-existing, not introduced by this change).

**Matrix:** P0-4 (R-5 / REL-1) ⬜ → ✅

**Commit:** `fix(ci): convert ci.yml:90 to literal-block run: scalar (REL-1)`

**Files touched:** `.github/workflows/ci.yml`, `02-matrix.md`, `04-progress.md`

---

## 2026-05-16 — REL-2 IMPLEMENTER: define UnprocessableEntity response in openapi.yaml

**Task:** R-4 / REL-2 — `openapi.yaml:1304` (rotate-key POST 422) referenced `#/components/responses/UnprocessableEntity` which was not defined in `components.responses`. `openapi_spec_validator.validate()` exits non-zero, breaking the CI `lint-contracts` job.

**Approach:** Option A — added `UnprocessableEntity` to `components.responses` between `Conflict` and `RateLimited`, matching the existing `application/problem+json` + inline `example` style used by all adjacent response definitions.

**Change:** `docs/architecture/contracts/rest/openapi.yaml` — 11 lines added (the `UnprocessableEntity` response definition). Example `detail` reflects the actual rotate-key `expires_in` validation constraint documented in the endpoint description.

**Verification:**
- `openapi_spec_validator.validate()` → exit 0, output `openapi: ok`
- `yaml.safe_load()` → exit 0, output `structural parse: ok`
- Internal `$ref` sweep → 355 internal refs, 0 UNRESOLVED

**Matrix:** P0-3 (R-4 / REL-2) ⬜ → ✅

**Commit:** `fix(openapi): define UnprocessableEntity response (REL-2)`

**Files touched:** `docs/architecture/contracts/rest/openapi.yaml`, `02-matrix.md`, `04-progress.md`

---

## 2026-05-16 — REL-5 IMPLEMENTER: add admin-ui screenshot dirs to .gitignore

**Task:** R-15 / REL-5 — Two untracked dirs (`admin-ui/screenshots-chunk-g/`, `admin-ui/screenshots-verify/`) sat in the working tree with no `.gitignore` coverage, creating risk that `git add -A` would accidentally commit them.

**Approach:** Added `admin-ui/screenshots-*/` glob to `.gitignore` near existing admin-ui artefact rules (after `install-*.log`), with a brief comment identifying these as Playwright/test screenshot output. The glob covers both existing siblings and any future `screenshots-*` dirs created by test runs.

**Change:** `.gitignore` — 3 lines added (blank separator, comment, glob pattern).

**Verification:**
- `git status --short | grep screenshots` → empty (both dirs now ignored)
- `git check-ignore -v admin-ui/screenshots-chunk-g admin-ui/screenshots-verify` → both matched at `.gitignore:20:admin-ui/screenshots-*/`

**Matrix:** R-15 / REL-5 ⬜ → ✅

**Commit:** `chore(gitignore): hide admin-ui playwright screenshot dirs (REL-5)`

**Files touched:** `.gitignore`, `02-matrix.md`, `04-progress.md`

---

## 2026-05-16 — REL-4 IMPLEMENTER: align 8 secondary 0.1.0-experimental surfaces to 0.1.0-preview.1

**Task:** R-13 / REL-4 — 8 secondary surfaces still carried `0.1.0-experimental` against the canonical `0.1.0-preview.1` set by OSS-4. Critical surface: `admin-api/src/admin_api/main.py:60` (FastAPI runtime `version=` field, directly reflected in `/openapi.json`).

**Approach:** Read-then-edit each file to verify exact location before patching. Single target string `0.1.0-experimental` → `0.1.0-preview.1` per file; formatting preserved (quotes, YAML alignment, proto comment spacing).

**Changes:**
1. `SECURITY.md:11` — version reference in supported-versions section
2. `admin-api/src/admin_api/main.py:60` — FastAPI `version="0.1.0-preview.1"` (CRITICAL)
3. `docs/architecture/contracts/events/audit-event.schema.json:7` — `x-mintkey-version`
4. `docs/architecture/contracts/events/change-event.schema.json:7` — `x-mintkey-version`
5. `docs/architecture/contracts/mcp/tools.yaml:53` — `server.version`
6. `docs/architecture/contracts/vault-adapter/vault.proto:4` — `// Version :` comment
7. `docs/architecture/contracts/README.md:9` — version reference in stability description
8. `docs/architecture/contracts/events/span-attributes.md:3,125` — header + resource attribute example (2 occurrences replaced)

**Verification:**
- `rg '0.1.0-experimental'` tree-wide (excl. `_archive/`, `.git/`, `*.lock`): 0 hits in runtime/contract files; remaining hits are team/remediation session docs (historical context), auto-generated `*.pb.go` files, `mcp-server/` (separate surface, out of scope for this chunk), and `CHANGELOG.md` prose — all confirmed non-target.
- `rg -nc '0.1.0-preview.1'` on all 8 target files: ≥1 per file ✓
- `json.load(audit-event.schema.json)` → ok; `json.load(change-event.schema.json)` → ok
- `yaml.safe_load(tools.yaml)` → ok
- `protoc --proto_path=... vault.proto --descriptor_set_out=/dev/null` → exit 0 ok
- `docker compose build admin-api` → built; `docker compose up -d --force-recreate admin-api` → started
- `curl -s http://localhost:8080/openapi.json | python3 -c "... d['info']['version']"` → `0.1.0-preview.1` ✓
- `pytest tests/ -k "openapi_parity" -v`: 4 tests PASS; `test_openapi_parity_snapshot` FAIL — pre-existing snapshot mismatch on router structure (`health` prefix `/v1/health`→`/metrics`, new `service_templates` router not in stored snapshot); this failure predates REL-4 and is unrelated to the version string change.

**Matrix:** P1-5 (R-13 / REL-4) ⬜ → ✅

**Commit:** (pending — no commit issued; no push)

**Files touched:** `SECURITY.md`, `admin-api/src/admin_api/main.py`, `docs/architecture/contracts/events/audit-event.schema.json`, `docs/architecture/contracts/events/change-event.schema.json`, `docs/architecture/contracts/mcp/tools.yaml`, `docs/architecture/contracts/vault-adapter/vault.proto`, `docs/architecture/contracts/README.md`, `docs/architecture/contracts/events/span-attributes.md`, `01-orchestrator-chunks.md`, `02-matrix.md`, `04-progress.md`

---

## 2026-05-16 — REL-3 IMPLEMENTER: USER + HEALTHCHECK on 6 non-distroless Dockerfiles

**Task:** R-11 / REL-3 — The 6 non-distroless Dockerfiles (admin-api, mcp-server, admin-ui, mock-backend, seed-job, jaeger-auth) had no `USER` directive (all ran as root) and no Dockerfile `HEALTHCHECK` instruction. Digest pinning was explicitly deferred by owner.

**Approach:**
- Python services (admin-api, mcp-server, mock-backend, seed-job): `RUN useradd -u 65532 -M -s /sbin/nologin nonroot && chown -R 65532:65532 /app` then `USER 65532:65532`. UID 65532 matches distroless `nonroot` convention for consistency across the fleet.
- admin-ui (node:22-slim): node:22-slim ships with pre-created `node` user (UID 1000); used `RUN chown -R node:node /app && USER node`.
- jaeger-auth (alpine): `RUN adduser -D -u 65532 -s /sbin/nologin oauth2proxy && USER 65532:65532`. Also added `wget` to `apk add` so the Dockerfile HEALTHCHECK can use `wget -qO- http://localhost:4180/ping`.
- HEALTHCHECK: python3 urllib inline one-liner for python services (no curl in slim); `node -e require('http').get(...)` for admin-ui; `wget -qO-` for jaeger-auth. Intervals match docker-compose.yml healthchecks (compose overrides Dockerfile at runtime; Dockerfile provides fallback for `docker run`).
- seed-job: USER 65532 added; HEALTHCHECK omitted (one-shot init container).

**Volume permission issue (blocked, resolved before reporting):** The existing `bootstrap_secrets` Docker volume had files owned by root (written by the prior root seed-job). After applying USER 65532, both seed-job and jaeger-auth failed with `PermissionError` on volume reads/writes. Per hard rule 6, this was documented rather than silently reverted. Fix: one-time `chown -R 65532:65532` on the mounted volume via a temporary alpine container. Documented in DEPLOYMENT.md as an operator upgrade note. Fresh installs are unaffected (Docker creates the volume directory owned by the first writer, now UID 65532).

**Changes (8 files):**
1. `admin-api/Dockerfile` — `useradd 65532`, `USER 65532:65532`, `HEALTHCHECK python3 :8080/v1/health`
2. `mcp-server/Dockerfile` — `useradd 65532`, `USER 65532:65532`, `HEALTHCHECK python3 :8082/health`
3. `admin-ui/Dockerfile` — `chown node:node /app`, `USER node`, `HEALTHCHECK node http.get :8081/health`; also added `wget` to alpine layer for jaeger-auth
4. `mock-backend/Dockerfile` — `useradd 65532`, `USER 65532:65532`, `HEALTHCHECK python3 :8999/health`
5. `seed-job/Dockerfile` — `useradd 65532`, `USER 65532:65532`, no HEALTHCHECK (one-shot)
6. `jaeger-auth/Dockerfile` — `adduser 65532 oauth2proxy`, `USER 65532:65532`, `HEALTHCHECK wget :4180/ping`; added `wget` to `apk add`
7. `docs/DEPLOYMENT.md` — audit table updated (0→6 USER, 0→5 HEALTHCHECK); operator upgrade note added
8. `01-orchestrator-chunks.md` — REL-3 ⬜ → ✅

**Verification:**
- `docker compose build admin-api mcp-server admin-ui mock-backend seed-job jaeger-auth` → all 6 Built (no errors)
- Pre-snapshot: svc=4 agents=3 grants=2
- `docker compose up -d --force-recreate admin-api mcp-server admin-ui mock-backend jaeger-auth` → all started
- `docker compose run --rm seed-job` → exit 0; all Keycloak steps idempotent; secrets refreshed
- `docker compose ps` → admin-api, mcp-server, admin-ui, mock-backend, jaeger-auth all `Up (healthy)`
- `id` check per service: `uid=65532(nonroot)` for admin-api, mcp-server, mock-backend; `uid=1000(node)` for admin-ui; `uid=65532(oauth2proxy)` for jaeger-auth — all uid≠0
- `docker inspect .Config.Healthcheck` — non-null JSON with Test/Interval on all 5 long-running services
- Post-snapshot: svc=4 agents=3 grants=2 → `DATA PRESERVED`

**Matrix:** P1-4 (R-11 / REL-3) ⬜ → ✅

**Files touched:** `admin-api/Dockerfile`, `mcp-server/Dockerfile`, `admin-ui/Dockerfile`, `mock-backend/Dockerfile`, `seed-job/Dockerfile`, `jaeger-auth/Dockerfile`, `docs/DEPLOYMENT.md`, `01-orchestrator-chunks.md`, `02-matrix.md`, `04-progress.md`
