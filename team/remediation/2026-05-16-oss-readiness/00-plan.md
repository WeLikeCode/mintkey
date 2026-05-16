# Mintkey OSS Readiness Remediation — Session Plan

**Session:** `2026-05-16-oss-readiness`
**Driver:** `remediation-orchestrator` skill (`~/.claude/skills/remediation-orchestrator/SKILL.md`)
**Status:** Phase 0 (audit + matrix) — implementation paused until matrix exists.

## Mission

Make Mintkey shareable with the world as a credible open-source technical preview without overclaiming production readiness. Address the gaps identified in the OSS readiness review: public OSS hygiene, technical launch blockers, how-to-use documentation, production-readiness documentation, release/security automation, and marketing positioning.

## Session files

| File | Purpose |
|---|---|
| `00-plan.md` | This file — mission, hard rules, chunk catalog (the original mega-prompt). |
| `01-orchestrator-chunks.md` | Ordered chunk catalog with ownership and dispatch state. Built after Phase 0. |
| `02-matrix.md` | OSS readiness audit tracking matrix. Built by Phase 0 researcher. |
| `03-escalations.md` | Decisions requiring owner input — answered before chunk dispatch. |
| `04-progress.md` | Live progress log. Append-only. |
| `99-report.md` | Closing report with commands, exit codes, residual risks, launch wording. |

---

## Known Findings To Address

From the initial OSS readiness review (project owner):

1. `README.md` claims Apache-2.0, but no root `LICENSE` file exists.
2. Public placeholders remain: `<repo-url>`, `<TBD-by-architect>`, `maintainers@example.invalid`.
3. `CONTRIBUTING.md` requires LLM co-author trailers, while project/user instructions forbid them. Resolve in favor of no co-author trailers.
4. CI has non-blocking gates: Mermaid uses `|| true`; Makefile lint masks Python failures with `|| true`.
5. No visible public issue templates, PR template, Code of Conduct, Support policy, Governance policy, or public maintainer model.
6. No dependency-update config found: Dependabot/Renovate missing.
7. No visible secret scanning, CodeQL, container scanning, SBOM/provenance, or release workflow.
8. No `.dockerignore` files found.
9. Dockerfiles need hardening review: explicit non-root users, digest pinning strategy, build/runtime separation, healthcheck assumptions.
10. Python dependency ranges use broad `>=`; release reproducibility needs a deliberate policy.
11. Package/version metadata is inconsistent: `admin-ui` is `1.0.0`, project docs say pre-alpha, OpenAPI says `0.1.0-experimental`, `mintkey-models` says `0.1.0`.
12. Deployment docs are still architecture-sketch oriented and do not provide a complete production readiness path.
13. Examples are placeholders, not runnable Mintkey examples.
14. Marketing pages are useful but doc-like; need clearer positioning, visuals, CTAs, comparison, and demo path.
15. Need a simple mock-backend-only local demo that avoids requiring external PATs.
16. Need client-specific MCP setup guides.

---

## Hard Rules (apply to every chunk)

- Follow `AGENTS.md` and `CLAUDE.md`.
- Do not add `Co-Authored-By` trailers to any commit.
- Do not edit accepted ADRs.
- Do not weaken security claims or remove pre-alpha warnings.
- Do not claim production readiness.
- Do not introduce new architecture decisions without an ADR/proposal path.
- Do not alter application behavior unless required by the remediation chunk.
- Keep changes surgical and traceable to this remediation.
- Every chunk needs verification output with commands and exit codes.
- If a command is expected to fail before the fix, capture the failure first.
- If a chunk needs a project-owner decision, stop and write it to `03-escalations.md`.

---

## Phase 0 — Audit And Matrix (current phase)

**Goal:** populate `02-matrix.md` with verified findings before any source edit. Identify escalations and write them to `03-escalations.md`.

**Researcher brief:** see dispatch in `04-progress.md`.

Phase 0 output:
- Complete matrix.
- Escalations file with owner-decision items.
- Single commit: `docs(remediation): create oss readiness matrix`.

**No source-code edits until Phase 0 lands.**

---

## Chunk Catalog (8 chunks — dispatch after Phase 0)

See `01-orchestrator-chunks.md` for the dispatched form. Original mega-prompt content reproduced below as the source of truth.

