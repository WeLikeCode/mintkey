# Mintkey Public GitHub Release Readiness Remediation — Session Plan

**Session:** `2026-05-16-public-github-release-readiness`
**Driver:** `remediation-orchestrator` skill (`~/.claude/skills/remediation-orchestrator/SKILL.md`)
**Status:** Step 0 (baseline assessment) — implementation paused until baseline lands.

## Mission

Remediate every blocker found in the public-release review so Mintkey can be safely published on GitHub as a **pre-alpha technical preview**, not as production-ready software.

This session follows the OSS-readiness session (`team/remediation/2026-05-16-oss-readiness/`, closed `7f5fe29`). Most public-hygiene blockers landed there. This session does an **independent verification** + addresses any residual blockers before push.

## Session files

| File | Purpose |
|---|---|
| `00-plan.md` | This file — mission, DoD, Step 0 prompt. |
| `01-orchestrator-chunks.md` | Chunk catalog (built after BASELINE-REVIEWER returns). |
| `02-matrix.md` | Readiness matrix. |
| `03-escalations.md` | Owner decisions/blockers. |
| `04-progress.md` | Live orchestration state. |
| `99-report.md` | Final release-readiness report. |

## Pattern (orchestrator-pattern skill)

- ORCHESTRATOR owns state, does not directly implement code.
- BASELINE-REVIEWER runs read-only verification first.
- IMPLEMENTER agents make surgical, test-first changes.
- Fresh REVIEWER agents independently verify each chunk.
- PASS moves forward.
- FAIL dispatches a new IMPLEMENTER with prior findings.
- ESCALATE stops and asks the owner.
- Hard-stop after 3 failed reviews for the same chunk.

**Hard rule:** Do not add `Co-Authored-By` trailers to any commit (per `~/.claude/CLAUDE.md`).

## Definition of Done

Mintkey is ready for public GitHub release only when:

1. Root `LICENSE` exists and matches the stated license.
2. Public security contact is real and usable.
3. No release-blocking placeholders remain.
4. OpenAPI validates cleanly.
5. GitHub workflow YAML parses cleanly.
6. CI does not intentionally mask release-critical failures.
7. CONTRIBUTING no longer requires LLM co-author trailers.
8. Governance files exist: Code of Conduct, Support, Governance, issue templates, PR template.
9. Dependency/security automation exists or is explicitly documented as deferred.
10. `.dockerignore` coverage exists.
11. Container runtime posture is reviewed and either hardened or documented.
12. Versioning/release policy is coherent for a pre-alpha technical preview.
13. Final report lists commands, exit codes, residual risks, and launch recommendation.

## Step 0 — BASELINE-REVIEWER prompt (verbatim from user)

```xml
<role>You are BASELINE-REVIEWER for Mintkey public GitHub release readiness. Do not edit files.</role>

<objective>
Verify the current repo against public-release readiness. Do not trust prior summaries.
Produce a concrete red/yellow/green report with file/line evidence.
</objective>

<read_first>
AGENTS.md
CLAUDE.md
README.md
QUICKSTART.md
SECURITY.md
CONTRIBUTING.md
.github/workflows/ci.yml
.github/workflows/playwright.yml
Makefile
docs/architecture/contracts/rest/openapi.yaml
admin-api/Dockerfile
mcp-server/Dockerfile
admin-ui/Dockerfile
services/*/Dockerfile
docker-compose.yml
</read_first>

<commands>
git status --short
git log --oneline --decorate -12
find . -maxdepth 3 -type f \( -iname 'license*' -o -iname 'notice*' -o -iname 'code_of_conduct*' -o -iname 'support*' -o -iname 'governance*' -o -iname 'pull_request_template.md' -o -iname 'dependabot.y*ml' -o -iname 'renovate.json' \) | sort
find . -name '.dockerignore' -print
rg -n "<repo-url>|TBD-by-architect|maintainers@example.invalid|example.invalid/mintkey|Co-Authored-By|Co-authored-by|noreply@anthropic.com" README.md QUICKSTART.md SECURITY.md CONTRIBUTING.md docs marketing .github
rg -n "\|\| true|continue-on-error" .github Makefile
python3 -c "import yaml, pathlib; [yaml.safe_load(p.read_text()) for p in pathlib.Path('.github/workflows').glob('*.yml')]; print('workflow yaml: ok')"
python3 -c "import yaml,openapi_spec_validator as v; v.validate(yaml.safe_load(open('docs/architecture/contracts/rest/openapi.yaml'))); print('openapi: ok')"
python3 -c "import json; from jsonschema import Draft202012Validator as V; [V.check_schema(json.load(open(p))) for p in ['docs/architecture/contracts/events/audit-event.schema.json','docs/architecture/contracts/events/change-event.schema.json']]; print('json schemas: ok')"
python3 -c "import yaml; yaml.safe_load(open('docs/architecture/contracts/mcp/tools.yaml')); print('mcp yaml: ok')"
</commands>

<output>
Return:
- RED release blockers
- YELLOW public-polish risks
- GREEN items already good
- exact failing command outputs
- exact file:line evidence
- no fixes
</output>
```

## Chunks (to be built post-baseline)

`01-orchestrator-chunks.md` populated after BASELINE-REVIEWER's RED/YELLOW/GREEN report. Chunks will map 1:1 onto RED items (release blockers) with YELLOW items optional.
