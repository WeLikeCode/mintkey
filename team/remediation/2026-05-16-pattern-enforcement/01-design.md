# Pattern Enforcement — Design Plan (Step 0)

**Session:** `2026-05-16-pattern-enforcement`
**Designer:** ENFORCE-DESIGN (Opus subagent)
**Status:** Step 0 (design) — implementation paused until this lands and the user signs off on the forks in §4.
**Implementation hard rules (inherited by every chunk):** no `Co-Authored-By`, no `--no-verify`, no push, no edits to Accepted ADRs, no product code changes, honor dirty working-tree files, honor data preservation.

This is the surveyor's output for the mega-prompt in `00-plan.md`. It does not implement anything. It tells the implementer exactly what each of the 8 file targets needs, how the three target platforms (Claude Code / Codex / opencode) get wired, how the work splits into chunks, where the genuine forks are, and how the reviewer will black-box-verify the result.

Files referenced are absolute. Line numbers are as of the reads in this session.

---

## Section 1 — Survey of current state

### Target 1: `team/remediation/README.md`

**Current state (63 lines):** introduces the folder pattern, the role-numbered files (`00-plan.md`, `01-spec.md`, `01-orchestrator-chunks.md`, `02-matrix.md`, `03-escalations.md`, `04-progress.md`, `99-report.md`), explains the orchestrator pattern lives in `~/.claude/skills/remediation-orchestrator/SKILL.md` (project-agnostic), the active-sessions table, the archive table, and the "Starting a new session" shell snippet.

**What's already there:**
- Folder pattern (`YYYY-MM-DD-<kebab-slug>/` and `_archive/`).
- The 7 role-numbered files with one-line role descriptions.
- Pointer to the skill at `~/.claude/skills/remediation-orchestrator/SKILL.md`.
- Active-sessions table (2 entries, both stale — does not include the OSS sessions or this one).
- Archive table (2 entries).

**What's missing relative to the prompt's requirements:**

1. **No intake gate.** The prompt requires every remediation to start with an issue-intake answering 9 fields (Problem statement, User-visible symptom, Expected behavior, Evidence, Scope, Out of scope, Risk level, Verification target, Owner decisions needed). The README never mentions intake.
2. **No decision rules table.** The prompt requires a "Request Type → Required Path" table with 9 rows (fix-with-evidence → remediation session; fix-without-evidence → ask intake first; multi-file → orchestrator required; security/release/auth/audit/credential/tenant → orchestrator required; new feature → Kiro; wire-contract → ADR; DB schema → Liquibase; docs typo → direct PR; dep bump → direct PR if tests included).
3. **No PASS/FAIL/ESCALATE/3-strike summary.** These rules live only in the skill SKILL.md. The README should mirror them so a contributor reading the README knows what to expect without opening the skill.
4. **No "How to start" with intake-first ordering.** The current "Starting a new session" snippet is `mkdir + touch 00-plan.md`. The prompt's flow is intake → plan → chunks. The snippet should reference the `ISSUE_INTAKE_TEMPLATE.md` and the `SESSION_TEMPLATE/` directory once they exist.
5. **Active-sessions table is stale.** Missing `2026-05-16-oss-readiness/`, `2026-05-16-public-github-release-readiness/`, `2026-05-16-pattern-enforcement/`. Implementer should refresh this in the same chunk so the README is accurate.

**Concrete delta:** add ~80–120 lines covering: (a) issue-intake gate (link to `ISSUE_INTAKE_TEMPLATE.md`, list of the 9 fields, when missing fields gate); (b) decision rules table verbatim from the prompt (9 rows); (c) PASS/FAIL/ESCALATE/3-strike rules (one short paragraph each); (d) revised "Starting a new session" snippet pointing at `SESSION_TEMPLATE/`; (e) refresh active-sessions table.

---

### Target 2: `team/remediation/ISSUE_INTAKE_TEMPLATE.md` (NEW)

**Current state:** does not exist. (`ls team/remediation/` shows the README and the dated session dirs; no template file at the top level.)

**What's missing — everything.** A new file. Required content per the prompt:

A reusable markdown template with a `## Issue intake` heading and the 9 fields as labeled markdown placeholders. Fields marked "Required? Yes" must be non-empty before a session may start; "Required? If any" may be left blank. The 9 fields verbatim from the prompt:

| Field | Required? | Description |
|---|---:|---|
| Problem statement | Yes | What is broken or risky? |
| User-visible symptom | Yes | What does the user/operator see? |
| Expected behavior | Yes | What should happen instead? |
| Evidence | Yes | Logs, screenshots, failing tests, commands, or exact file references |
| Scope | Yes | Which areas may be changed? |
| Out of scope | Yes | Which areas must not be touched? |
| Risk level | Yes | Security, data loss, UX, CI, docs, release, etc. |
| Verification target | Yes | Which command/test proves the fix? |
| Owner decisions needed | If any | What cannot be guessed? |

Plus: a top-of-file usage note ("Copy to `team/remediation/<date>-<topic>/ISSUE_INTAKE.md` before opening the session.") and a one-line gating reminder ("Missing any Required field = ask for it OR open `03-escalations.md` if already inside a session.").

**Concrete delta:** new file, ~60–90 lines. Project-agnostic structure but free to reference Mintkey-specific risk-level categories (security, data loss, UX, CI, docs, release) since the file lives in-repo.

---

### Target 3: `team/remediation/SESSION_TEMPLATE/` (NEW directory)

**Current state:** does not exist.

**What's missing — everything.** A directory of starter files copy-pasteable into a new session. Per the prompt, this is the "scaffolding" companion to the intake template. Minimum file set, derived from the role-numbered files in the README plus the intake:

| File | Purpose | Source pattern |
|---|---|---|
| `00-plan.md` | Mission, hard rules, chunk plan placeholder, references to the intake | Modeled on `2026-05-16-oss-readiness/00-plan.md` and the existing `00-plan.md` in this session |
| `01-orchestrator-chunks.md` | Chunk catalog placeholder with empty table + owner/files/AC columns | Modeled on `2026-05-16-oss-readiness/01-orchestrator-chunks.md` |
| `02-matrix.md` | Tracking matrix placeholder with severity + status legend | Modeled on `2026-05-13-admin-ui-action-grid/02-matrix.md` (severity rendition) or `2026-05-16-oss-readiness/02-matrix.md` (findings rendition) |
| `03-escalations.md` | Empty escalations log with one example entry | Modeled on `2026-05-13-admin-ui-action-grid/03-escalations.md` |
| `04-progress.md` | Live state file with DoD checklist, chunk plan, round history, OQ list | Modeled on `~/.claude/skills/remediation-orchestrator/references/state-file.template.md` |
| `99-report.md` | Closing report skeleton (commands, exit codes, residuals) | Modeled on `2026-05-16-oss-readiness/99-report.md` |
| `ISSUE_INTAKE.md` | Symlink or pre-filled copy of `../ISSUE_INTAKE_TEMPLATE.md` | Per the fork in §4 |