### OSS-1 — Public Legal And Placeholder Hygiene
Goal: remove launch-blocking public placeholders and add minimum legal surface.
Tasks: add root `LICENSE` (Apache-2.0 pending owner confirm); add `NOTICE` if needed; replace `<repo-url>`, `<TBD-by-architect>`, `maintainers@example.invalid` placeholders; replace OpenAPI contact placeholder; update matrix.
Commit: `docs: prepare public legal and contact surface`

### OSS-2 — Governance And Contribution Surface
Goal: make the repo legible and welcoming without lowering engineering standards.
Tasks: add `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml`; add `.github/pull_request_template.md`; add `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `GOVERNANCE.md`; update `CONTRIBUTING.md` to remove mandatory LLM co-author trailer; keep SDD/ADR/audit/verification intact; update matrix.
Commit: `docs: add open source governance templates`

### OSS-3 — CI Gates And Security Automation
Goal: make CI trustworthy for public contributors.
Tasks: make Mermaid gate blocking; remove `|| true` from Makefile lint; add CodeQL, dependency-review, container-scan, optional Scorecard workflows; add Dependabot/Renovate for Actions/Docker/Go/npm/Python; update matrix.
Commit: `ci: enforce public readiness gates`

### OSS-4 — Release And Supply Chain Packaging
Goal: define how users get reproducible technical-preview artifacts.
Tasks: align version metadata; decide on `admin-ui` visibility; add release checklist; add GHCR image publishing workflow (owner-confirmed); SBOM/provenance if feasible; commit-SHA + semver-prerelease tags; update matrix.
Commit: `build: define technical preview release pipeline`

### OSS-5 — Container And Runtime Hardening
Goal: make the Docker surface credible for public self-hosters.
Tasks: add `.dockerignore` (root + per-service where needed); review all Dockerfiles for runtime user + healthcheck deps; document dev-only secrets + override path; add `docs/DEPLOYMENT.md` or `docs/PRODUCTION-READINESS.md` with supported/unsupported boundaries; update matrix.
Commit: `build: harden container packaging for public preview`

### OSS-6 — How-To-Use Documentation
Goal: make a new user successful without reading the architecture folder.
Tasks: 10-minute local mock-only demo; GitHub PAT demo cleanup; MCP client guides (Claude Desktop, Claude Code, Cursor, mcp-cli); operator cookbook (add service → call through proxy → rotate → revoke → audit → trace); expected outputs and failure modes; update matrix.
Commit: `docs: add first-user walkthroughs for public preview`

### OSS-7 — Marketing Package
Goal: make the project understandable and shareable.
Tasks: sharpen headline; CTAs (try locally / read security / view arch / contribute); comparison section vs alternatives; supported auth schemes table; "why now / who it is for"; keep pre-alpha warning prominent; update matrix.
Commit: `docs: refine public marketing narrative`

### OSS-8 — Final Verification And Public Launch Report
Goal: prove the repo is ready for a technical-preview announcement.
Tasks: run validators, unit/architecture/acceptance tests, Go, UI tests, smoke, secret/placeholder greps; produce `99-report.md`; document residuals; explicit "not production ready" line; update `PROGRESS.md` only if convention allows.
Commit: `docs: close oss readiness remediation`

---

## Escalation Rules

Phase 0 researcher MUST stop and write `03-escalations.md` for any of these that are unknown:

- Final GitHub repository URL.
- Final maintainer/security email.
- Whether Apache-2.0 is definitely the intended license.
- Whether GHCR is the intended image registry.
- Whether the project wants public Discussions enabled.
- Whether release automation should publish images immediately or only dry-run.
- Whether production docs should be "unsupported but possible" or "explicitly out of scope."

**Do not guess.**

---

## Final Acceptance Criteria

The remediation is complete only when:

1. Root license exists.
2. Security contact is real or explicitly escalated.
3. No public placeholders remain except intentional examples.
4. CI gates do not mask failures.
5. Governance templates exist.
6. Contribution docs no longer require co-author trailers.
7. Dependency/security automation exists or is explicitly deferred.
8. A new user has a mock-only local demo path.
9. MCP client setup docs exist.
10. Release/versioning policy is coherent.
11. Marketing pages have clear positioning and CTA.
12. `99-report.md` documents commands, exit codes, and residual risks.
13. No production-readiness claims exceed the verified state.

## Final response format

- Summary of completed chunks.
- Verification commands with exit codes.
- Remaining escalations.
- Recommended public launch wording.
- Exact files changed.
