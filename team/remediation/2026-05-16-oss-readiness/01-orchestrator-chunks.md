# OSS Readiness — Chunk Catalog + Dispatch State

**Session:** 2026-05-16-oss-readiness
**Driver:** `remediation-orchestrator` skill
**Phase 0:** ✅ done (matrix + escalations committed in `4e662769`)
**Escalations:** ✅ all 7 resolved (see `03-escalations.md`)

## Locked decisions (apply to every chunk)

- **License:** Apache-2.0 (E-1)
- **Repo URL:** `https://github.com/WeLikeCode/mintkey` (clone: `https://github.com/WeLikeCode/mintkey.git`) (E-2)
- **Security email:** `the+security@ciprianiacobescu.com` (E-3)
- **Container registry:** `ghcr.io/welikecode` (E-4) — only matters for E-5 deferral
- **Release workflow:** DEFERRED — document path in `docs/RELEASE.md` only; no GHCR publish workflow this session (E-5)
- **Deployment doc scope:** "Unsupported but possible" with prominent pre-alpha warning (E-6)
- **GitHub Discussions:** enabled — SUPPORT.md links there (E-7)

## Universal hard rules (every implementer brief inherits these — pulled from skill)

- No `Co-Authored-By: Claude` trailer on any commit (per `~/.claude/CLAUDE.md`)
- No `--no-verify` on commits
- No `docker compose down -v` (pre-existing data + 3 active agents must be preserved)
- No edits to accepted ADRs (`docs/architecture/01-architecture/adr/0001..0020`)
- No production-readiness claims; preserve pre-alpha posture
- Validate via tools: every "done" claim carries command output
- Surgical changes; one logical change per commit
- Update `02-matrix.md` row(s) you closed before commit

## Chunk dispatch plan (waves)

### Wave 1 (sequential — foundation)
| # | Chunk | Owner files | Status |
|---|---|---|---|
| OSS-1 | Legal + placeholder hygiene | `LICENSE`, `NOTICE`?, `README.md`, `QUICKSTART.md`, `SECURITY.md`, `marketing/index.html`, `openapi.yaml` (info.contact) | ⬜ pending — Wave 1 |

### Wave 2 (parallel after OSS-1)
| # | Chunk | Owner files | Status |
|---|---|---|---|
| OSS-2 | Governance + contribution surface | `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml`, `.github/pull_request_template.md`, `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `GOVERNANCE.md`, `CONTRIBUTING.md` (remove Co-Author requirement) | ⬜ pending — Wave 2 |
| OSS-5 | Container + runtime hardening | `.dockerignore` (root + per-service), Dockerfile reviews, `docs/DEPLOYMENT.md` | ⬜ pending — Wave 2 |

### Wave 3 (parallel after Wave 2)
| # | Chunk | Owner files | Status |
|---|---|---|---|
| OSS-3 | CI gates + security automation | `.github/workflows/{codeql,dependency-review,scorecard,container-scan}.yml`, `.github/dependabot.yml`, `Makefile` (`||true` removal), existing CI files | ⬜ pending — Wave 3 |
| OSS-4 | Versioning policy + release doc | `admin-ui/package.json`, `mintkey-models/pyproject.toml`, `README.md` (version badge), `CHANGELOG.md` (header normalize), `openapi.yaml` (version), `docs/RELEASE.md` (NEW — describes manual release path; no workflow) | ⬜ pending — Wave 3 |

### Wave 4 (after Waves 2+3)
| # | Chunk | Owner files | Status |
|---|---|---|---|
| OSS-6 | How-to documentation | `docs/guides/10min-mock-demo.md` (NEW), `docs/guides/mcp-clients/{claude-desktop,claude-code,cursor,mcp-cli}.md` (NEW), `docs/HOW-TO.md` (operator cookbook expansion), `examples/` runnable scripts | ⬜ pending — Wave 4 |
| OSS-7 | Marketing package | `marketing/index.html`, `marketing/architecture.html`, `marketing/security.html` (headline, CTAs, comparison, "why now", supported auth schemes) | ⬜ pending — Wave 4 |

### Wave 5 (after Wave 4)
| # | Chunk | Owner files | Status |
|---|---|---|---|
| OSS-8 | Final verification + report | `team/remediation/2026-05-16-oss-readiness/{02-matrix,04-progress,99-report}.md` | ⬜ pending — Wave 5 |

## Round history (append-only)

- 2026-05-16: Phase 0 dispatched; researcher returned PASS (commit `4e662769`); 33 findings, 7 escalations, all 7 escalations resolved by owner within the hour.
