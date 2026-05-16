# Public GitHub Release Readiness — Progress Log

Append-only. Most recent entry at the top.

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
