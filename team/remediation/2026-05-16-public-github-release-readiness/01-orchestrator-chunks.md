# Public GitHub Release Readiness — Chunk Catalog

**Session:** 2026-05-16-public-github-release-readiness
**Baseline:** REL-BASELINE returned 2 RED + 3 YELLOW + 12 GREEN (see `02-matrix.md`).

## Universal hard rules

- No `Co-Authored-By: Claude` trailer (per `~/.claude/CLAUDE.md`).
- No `--no-verify`.
- No `docker compose down -v`.
- No edits to accepted ADRs.
- Surgical changes; one logical change per commit.
- Validate via tools; every "done" claim carries command output.
- Update `02-matrix.md` row(s) you close before commit.

## Dispatch plan

### Wave 1 (parallel, RED fixes — required before push)

| # | Chunk | Owner files | Status |
|---|---|---|---|
| REL-1 | Fix `ci.yml:90` malformed YAML scalar | `.github/workflows/ci.yml` | ⬜ pending — Wave 1 |
| REL-2 | Define `UnprocessableEntity` response in openapi.yaml | `docs/architecture/contracts/rest/openapi.yaml` | ⬜ pending — Wave 1 |

### Wave 2 (parallel, YELLOW polish — owner-discretion)

| # | Chunk | Owner files | Status |
|---|---|---|---|
| REL-3 | Container hardening (USER + HEALTHCHECK + optional digest pin) | 6 non-distroless Dockerfiles | ⬜ pending — owner decision |
| REL-4 | Align secondary `0.1.0-experimental` surfaces to canonical | 8 files incl. `admin-api/src/admin_api/main.py:60` | ⬜ pending — owner decision |
| REL-5 | Gitignore screenshot dirs | `.gitignore` | ⬜ pending — owner decision |

### Wave 3 (after Wave 1+2)

| # | Chunk | Owner files | Status |
|---|---|---|---|
| REL-FINAL | Final reviewer matrix + 99-report.md | matrix + report | ⬜ pending |

## Round history (append-only)

- 2026-05-16: Step 0 BASELINE-REVIEWER (Opus) returned PASS-with-RED. 2 RED items identified; chunk catalog built.