The intake-vs-fork point: the prompt is silent on whether `SESSION_TEMPLATE/` should contain a copy of the intake or whether the user copies the intake separately. See §4 fork F2.

**Concrete delta:** new directory + 6 to 7 markdown files. Total ~250–400 lines. Each file is a skeleton with `{{placeholder}}` markers and a one-line "See `team/remediation/README.md` for the pattern" pointer. Project-agnostic in structure; Mintkey-flavored hard-rules cross-reference (since the file lives in-repo).

---

### Target 4: `.github/pull_request_template.md`

**Current state (60 lines):** has Summary, Linked issue / ADR (with sub-bullets Issue / ADR(s) / Spec AC(s)), Test plan (with a 2-column table placeholder), Pre-submission checklist (6 items), Verification output (with example).

**What's already there (mapped to the prompt's required sections):**

| Prompt required section | Already present in current template? |
|---|---|
| `## Change Type` (5 checkboxes) | ❌ no — no Change Type section at all |
| `## Required Provenance` (remediation block + Kiro block) | ⚠️ partial — "Linked issue / ADR" has Issue/ADRs/Spec ACs but no remediation-vs-Kiro split, no session-folder / matrix-row / reviewer-result fields |
| `## Issue Definition` (Problem / Expected / Evidence / Scope / Out of scope) | ❌ no — Summary is freeform; no structured intake fields |
| `## Verification` (paste output + 4 checkboxes) | ⚠️ partial — has Test plan table + Verification output blob + 6-item pre-submission checklist, but the prompt's 4 specific Verification checkboxes are missing (Tests run, Linters/validators run, Smoke/integration run, Security/plaintext checks run) |
| `## Agent/Automation Rules` (5 checkboxes) | ⚠️ partial — pre-submission checklist has `--no-verify`, `Co-Authored-By`, pre-alpha-not-weakened, ADR-touched-then-included, but missing exact items "No unverified tests pass claim", "No unrelated refactor", "No accepted ADR edited" as separate checkboxes |

**What's missing relative to the prompt's verbatim requirements:**

1. `## Change Type` section with the 5 checkboxes (Remediation / Kiro / Docs / Deps / Other).
2. `## Required Provenance` section split into the remediation block (Session folder / Issue intake file / Matrix row(s) / Reviewer result) and the Kiro block (Requirement / Design section / Task / ADR-or-proposal).
3. `## Issue Definition` section with Problem / Expected behavior / Evidence / Scope / Out of scope sub-fields.
4. `## Verification` section with the 4 specific checkboxes verbatim from the prompt.
5. `## Agent/Automation Rules` section with the 5 specific checkboxes verbatim from the prompt.

