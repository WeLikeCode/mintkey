# Skills Catalog

> Skills are scoped, repeatable workflows invoked by name. They live in `.kiro/skills/<name>/SKILL.md` per Kiro convention. This catalog documents the skills the template ships and the boundaries between them.

## Skills shipped with this template

| Skill | Category | Trigger phrasings | When NOT to use |
|---|---|---|---|
| `architecture-advisor` | governance | "should I use X or Y", "trade-offs of", "is this the right pattern" | User has decided → `adr-from-decision`. Premise attack → `think-tiger`. |
| `think-tiger` | governance | "challenge this", "stress-test my thinking", "play devil's advocate", "what am I missing" | User wants neutral options → `architecture-advisor`. Persona-review of a draft → `adversarial-review`. |
| `adversarial-review` | review | "tear this apart", "multi-lens review", "validate via subagents" | PR review → use the project's code-review skill. Premise attack of un-drafted idea → `think-tiger`. |
| `adr-from-decision` | generation | "write ADR for X", "promote this to an ADR" | Decision not yet made → `architecture-advisor`. Light note → `decision-log-append`. |
| `risk-register-update` | governance | "update risks", "is risk R-N still real", "add a risk for {situation}" | First-time creation → write the doc. Generic platform concern → backlog. |
| `assumption-validate` | governance | "validate assumption A-N", "is this still open" | It's a risk → `risk-register-update`. It's a decision → `adr-from-decision`. |
| `spec-first-check` | governance | "implement X", "build the worker for Y", "let's code Z" | Pure refactor / test-only / doc-only changes. Explicit `--skip-spec-first`. |
| `decision-log-append` | generation | "log this decision", "note this for later" | Architectural cascade → `adr-from-decision`. |
| `requirements-extract` | generation | "extract requirements from X", "ingest BA notes", "update requirements from meeting notes", "deduplicate requirements" | Single known requirement → edit CSV directly. Document is an ADR → not requirements. Content is risks/assumptions → use those skills. |
| `project-setup` | onboarding | "set up this project", "run the onboarding wizard", "bootstrap the project" | Project already set up (`completed: true` in `.kiro/setup-state.json`) → exits. User is not the architect → redirects. |
| `task-implement` *(Claude Code skill)* | implementation | "implement task T-N", "pick up the next task in `<feature>`", "start the next Kiro task", "work on tasks.md" | No spec / design stub → `spec-first-check` then architect. Architectural / governance work → wrong skill. Pure refactor / test-only / doc-only → just edit. |

11 skills. Roughly: 4 governance / 3 generation / 1 onboarding / 1 review / 1 anti-vibe-coding gate / 1 implementation.

> **Skill location convention:** governance / generation / review / onboarding skills live under `.kiro/skills/<name>/SKILL.md` (Kiro convention — invoked by Claude reading this catalog). The `task-implement` skill is a **Claude Code skill** at `.claude/skills/task-implement/SKILL.md` because it depends on Claude Code primitives (`ExitPlanMode` for the plan gate, parallel `Agent` sub-agents for execution and milestone review/test gates) that aren't part of the plain Kiro convention.

## Boundaries between overlapping skills

- **architecture-advisor vs think-tiger:** advisor is neutral exploration; tiger is hostile attack. If user is exploring → advisor. If user is leaning → tiger.
- **think-tiger vs adversarial-review:** tiger attacks an idea (no draft yet); adversarial-review attacks a written artifact via personas.
- **decision-log-append vs adr-from-decision:** log if < 80 words and no architectural cascade; ADR if there are consequences worth a Consequences section.
- **risk-register-update vs assumption-validate:** risk has a failure mode; assumption is a claim being acted on. If you can answer "what breaks if this is wrong" — it's a risk.
- **requirements-extract vs decision-log-append:** if the source text states what the system must do → requirement. If it records a choice that was made → decision. If it states a constraint with architectural cascade → both (extract the requirement, log the decision).
- **project-setup vs other skills:** project-setup runs once (or resumes). All other skills assume the project is already set up. If `.kiro/setup-state.json` is missing, run project-setup first.
- **task-implement vs spec-first-check:** `spec-first-check` is the **gate** — it refuses code work when no spec exists. `task-implement` is the **execution** — it picks up an already-spec'd task and ships it. If the spec exists, jump straight to `task-implement`; it re-runs the same readiness checks before any code is written.
- **task-implement vs adr-from-decision:** `task-implement` ships code against an existing design. `adr-from-decision` captures a new architectural decision. If the implementation forces a new decision, surface it and hand off to `adr-from-decision`; do not silently bake the decision into code.

## Adding a new skill

1. Create `.kiro/skills/<skill-name>/SKILL.md` with proper frontmatter:
   ```yaml
   ---
   name: skill-name
   description: One-paragraph description with activation phrasings
   compatibility: What context / access the skill needs
   metadata:
     author: <handle>
     version: 0.1
   ---
   ```
2. Place reference templates in `.kiro/skills/<skill-name>/references/`.
3. Embed reference content from the SKILL.md using Kiro's `#[[file:...]]` syntax — pulls templates into context only when the skill activates.
4. Add the skill to the table above with trigger phrasings and when-NOT-to-use boundaries.
5. PR with at least 1 dogfood example — show the skill running on a real artifact.

## Anti-patterns explicitly excluded

- Skill that wraps a single command-line invocation (just use the command).
- Skill with vague "review this" semantics — be specific about what's reviewed and how.
- Skill that auto-applies changes without user confirmation for non-trivial cases.
- Skill catalog with 30+ entries — too many to remember = useless.

## Boundary with agents and hooks

| Construct | Purpose | Lives in |
|---|---|---|
| **Skill** (`SKILL.md`) | User-invoked, repeatable workflow with clear trigger phrasings, completes in < 5 minutes | `.kiro/skills/<name>/` |
| **Hook** (`*.kiro.hook` JSON) | Event-triggered automation (file-saved, user-triggered, schedule) | `.kiro/hooks/` |
| **Steering file** (markdown) | Stable rules / conventions / governance the agent should always know about | `.kiro/steering/` |
| **Spec** (Kiro SDD docs) | Per-feature requirements / design / tasks | `.kiro/specs/<feature>/` |

If you find yourself wanting a "long-running multi-step thing with autonomous decisions," that's not a skill — that's likely a separate agent definition, outside the Kiro `.kiro/` directory.
