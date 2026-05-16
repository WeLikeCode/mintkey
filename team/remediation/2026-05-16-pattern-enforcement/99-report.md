# Pattern Enforcement — Closing Report

**Session:** 2026-05-16-pattern-enforcement
**Status:** COMPLETE
**Date:** 2026-05-16
**Driver:** `remediation-orchestrator` skill

## Executive summary

Made Mintkey's remediation pattern mandatory across Claude Code, Codex, opencode, and GitHub PRs. Issue intake is now required before any remediation begins; the 9-row decision table is byte-identical across `team/remediation/README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md` (R-27 verified). The Claude Code skill at `~/.claude/skills/remediation-orchestrator/` has a Step 0 intake-gate; Codex + opencode read the same decision table from repo-root `AGENTS.md` per their convention (F1 decision).

## Commits

| # | Commit | Chunk | Files |
|---|---|---|---|
| 1 | `f86135e` | session setup | `00-plan.md` |
| 2 | `c36f236` | PE-2 | `team/remediation/README.md` + `CONTRIBUTING.md` |
| 3 | `b59a63b` | PE-4 | `.github/pull_request_template.md` |
| 4 | `b5a10f3` | PE-1 | `ISSUE_INTAKE_TEMPLATE.md` + `SESSION_TEMPLATE/*` + skill update + `references/issue-intake.md` |
| 5 | `1c4e068` | PE-3 | `AGENTS.md` + `CLAUDE.md` lock-step |

## Final acceptance criteria — verified by ENFORCE-REVIEW (Opus)

| AC | Status | Notes |
|---|---|---|
| Issue intake template exists with 9 fields | ✅ | 79 lines; 9 fields verbatim |
| Session template directory scaffolds 6 files + symlink | ✅ | `cp -r` workflow works; symlink resolves |
| Skill SKILL.md has Step 0 intake-gate | ✅ | frontmatter description extended; section added |
| Skill references/issue-intake.md project-agnostic | ✅ | 0 Mintkey-specific identifiers |
| Decision table identical in 4 locations | ✅ | byte-identical MD5 across README, CONTRIBUTING, AGENTS, CLAUDE |
| README has intake + decision rules + PASS/FAIL/ESCALATE/3-strike | ✅ | new sections at lines 60-95 |
| CONTRIBUTING has "Remediation vs Spec-Driven Work" | ✅ | line 48; references the canonical table |
| AGENTS.md ↔ CLAUDE.md lock-step | ✅ | new-section diff = 1 line (documented Claude/Codex opener) |
| PR template has 5 required sections in order | ✅ | Change Type → Required Provenance → Issue Definition → Verification → Agent Rules |
| All 5 PR sections have verbatim checkboxes | ✅ | 5 / 5 / 4 / 5 checkboxes |
| No Co-Authored-By in any session commit | ✅ | grep verified across 5 commits |
| No source code touched | ✅ | only docs + templates + skill + PR template |
| No `--no-verify` used | ✅ | grep verified |
| No accepted ADRs edited | ✅ | `docs/architecture/01-architecture/adr/` untouched |

26/28 reviewer rows PASS. 2 cosmetic verbatim-vs-semantic discrepancies (R-14 anti-pattern phrasing; R-18 "was" inserted in PR template) — semantic content correct, grep pattern matched looser wording. Not a content issue.

## Locked decisions (forks F1-F4)

- **F1**: opencode reads root `AGENTS.md` — no `.opencode/` symlink (relies on opencode CLI convention)
- **F2**: `SESSION_TEMPLATE/ISSUE_INTAKE.md` is a symlink to `../ISSUE_INTAKE_TEMPLATE.md` (matches existing repo symlink patterns)
- **F3**: `SESSION_TEMPLATE/` is a static directory (operators run `cp -r` to scaffold)
- **F4**: Even doc typos + dep bumps fill the Issue Definition section in the PR template ("direct PR allowed" = "no session folder needed", NOT "no intake fields needed")

## How a future remediation starts

```bash
# 1. User describes a concrete fix.
# 2. Agent (Claude / Codex / opencode) reads AGENTS.md (or skill for Claude Code) → routing table → identifies remediation path.
# 3. Agent asks for the 9 intake fields if not provided.
# 4. Scaffold the session:
cp -r team/remediation/SESSION_TEMPLATE/ team/remediation/$(date +%F)-<slug>/
# 5. Fill ISSUE_INTAKE.md (or 00-issue-intake.md), then 00-plan.md.
# 6. Dispatch baseline reviewer → implementer chunks → fresh reviewer per chunk.
# 7. PASS / FAIL / ESCALATE — 3-strike hard-stop per chunk.
# 8. Close with 99-report.md.
```

## Residuals (out of session scope)

- The `task-implement` skill exists in BOTH `.agents/skills/` and `.claude/skills/` with slight drift (designer flagged in Section 2 of `01-design.md`). Out of scope for this session — separate lock-step cleanup.
- Codex `config.toml` does NOT carry agent instructions (only MCP/env config). The decision table relies on Codex reading repo-root `AGENTS.md`. If a future Codex version stops doing that, we'd need a fallback.
- opencode is not installed/configured in this dev environment to test the fallthrough behavior. Theory says it reads root `AGENTS.md`; verify when opencode integration is exercised.
- 2 anti-pattern phrasings in AGENTS+CLAUDE differ from the design's reviewer-matrix grep terms (R-14). Tweak either the bullets or the matrix grep in a future session if strict-grep verification matters.

## Not production ready

Mintkey remains pre-alpha. This session does NOT change product behavior, only governance/workflow/templates.

## Next steps

1. **Verify routing works** by exercising it: any next time a user asks "fix this bug", the agent should route to remediation + ask for intake if missing.
2. **Lock-step monitor**: any future edit to the 9-row decision table MUST update all 4 files together (README + CONTRIBUTING + AGENTS + CLAUDE). A CI lint that diffs the 4 extracted tables would prevent drift.
3. **Skill discovery**: confirm Claude Code auto-discovers the skill at the next session start (the frontmatter `description` is the activation hook).
4. **Push readiness**: this session adds zero blockers to the OSS push. Combined with the prior `2026-05-16-public-github-release-readiness` session's PASS_ALL, the repo is ready when the owner decides to `git push -u origin main`.