**Concrete delta:** rewrite the template (~120–150 lines after rewrite vs 60 today). Preserve the spirit of the existing Pre-submission checklist content by mapping its items into the new `Agent/Automation Rules` section where they overlap; drop the Test plan 2-column table (replace with the Verification section's prose + checkboxes). Keep the Verification-output code-fence block at the bottom so authors still paste exit codes.

---

### Target 5: `CONTRIBUTING.md`

**Current state (224 lines):** has Zero-tolerance-for-vibe-coding, Kiro SDD pipeline (mermaid + non-negotiable rules), AI-slop examples, Worked example, How-to-propose / How-to-add / How-to-file-a-PR / Commit-and-PR style / Coding-agent-usage / Reviewing / Code-of-conduct. Already references the skill via mentions of the orchestrator pattern… actually let me re-check.

**Grep result:** `CONTRIBUTING.md` does NOT currently mention `team/remediation/`, `remediation-orchestrator`, `orchestrator pattern`, or `ISSUE_INTAKE_TEMPLATE`. CONTRIBUTING is purely Kiro-flavored right now. It is silent on remediation work.

**What's missing relative to the prompt's requirements:**

A new section titled "Remediation vs Spec-Driven Work" (or "Bug fixes vs new features", or similar) that:

1. Distinguishes the two paths. "If you are adding or changing behavior → Kiro spec-driven (the existing pipeline). If you are fixing broken behavior with clear evidence → remediation session at `team/remediation/YYYY-MM-DD-<topic>/`."
2. Reproduces the decision-rules table (same 9 rows as the README, since the table is the authoritative routing).
3. References `team/remediation/README.md` and `team/remediation/ISSUE_INTAKE_TEMPLATE.md` for the intake.
4. References `~/.claude/skills/remediation-orchestrator/SKILL.md` for the orchestrator pattern (the project-agnostic skill).
5. States the cross-platform wiring (Codex / opencode / Claude Code agents all follow this — see Section 2 of this design).

Should sit immediately after the "Kiro Spec-Driven Development pipeline" section (current line 25–46) and before "Non-negotiable rules" (line 48), so the reader sees both paths before the rules apply to either.

**Concrete delta:** add a new ~60–90 line section. Do NOT edit the existing Zero-tolerance / SDD pipeline / Non-negotiable rules / Worked-example sections — they remain authoritative for spec-driven work. The remediation path is additive, not replacing.

---

### Target 6: `AGENTS.md`

**Current state (331 lines):** has What-this-project-is, Operating principles (P0–P3), Karpathy's four principles, Reconciling principles, Mintkey-specific guardrails (Schema / IDs / Audit / Tokens / Architecture / Tech stack), Verification commands, Repo map, "How to add an X" pattern library, Anti-patterns, When-in-doubt, Sources. Locked-step sibling of `CLAUDE.md`.

**Grep result:** `AGENTS.md` does NOT currently mention `team/remediation/`, `remediation-orchestrator`, `ISSUE_INTAKE`, or the orchestrator pattern. The "How to add an X" table covers REST endpoint, MCP tool, audit-event-type, auth-scheme, schema-column, ADR, flow — nothing about bug fixes / remediations.

**What's missing relative to the prompt's requirements (decision-table guardrails):**

1. **A new section** named e.g. "Decision: remediation vs spec-driven" — or extending the "How to add an X" table with a "Fixing" sibling block. The section MUST reproduce the 9-row decision-rules table verbatim from the prompt. It MUST live above the existing Anti-patterns section so readers process the routing before the rules apply.
2. **An intake-gate sentence** in Principle 2 (or as a sibling principle): "If the user has not clearly defined the issue, ask for the 9 intake fields before remediating. Do NOT improvise a fix based on a vague request."
3. **A pointer** to `team/remediation/README.md`, `team/remediation/ISSUE_INTAKE_TEMPLATE.md`, and `~/.claude/skills/remediation-orchestrator/SKILL.md`. Codex reads `AGENTS.md` for project instructions; the skill is in the user's `~/.claude/` and not auto-loaded by Codex, so the pointer must include the inline content (or a sufficient summary) so Codex sessions inherit the rule without needing the skill file.
4. **Anti-pattern row:** add to the existing Anti-patterns list "❌ Start a multi-file remediation without an `ISSUE_INTAKE.md` and a `team/remediation/<date>/` session folder." and "❌ Edit a security / auth / audit / credential / tenant-isolation issue with a direct PR — open an orchestrator session."

**Concrete delta:** add ~80–110 lines. Must lock-step with `CLAUDE.md` (Target 7).

---

### Target 7: `CLAUDE.md`

**Current state (323 lines):** mirror of `AGENTS.md` minus a few lines (e.g., the agents.md standard reference paragraph is in `AGENTS.md` line 5 but absent from `CLAUDE.md`; some "agent runtime" phrasings differ between the two files at line 31 vs 29). Otherwise content is in lock-step.

**Grep result:** same as `AGENTS.md`. No mention of remediation, orchestrator, intake.

**What's missing — identical to Target 6.** The decision-rules table, the intake-gate sentence, the pointers, the anti-pattern rows.

**Concrete delta:** add the same ~80–110 lines as `AGENTS.md`, with identical content. The single allowed difference vs `AGENTS.md`: a Claude-Code-flavored opening sentence ("Claude Code activates the `remediation-orchestrator` skill at `~/.claude/skills/remediation-orchestrator/SKILL.md` for the orchestration mechanics; this section is the project-side routing.") whereas `AGENTS.md` says ("For agents without skills (Codex, opencode, etc.), this section is the entire routing — there is no separate skill file to read.").

**Lock-step verification:** after both edits land, `diff` the relevant sections of the two files. They MUST be identical except for the one Claude-vs-non-Claude opening sentence. Reviewer matrix has a row for this.

---

### Target 8: `~/.claude/skills/remediation-orchestrator/SKILL.md`

**Current state (73 lines + 7 references files in `references/`):** has frontmatter (name + description), main body (intro + when-to-invoke + when-NOT + Workflow Step 0–3 + Hard rules pointer + Templates pointer + Reviewer-anti-patterns pointer + Code-navigation discipline pointer + Parallelism + Escalation + Resumability). The references/ directory has:

- `hard-rules.md` (20 lines) — no-Co-Authored-By, no --no-verify, no docker compose down -v, etc.
- `implementer-brief.template.md` (100 lines) — XML-tagged subagent prompt.
- `reviewer-brief.template.md` (79 lines) — XML-tagged reviewer subagent prompt with universal ACs A–E.
- `researcher-brief.template.md` (48 lines) — read-only researcher prompt.
- `reviewer-antipatterns.md` (81 lines) — grep checks (assert True, pytest.skip, mocking SUT, --no-verify, Co-Authored-By, etc.).
- `serena-discipline.md` (45 lines) — Serena MCP navigation guidance.
- `state-file.template.md` (42 lines) — `04-progress.md` template.

**What's missing relative to the prompt's requirements:**

1. **Frontmatter `description` does not mention issue intake.** Currently reads: "Run a multi-step code remediation using the orchestrator + IMPLEMENTER + REVIEWER subagent pattern. The orchestrator owns state and dispatches; an IMPLEMENTER subagent does each chunk test-first and surgically; a fresh REVIEWER subagent independently verifies. FAIL spawns a new implementer; 3-strike hard-stop. Activate when the user says..."
   - Per the prompt's required behavior, the skill must auto-activate even when the user describes a fix without saying "orchestrator" — and must request issue intake first if the 9 fields are not already provided.
   - Delta: extend the description to include a phrase like "Request issue intake first if the user has not clearly defined the issue (problem, evidence, scope, verification target)."
2. **No "Issue intake gate" section.** Workflow currently starts at Step 0 — Baseline. The prompt mandates an intake step *before* baseline. New step required (call it Step −1 or Step 0a):
   - "Confirm the 9 intake fields are answered. If any Required field is missing, ASK the user. Do NOT proceed to baseline."
3. **No `references/issue-intake.md`.** Companion template + checklist for the orchestrator to use when checking intake completeness. Should mirror `team/remediation/ISSUE_INTAKE_TEMPLATE.md` (project-agnostic — no `t_default` / no Mintkey IDs / no ADR references in the skill's copy).
4. **The skill must remain project-agnostic** (per the user's hard rule "the skill is project-agnostic — the extension MUST stay project-agnostic too"). Concretely: no `Mintkey`, no `t_default`, no `mk_agent_…`, no `RLS`, no `Liquibase`, no `ADR-NNNN` references in the skill body or in `references/issue-intake.md`. The intake fields themselves (Problem / Symptom / Evidence / Scope / Out-of-scope / Risk / Verification target / Owner decisions) are general-purpose.

**Concrete delta:**
- Edit frontmatter `description` (one-line addition).
- Add a "Step 0 — Issue intake gate" subsection above (or as a renamed first part of) the current "Step 0 — Baseline" section.
- New file `references/issue-intake.md` (~50–70 lines).

---

## Section 2 — Cross-platform wiring

Three target platforms. Each has a different mechanism for loading project instructions. The mega-prompt requires the same intake + decision-table rules to apply uniformly across all three (and across the GitHub PR review surface).

### Claude Code

**Mechanism:** `~/.claude/skills/<name>/SKILL.md` (skills are user-level by default; `.claude/skills/` in a repo can also be added but is not the canonical install path for `remediation-orchestrator`). Claude Code loads skill descriptions at session start and activates the skill when the description matches the user's intent.

**Existing install:** `~/.claude/skills/remediation-orchestrator/SKILL.md` already exists with workflow, hard-rules, templates, antipatterns, serena-discipline, state-file template (Target 8 survey above).

**Extension path:** update `SKILL.md` per Target 8. The frontmatter `description` is the auto-activation hook — adding "request issue intake first if not provided" makes the skill self-arm even when the user types "fix this credential leak" rather than "orchestrate this remediation".

**Also loaded by Claude Code:** the in-repo `CLAUDE.md` (Target 7). Claude Code reads it for project-specific guardrails. Adding the decision-rules table here means a Claude Code user gets both the project-routing (from CLAUDE.md) and the orchestration mechanics (from the skill). The two reinforce each other.

### Codex (Codex CLI)

**Mechanism:** Codex reads `AGENTS.md` (repo-level) for project instructions per the [agents.md](https://agents.md) open standard. `.codex/config.toml` exists in the repo (verified — has MCP server config for `context7` and `serena`, plus `shell_environment_policy`) but **does NOT carry agent instructions**. config.toml is for MCP/env/CLI configuration; project guardrails go in `AGENTS.md`.

**Decision-table + intake-gate guardrails belong in `AGENTS.md`.** Codex does NOT auto-load skills from `~/.claude/skills/`. So the AGENTS.md decision-rules table must be self-sufficient: a Codex session must be able to follow the orchestrator pattern from AGENTS.md alone, without referencing the skill (the skill is a Claude-Code mechanism Codex cannot read).

**Concretely:**
- AGENTS.md gets the 9-row decision-table.
- AGENTS.md gets the intake-gate sentence.
- AGENTS.md gets a pointer to `team/remediation/README.md` for the orchestrator pattern essentials (PASS/FAIL/ESCALATE/3-strike), so a Codex session knows the loop without reading the user-level skill.
- The "How to add an X" table in AGENTS.md gets a new row (or a sibling "How to fix an X" table) covering the routing.

### opencode

**Mechanism:** opencode reads `AGENTS.md` from the repository root, per the agents.md open standard. opencode-specific config (if any) lives in `.opencode/`.

**Repo check:** `.opencode/` does NOT exist in `/Users/alexandruiacobescu/gooseProjects/mintkey/` (verified). The repo has `.codex/`, `.agents/`, `.claude/`, `.github/`, `.kiro/` — but no `.opencode/`. The AGENTS.md line 270 mentions `.opencode/` as "parallel structure if/when added", confirming the design intent: it's planned but absent.

**Wiring options for opencode:**

| Option | Mechanism | Cost | Benefit |
|---|---|---|---|
| **A — Rely on AGENTS.md fallthrough** | Do nothing additional; opencode loads root-level `AGENTS.md` automatically. | Zero — same edit as Codex. | Single source of truth; lock-step easy. |
| **B — Create `.opencode/AGENTS.md` symlink** | `ln -s ../AGENTS.md .opencode/AGENTS.md`. opencode loads its config dir first; symlink ensures consistency. | One file (symlink). Symlinks behave fine in git. | Future-proof against opencode changing its precedence rules. |
| **C — Duplicate the file** | Copy `AGENTS.md` into `.opencode/AGENTS.md`. | Two files to keep in lock-step manually. | None vs symlink. |

This is fork F1 below (§4). Recommendation: **A** (rely on the root `AGENTS.md`), with B as a fallback if opencode ever changes its loading precedence. Avoid C — duplication invites drift, and we already have the AGENTS.md ↔ CLAUDE.md lock-step problem; adding a third file is gratuitous.

A separate observation: the repo has `.agents/skills/task-implement/SKILL.md` and `.claude/skills/task-implement/SKILL.md` — two copies of an in-repo skill, with the .agents/ copy slightly newer (Mar 16 vs Mar 10) but content-similar. This is duplication-pattern C in action for the `task-implement` skill. The `remediation-orchestrator` skill currently lives ONLY in `~/.claude/skills/` (user-level, not in-repo), and the prompt does not ask for it to be cloned into `.agents/skills/` or `.opencode/skills/`. So we do NOT propose extending opencode/codex with their own skill copies — they get the rule via `AGENTS.md`.

### GitHub PRs

**Mechanism:** `.github/pull_request_template.md` populates the PR body. Reviewers (human or LLM) see the structured fields and can refuse to approve PRs that leave Required Provenance blank.

**Extension path:** rewrite the template per Target 4. Adds Change Type / Required Provenance / Issue Definition / Verification / Agent Rules sections.

### Lock-step matrix

After all edits land, the following content equivalence must hold:

| Content | Lives in | Must match |
|---|---|---|
| 9-row decision table | `team/remediation/README.md`, `CONTRIBUTING.md` (Remediation-vs-Spec section), `AGENTS.md` (Decision-routing section), `CLAUDE.md` (Decision-routing section) | All 4 copies identical verbatim |
| 9-field intake schema | `team/remediation/ISSUE_INTAKE_TEMPLATE.md`, `~/.claude/skills/remediation-orchestrator/references/issue-intake.md` | Schema identical; example values may differ (template is Mintkey-flavored, skill ref is project-agnostic) |
| PASS / FAIL / ESCALATE / 3-strike | `team/remediation/README.md`, `~/.claude/skills/remediation-orchestrator/SKILL.md` | Same rules; SKILL.md has more detail (it owns the mechanics) |
| Intake-gate sentence | `AGENTS.md` Principle 2 (or sibling), `CLAUDE.md` Principle 2 (or sibling), `~/.claude/skills/remediation-orchestrator/SKILL.md` description + Step 0a | Same idea; SKILL.md owns the operational gate |

---

## Section 3 — Chunk decomposition

The work decomposes into **4 chunks** (`PE-1` through `PE-4`). The mega-prompt suggests this split; I confirm it is correct after the survey. Each chunk has disjoint file ownership (no two chunks touch the same file), so they can be dispatched in parallel if the orchestrator wishes — though I recommend serial dispatch since PE-2 and PE-3 both quote the decision-table verbatim, and dispatching PE-2 before PE-3 lets the implementer of PE-3 copy the exact text PE-2 settled on.

### PE-1 — Templates + Skill extension

**Owner files:**
- NEW: `team/remediation/ISSUE_INTAKE_TEMPLATE.md`
- NEW: `team/remediation/SESSION_TEMPLATE/` (directory with 6–7 files)
- EDIT: `~/.claude/skills/remediation-orchestrator/SKILL.md` (frontmatter + Step 0a)
- NEW: `~/.claude/skills/remediation-orchestrator/references/issue-intake.md`

**Acceptance criteria:**
1. `team/remediation/ISSUE_INTAKE_TEMPLATE.md` exists, contains all 9 fields with the prompt's verbatim labels and Required? markers, has a top-of-file usage note, and a missing-fields gating reminder.
2. `team/remediation/SESSION_TEMPLATE/` exists with at least 6 files: `00-plan.md`, `01-orchestrator-chunks.md`, `02-matrix.md`, `03-escalations.md`, `04-progress.md`, `99-report.md`. Each is a non-empty skeleton with `{{placeholder}}` markers.
3. `~/.claude/skills/remediation-orchestrator/SKILL.md` frontmatter `description` mentions issue intake (one of: "issue intake", "request the 9-field intake", "request intake first").
4. `~/.claude/skills/remediation-orchestrator/SKILL.md` has a Step 0a (or equivalent named subsection) describing the intake gate.
5. `~/.claude/skills/remediation-orchestrator/references/issue-intake.md` exists, contains the 9-field schema, and is project-agnostic (no Mintkey identifiers).

**Verification commands (the reviewer will run these):**

```sh
# AC1 + AC5: files exist and have minimum content
test -f team/remediation/ISSUE_INTAKE_TEMPLATE.md && wc -l team/remediation/ISSUE_INTAKE_TEMPLATE.md
test -f ~/.claude/skills/remediation-orchestrator/references/issue-intake.md && \
  wc -l ~/.claude/skills/remediation-orchestrator/references/issue-intake.md

# AC1: 9 required field labels present
for f in "Problem statement" "User-visible symptom" "Expected behavior" "Evidence" \
         "Scope" "Out of scope" "Risk level" "Verification target" "Owner decisions"; do
  grep -q "$f" team/remediation/ISSUE_INTAKE_TEMPLATE.md || echo "MISSING: $f"
done

# AC2: 6 session template files exist
for f in 00-plan.md 01-orchestrator-chunks.md 02-matrix.md 03-escalations.md 04-progress.md 99-report.md; do
  test -f "team/remediation/SESSION_TEMPLATE/$f" || echo "MISSING: $f"
done

# AC3: frontmatter mentions intake
head -3 ~/.claude/skills/remediation-orchestrator/SKILL.md | grep -iE "issue.intake|9.field.intake|intake.first"

# AC4: Step 0a (or named intake gate) exists in SKILL.md body
grep -iE "intake.gate|Step 0a|Step 0\.5|issue intake" ~/.claude/skills/remediation-orchestrator/SKILL.md

# AC5: project-agnostic — must NOT contain Mintkey identifiers
grep -iE "mintkey|adr-[0-9]|liquibase|t_default|mk_agent_|kong|rls" \
  ~/.claude/skills/remediation-orchestrator/references/issue-intake.md
# (must return empty)
```

**Estimated size:** medium. ~7–9 new files + 1 edit. ~400–600 net new lines across the templates and the skill extension.

---

### PE-2 — Repo-level remediation governance

**Owner files:**
- EDIT: `team/remediation/README.md`
- EDIT: `CONTRIBUTING.md`

**Acceptance criteria:**
1. `team/remediation/README.md` has an "Issue intake" section listing the 9 fields and referencing `ISSUE_INTAKE_TEMPLATE.md`.
2. `team/remediation/README.md` has a "Decision rules" section with the 9-row decision table verbatim from the prompt.
3. `team/remediation/README.md` has a "PASS / FAIL / ESCALATE / 3-strike" subsection (one short paragraph per outcome).
4. `team/remediation/README.md`'s active-sessions table includes `2026-05-16-oss-readiness/`, `2026-05-16-public-github-release-readiness/`, and `2026-05-16-pattern-enforcement/`.
5. `CONTRIBUTING.md` has a new section titled "Remediation vs Spec-Driven Work" (or equivalent, ≤ 5-word title containing both "Remediation" and "Spec") inserted between the current "Kiro Spec-Driven Development pipeline" section and "Non-negotiable rules" section.
6. The new CONTRIBUTING.md section quotes the same 9-row decision table verbatim and references `team/remediation/README.md` and `~/.claude/skills/remediation-orchestrator/SKILL.md`.

**Verification commands:**

```sh
# AC1, AC2, AC3
grep -c "Problem statement\|User-visible symptom\|Expected behavior" team/remediation/README.md
# (must return ≥ 3)
grep -E "Decision rules|Decision Rules" team/remediation/README.md
grep -E "PASS.*FAIL.*ESCALATE|3-strike|hard-stop" team/remediation/README.md

# AC4
for s in 2026-05-16-oss-readiness 2026-05-16-public-github-release-readiness 2026-05-16-pattern-enforcement; do
  grep -q "$s" team/remediation/README.md || echo "MISSING session: $s"
done

# AC5, AC6
grep -E "Remediation vs Spec|Remediation vs spec|Spec-Driven.*Remediation" CONTRIBUTING.md
grep -c "Problem statement\|User-visible symptom\|Expected behavior" CONTRIBUTING.md
# (must return ≥ 3 — table is now quoted in two places)

# Cross-doc: decision-table rows match prompt verbatim
for row in 'Fix this bug.*clear evidence' 'Multi-file remediation' 'Security, release, auth, audit, credential, tenant' \
           'New feature' 'Wire contract change' 'Database schema change' 'Documentation typo' 'Dependency bump'; do
  grep -qE "$row" team/remediation/README.md || echo "README missing: $row"
  grep -qE "$row" CONTRIBUTING.md || echo "CONTRIBUTING missing: $row"
done
```

**Estimated size:** small. 2 files edited; ~150–200 net new lines combined.

---

### PE-3 — Agent guardrails (AGENTS.md ↔ CLAUDE.md lock-step)

**Owner files:**
- EDIT: `AGENTS.md`
- EDIT: `CLAUDE.md`

**Acceptance criteria:**
1. `AGENTS.md` has a new section (heading exactly "## Decision: remediation vs spec-driven work" or "## Routing: remediation vs spec-driven work" — implementer picks; reviewer accepts either) located above the existing "Anti-patterns (do NOT)" section.
2. That section in `AGENTS.md` contains the 9-row decision-rules table verbatim.
3. `AGENTS.md` Principle 2 (or a new sibling Principle 2a) has an intake-gate sentence: "If the user has not clearly defined the issue, ask for the intake fields before remediating."
4. `AGENTS.md` "Anti-patterns" list has 2 new rows: "❌ Start a multi-file remediation without an issue intake and a `team/remediation/<date>/` session folder." and "❌ Edit a security / auth / audit / credential / tenant-isolation issue with a direct PR — open an orchestrator session."
5. `CLAUDE.md` mirrors `AGENTS.md` in lock-step: identical decision-table; identical intake-gate sentence; identical anti-patterns; single allowed difference is the Claude-vs-Codex opening sentence introducing the section.
6. `diff` of the two files' new sections shows ≤ 2 differing lines.

**Verification commands:**

```sh
# AC1, AC2 — AGENTS.md
grep -E "Decision.*remediation|Routing.*remediation" AGENTS.md
grep -E "Multi-file remediation|Wire contract change|Database schema change" AGENTS.md
# (the 9 rows must all be present)

# AC3 — intake-gate sentence
grep -iE "clearly defined.*issue|9.field intake|request.*intake" AGENTS.md

# AC4 — new anti-patterns
grep -E "remediation without an issue intake|orchestrator session" AGENTS.md

# AC5 — CLAUDE.md mirrors
grep -E "Decision.*remediation|Routing.*remediation" CLAUDE.md
grep -E "Multi-file remediation|Wire contract change|Database schema change" CLAUDE.md
grep -iE "clearly defined.*issue|9.field intake|request.*intake" CLAUDE.md
grep -E "remediation without an issue intake|orchestrator session" CLAUDE.md

# AC6 — lock-step diff (extract the new section from each; diff)
# Implementer documents this in the commit message; reviewer re-runs.
awk '/^## Decision: remediation|^## Routing: remediation/,/^## /' AGENTS.md > /tmp/agents-section.md
awk '/^## Decision: remediation|^## Routing: remediation/,/^## /' CLAUDE.md > /tmp/claude-section.md
diff /tmp/agents-section.md /tmp/claude-section.md
# (must show ≤ 2 differing lines — the opening sentence)
```

**Estimated size:** small. 2 files edited; ~200 net new lines combined. The work is mostly copy-paste between the two files plus the one allowed difference.

---

### PE-4 — PR template

**Owner files:**
- REWRITE: `.github/pull_request_template.md`

**Acceptance criteria:**
1. The template has 5 top-level sections in this order: `## Change Type`, `## Required Provenance`, `## Issue Definition`, `## Verification`, `## Agent/Automation Rules`. Plus a `## Summary` section at the top is optional but encouraged (preserve from existing).
2. `## Change Type` contains exactly 5 checkboxes with the prompt's verbatim labels: Remediation session / Kiro/spec-driven feature / Documentation-only / Dependency-only / Other.
3. `## Required Provenance` contains TWO sub-blocks: "For remediation:" with Session-folder / Issue-intake-file / Matrix-row(s) / Reviewer-result; "For Kiro/spec-driven work:" with Requirement / Design-section / Task / ADR-or-proposal.
4. `## Issue Definition` contains the 5 sub-fields: Problem / Expected behavior / Evidence / Scope / Out of scope.
5. `## Verification` contains a "Paste command output and exit codes" instruction and 4 checkboxes: Tests run / Linters/validators run / Smoke/integration run if relevant / Security/plaintext checks run if relevant.
6. `## Agent/Automation Rules` contains 5 checkboxes verbatim: No --no-verify / No unverified "tests pass" claim / No unrelated refactor / No accepted ADR edited / No Co-Authored-By trailer required or added.

**Verification commands:**

```sh
# AC1 — section order
grep -nE "^## " .github/pull_request_template.md
# Output must show ## Change Type, ## Required Provenance, ## Issue Definition, ## Verification, ## Agent/Automation Rules in that order.

# AC2 — Change Type checkboxes
grep -cE "\[ \] (Remediation session|Kiro/spec-driven feature|Documentation-only|Dependency-only|Other)" \
  .github/pull_request_template.md
# (must be ≥ 5)

# AC3 — Required Provenance fields
for f in "Session folder" "Issue intake file" "Matrix row" "Reviewer result" \
         "Requirement" "Design section" "Task"; do
  grep -q "$f" .github/pull_request_template.md || echo "MISSING: $f"
done

# AC4 — Issue Definition fields
for f in "Problem" "Expected behavior" "Evidence" "Scope" "Out of scope"; do
  grep -q "$f" .github/pull_request_template.md || echo "MISSING: $f"
done

# AC5 — Verification checkboxes
for f in "Tests run" "Linters/validators run" "Smoke/integration run" "Security/plaintext"; do
  grep -q "$f" .github/pull_request_template.md || echo "MISSING: $f"
done

# AC6 — Agent Rules checkboxes
for f in "No \`--no-verify\`" "No unverified" "No unrelated refactor" "No accepted ADR edited" "No \`Co-Authored-By\`"; do
  grep -q "$f" .github/pull_request_template.md || echo "MISSING: $f"
done
```

**Estimated size:** small. 1 file rewritten; ~150 lines after rewrite (vs 60 today).

---

### Why 4 chunks, not 2

I considered merging PE-2 + PE-3 (they both quote the decision-table) and merging PE-1 + PE-4 (template work). I keep them split for three reasons:

1. **Disjoint file ownership** is preserved across all 4 chunks. Reviewer can re-run each chunk's verification independently. Merging risks scope creep where one implementer half-finishes the next chunk's work.
2. **Lock-step risk in PE-3** (AGENTS.md ↔ CLAUDE.md) is a known failure mode for this repo — the two files have drifted before. Isolating PE-3 lets the reviewer focus on the diff between the two new sections, which is the single highest-risk verification item in this design.
3. **PE-1 is the slowest** (skill extension + templates) and PE-4 is the fastest (rewrite one short file). Splitting them lets the orchestrator dispatch PE-4 first (or in parallel) and have a quick win on the board while PE-1 is still in flight.

If the orchestrator decides to merge for speed, the natural merge is PE-2 + PE-3 (governance + guardrails — both edit the decision-table). PE-1 should stay independent (it touches the user-level skill, which is outside the repo). PE-4 should stay independent (it touches `.github/`, which has its own review surface).

---

## Section 4 — Forks for user sign-off

Four architectural decisions that genuinely fork. Each has a recommendation, but the user should confirm before PE-1 (templates) is dispatched.

### Fork F1 — opencode wiring

**Question:** how does opencode pick up the decision-table + intake-gate rules?

| Option | Description | Tradeoff |
|---|---|---|
| **A — Rely on AGENTS.md fallthrough** ⭐ | opencode reads root `AGENTS.md` per the agents.md convention. No new file. | Zero cost. Single source of truth. Risk: if opencode ever changes precedence to prefer `.opencode/AGENTS.md`, this breaks silently. |
| **B — Create `.opencode/AGENTS.md` symlink to `../AGENTS.md`** | One symlink. opencode sees its dir-local copy. | Future-proof. Symlinks behave fine in git (verified — git tracks the link, opencode tools follow it). Slight oddity if anyone uses Windows / msys2 where symlinks behave differently. |
| **C — Duplicate the file** | `cp AGENTS.md .opencode/AGENTS.md`. | Worst option. Adds a third lock-step target (currently we already struggle with AGENTS.md ↔ CLAUDE.md). |

**Recommendation: A.** Mintkey is Mac+Linux today (verified — no Windows-targeted CI, no `.gitattributes` for Windows). The agents.md standard explicitly endorses root-level `AGENTS.md` for opencode. No measurable benefit to B until opencode breaks the convention.

If user wants B as a hedge: implementer creates the symlink in PE-3 as a 1-line addition. No diff-tracking risk.

### Fork F2 — `SESSION_TEMPLATE/ISSUE_INTAKE.md` — symlink, copy-paste, or absent?

**Question:** does `SESSION_TEMPLATE/` include an `ISSUE_INTAKE.md` (so a new session has the intake form bundled), or does the user copy the intake separately from `team/remediation/ISSUE_INTAKE_TEMPLATE.md`?

| Option | Description | Tradeoff |
|---|---|---|
| **A — Symlink `SESSION_TEMPLATE/ISSUE_INTAKE.md → ../ISSUE_INTAKE_TEMPLATE.md`** ⭐ | New session inherits the template by `cp -r SESSION_TEMPLATE/ <session-dir>/`. Symlink resolves to live template. | Single source. New session always uses the latest template. Symlink-aware ops only. |
| **B — Duplicate copy** | `SESSION_TEMPLATE/ISSUE_INTAKE.md` is a static copy of `ISSUE_INTAKE_TEMPLATE.md`. | Drift risk: template gets updated, session-template's copy stays stale. |
| **C — Absent; user must copy separately** | `SESSION_TEMPLATE/` does not include the intake; the README's "Starting a new session" snippet documents the two-step copy. | Cleanest separation. Slightly more friction; risk of users forgetting the intake. |

**Recommendation: A (symlink).** New sessions get the latest intake automatically; matches the pattern Mintkey already uses for `docs/architecture/adrs/` → `01-architecture/adr/` symlinks (verified — that pattern exists in the repo).

Counterargument for C: the intake is the gate; making it absent in the template forces the operator to think before they can run a session. Forces the gate to be intentional. Slight friction win.

Counterargument for B: it just works on Windows. Not currently a concern.

**Default to A unless user wants to enforce intentional intake → C.**

### Fork F3 — `SESSION_TEMPLATE/` as static dir vs scaffolding script

**Question:** is the template a copy-pasteable directory (the user `cp -r`s it into a new session), or a Bash/Make script that scaffolds a dated session (e.g., `make new-session TOPIC=foo`)?

| Option | Description | Tradeoff |
|---|---|---|
| **A — Static directory** ⭐ | `team/remediation/SESSION_TEMPLATE/` exists; user runs `cp -r team/remediation/SESSION_TEMPLATE team/remediation/$(date +%F)-<topic>`. | Minimum work. README documents the one-line copy. Discoverable. |
| **B — Static directory + Makefile target** | Adds `make new-session TOPIC=<slug>` to the existing Makefile (which already exists in repo). The target does the `cp -r` plus stamps the date. | Slightly more pleasant DX. Extra surface in Makefile to maintain. |
| **C — Just a script under `scripts/`** | `scripts/new-remediation-session.sh` does the same. | Adds a new file. Less discoverable than make target. |

**Recommendation: A.** This is a governance-pattern session, not a velocity-pattern session. A `cp -r` is fine. If we add a make-target later, it's a one-liner. Premature DX optimization right now.

If user wants ergonomics → B (already have a Makefile; cheap to extend).

### Fork F4 — "Direct small PR allowed" rows in the decision-table — any direct PR or require a tiny issue stub?

**Question:** the prompt's decision-table has two "Direct PR allowed" rows: "Documentation typo" and "Dependency bump" (the latter qualified with "if tests/verification included"). Should these still require a tiny issue stub (one paragraph in the PR body) or genuinely zero overhead?

| Option | Description | Tradeoff |
|---|---|---|
| **A — Zero overhead** | A docs typo PR can be 1 line of body. No intake. No session. Just merge. | Lowest friction. Risk: drift — someone files an "innocent" 12-file "doc" PR that turns out to be code. |
| **B — Tiny stub required** ⭐ | The PR template's `## Issue Definition` is always required, but for direct-PR types, "Problem: doc typo on README:42, fixing" is sufficient. | Forces the author to articulate even tiny changes. Cost: 30 seconds. Benefit: makes the LLM-bot diff-bomb pattern detectable. |
| **C — Stub only for deps, not for docs** | Docs typo = zero overhead. Dep bump = stub required (already in the prompt's qualifier "if tests/verification included"). | Compromise. Hard to maintain consistently. |

**Recommendation: B.** Mintkey is a security project. The prompt itself emphasizes "Validate via tools — never claim done without running it" (which inherits from `feedback_validate_via_tools.md` in the user's memory). Zero-overhead direct PRs are a known LLM-slop vector. The cost of one paragraph is trivial; the cost of an undetected `.md` change that turns out to weaken a security claim is large.

The PR template already covers this: the `## Issue Definition` section appears unconditionally. We just need the decision-table copy in the README/CONTRIBUTING/AGENTS.md/CLAUDE.md to clarify that "direct PR allowed" means "no session folder needed" — not "no intake fields needed."

---

## Section 5 — Reviewer matrix

The reviewer (fresh subagent, dispatched after all 4 implementer chunks PASS) runs each row independently. Empty output is good for grep-checks; non-empty output is a fail unless explicitly explained.

| # | Check | Black-box verification | Expected | Failure mode |
|---|---|---|---|---|
| R-1 | `ISSUE_INTAKE_TEMPLATE.md` exists | `test -f team/remediation/ISSUE_INTAKE_TEMPLATE.md && wc -l team/remediation/ISSUE_INTAKE_TEMPLATE.md` | exit 0, ≥ 50 lines | file missing or empty |
| R-2 | All 9 intake fields present | `for f in "Problem statement" "User-visible symptom" "Expected behavior" "Evidence" "Scope" "Out of scope" "Risk level" "Verification target" "Owner decisions"; do grep -q "$f" team/remediation/ISSUE_INTAKE_TEMPLATE.md \|\| echo "MISSING: $f"; done` | no MISSING output | any field missing = FAIL |
| R-3 | `SESSION_TEMPLATE/` has all 6 expected files | `for f in 00-plan.md 01-orchestrator-chunks.md 02-matrix.md 03-escalations.md 04-progress.md 99-report.md; do test -f "team/remediation/SESSION_TEMPLATE/$f" \|\| echo "MISSING: $f"; done` | no MISSING output | file missing = FAIL |
| R-4 | `team/remediation/README.md` has Decision rules section with 9 verbatim rows | `for row in 'Fix this bug.*clear evidence' 'Fix this bug.*without' 'Multi-file remediation' 'Security, release, auth, audit, credential' 'New feature' 'Wire contract change' 'Database schema change' 'Documentation typo' 'Dependency bump'; do grep -qE "$row" team/remediation/README.md \|\| echo "README missing: $row"; done` | no missing output | any row missing = FAIL |
| R-5 | `team/remediation/README.md` has PASS/FAIL/ESCALATE/3-strike summary | `grep -E "PASS.*FAIL.*ESCALATE\|3-strike\|hard-stop" team/remediation/README.md` | ≥ 1 hit | absent = FAIL |
| R-6 | `team/remediation/README.md` active-sessions table updated | 3 grep checks for the 3 new session slugs | all 3 present | any missing = FAIL |
| R-7 | `CONTRIBUTING.md` has the new Remediation-vs-Spec section | `grep -iE "Remediation vs Spec\|Remediation vs spec\|Spec-Driven.*Remediation" CONTRIBUTING.md` | ≥ 1 hit | absent = FAIL |
| R-8 | `CONTRIBUTING.md` quotes the same 9-row decision table | same grep loop as R-4 against `CONTRIBUTING.md` | no missing | any missing = FAIL |
| R-9 | `AGENTS.md` has the decision-routing section | `grep -E "Decision.*remediation\|Routing.*remediation" AGENTS.md` | ≥ 1 hit | absent = FAIL |
| R-10 | `AGENTS.md` quotes the same 9-row decision table | same grep loop as R-4 against `AGENTS.md` | no missing | any missing = FAIL |
| R-11 | `CLAUDE.md` has the decision-routing section | `grep -E "Decision.*remediation\|Routing.*remediation" CLAUDE.md` | ≥ 1 hit | absent = FAIL |
| R-12 | `CLAUDE.md` quotes the same 9-row decision table | same grep loop as R-4 against `CLAUDE.md` | no missing | any missing = FAIL |
| R-13 | `AGENTS.md` ↔ `CLAUDE.md` lock-step on the new section | extract the new section from each, `diff` them | ≤ 2 differing lines (the opening sentence) | any other diff = FAIL |
| R-14 | New anti-pattern rows present in both files | `grep -E "remediation without an issue intake\|orchestrator session" AGENTS.md CLAUDE.md` | ≥ 2 hits per file | absent = FAIL |
| R-15 | `.github/pull_request_template.md` has 5 required sections in order | `grep -nE "^## " .github/pull_request_template.md` | output shows Change Type → Required Provenance → Issue Definition → Verification → Agent/Automation Rules in that order | wrong order or missing = FAIL |
| R-16 | PR template Change Type has 5 verbatim checkboxes | `grep -cE "\[ \] (Remediation session\|Kiro/spec-driven feature\|Documentation-only\|Dependency-only\|Other)" .github/pull_request_template.md` | ≥ 5 | < 5 = FAIL |
| R-17 | PR template Verification has 4 verbatim checkboxes | grep for "Tests run", "Linters/validators run", "Smoke/integration run", "Security/plaintext" | all 4 present | any missing = FAIL |
| R-18 | PR template Agent/Automation Rules has 5 verbatim checkboxes | grep for "No `--no-verify`", "No unverified", "No unrelated refactor", "No accepted ADR edited", "No `Co-Authored-By`" | all 5 present | any missing = FAIL |
| R-19 | Skill `SKILL.md` frontmatter `description` mentions intake | `head -3 ~/.claude/skills/remediation-orchestrator/SKILL.md \| grep -iE "issue.intake\|intake.first\|9.field.intake"` | ≥ 1 hit | absent = FAIL |
| R-20 | Skill has `references/issue-intake.md`, project-agnostic | `test -f ~/.claude/skills/remediation-orchestrator/references/issue-intake.md && grep -iE "mintkey\|adr-[0-9]\|liquibase\|t_default\|mk_agent_\|kong\|rls" ~/.claude/skills/remediation-orchestrator/references/issue-intake.md` | file exists, grep returns empty | file missing OR project-specific identifier present = FAIL |
| R-21 | No `Co-Authored-By` trailer in any new commit | `git log --since=2026-05-16 --format='%B' \| grep -i 'co.authored.by.*claude\|noreply@anthropic'` | empty | any hit = FAIL |
| R-22 | No source code touched | `git diff <session-start>..HEAD -- ':!team/remediation/' ':!CLAUDE.md' ':!AGENTS.md' ':!CONTRIBUTING.md' ':!.github/' '*.py' '*.go' '*.ts' '*.tsx' '*.js' '*.yaml' '*.yml' '*.json' '*.proto'` | empty | any product-code diff = FAIL |
| R-23 | No `--no-verify` in any new commit | `git log --since=2026-05-16 --format='%H %s' \| while read h s; do git show --stat "$h" \| grep -i 'no.verify' && echo "FAIL: $h"; done` | empty | any hit = FAIL |
| R-24 | No edits to Accepted ADRs | `git diff <session-start>..HEAD -- docs/architecture/01-architecture/adr/` | empty | any ADR file changed = FAIL |
| R-25 | Decision-table rows are identical across all 4 files | extract the table rows from `team/remediation/README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`; `diff` pairwise | all 4 identical | any drift = FAIL |

**Hard-stop trigger:** if ≥ 2 rows fail and the implementer attempts a fix, the reviewer dispatches a new implementer with the prior findings verbatim (per the skill's standard FAIL → new IMPLEMENTER loop). Hard-stop at iteration 3.

**Pre-existing-issue carve-outs:** the active-sessions table refresh (R-6) and the AGENTS.md ↔ CLAUDE.md drift (R-13) both have known pre-existing state — AGENTS.md and CLAUDE.md already differ in a few places that this design does NOT require fixing. The reviewer must diff ONLY the new section, not the whole files. R-13's `awk` extracts the new section; reviewer should not flag pre-existing drift elsewhere.

---

## Out of scope for this design (deferred items)

- **Renumbering existing session files** to match the SESSION_TEMPLATE. The active sessions stay as they are.
- **Migrating the `task-implement` skill** to also live in `~/.claude/skills/`. That skill is Mintkey-specific and stays in `.agents/skills/` + `.claude/skills/`. We do not touch it.
- **Making `make new-session` Makefile target** (per F3 recommendation). Deferred until/unless user opts into F3-B.
- **`.opencode/AGENTS.md` symlink** (per F1 recommendation). Deferred until/unless user opts into F1-B.
- **A separate `RUNBOOK.md` for the orchestrator pattern**. The README + skill split is sufficient; a third document would just add a drift surface.

## Implementation dispatch order (recommended)

1. User signs off on this design (or replies with deltas).
2. User answers forks F1, F2, F3, F4 (or accepts the recommendations).
3. Implementer creates session step files (`01-orchestrator-chunks.md`, `02-matrix.md`, `04-progress.md`) and dispatches:
   - **PE-1** (Templates + Skill) — medium chunk, dispatch first since PE-2/PE-3 reference the intake template.
   - **PE-2** (Repo governance) — small chunk, dispatches after PE-1's intake-template-shape lands so the decision-table cross-references the file.
   - **PE-3** (Agent guardrails) — small chunk, can dispatch in parallel with PE-2 if implementers are disjoint (different sub-agents), but the orchestrator's preference is serial so PE-3 can copy PE-2's verbatim table.
   - **PE-4** (PR template) — small chunk, can dispatch anytime; orthogonal to the others.
4. After all 4 chunks PASS implementer + reviewer, the orchestrator spawns a final full-DoD REVIEWER running the entire R-1 through R-25 matrix and writes `99-report.md`.

Total estimated implementer chunks: 4 (medium + small + small + small) ≈ 1 medium + 3 small. Estimated total net new lines: ~1100–1500 across 12 files (8 edited/rewritten, 4–7 new).
