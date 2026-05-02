# Onboarding — Architect track

**Time:** ~3 hours, Day 0
**Outcome:** you can run the wizard, draft your first ADR, and identify the top 3 open questions to schedule.

| # | File | Time | What you'll know after |
|---|---|---|---|
| 1 | [BOOTSTRAP.md](../../BOOTSTRAP.md) | 15 min | The wizard exists, what it asks, when it refuses |
| 2 | [bootstrap/questionnaire.md](../../bootstrap/questionnaire.md) | 25 min | Pre-think your 25 answers |
| 3 | Invoke `project-setup` skill in Kiro (or `./bootstrap/setup-wizard.sh`) | 30 min | Engagement is populated |
| 4 | [.kiro/steering/STEERING-PROTOCOL.md](../../.kiro/steering/STEERING-PROTOCOL.md) | 20 min | How agents load steering on demand |
| 5 | [.kiro/steering/skills-catalog.md](../../.kiro/steering/skills-catalog.md) + skim 3 individual skills | 20 min | What skills exist and when each fires |
| 6 | All files in `.kiro/steering/rule-` | 15 min | Always-loaded protocol rules — what overrides everything |
| 7 | [.kiro/skills/adr-from-decision/references/adr-template.md](../../.kiro/skills/adr-from-decision/references/adr-template.md) | 10 min | ADR house style |
| 8 | Generated `docs/architecture/architecture-vision.md` | 20 min | Your scaffold; refine later |
| 9 | Generated `docs/architecture/risk-register.md` | 15 min | Verify your three real risks landed cleanly |
| 10 | Generated `.kiro/steering/open-questions.md` | 10 min | Schedule the top 3 |

## Your first hour after bootstrap

1. Run `/architecture-advisor` on the most contested decision you have. Surface 3-5 options. Don't decide yet — just lay out the field.
2. Run `/think-tiger` against your strongest leaning. Notice what assumptions it identifies.
3. Once you do decide, run `/adr-from-decision` to draft ADR-0001. The skill drafts in `team/{your-handle}/drafts/`. Review, then `git mv` to canon.
4. Schedule a workshop for the highest-priority open question.

## Before you let developers onto the repo

- `docs/architecture/architecture-vision.md` is at least skeleton-complete (1-2 pages for Discovery; 3 pages for PoC).
- At least one ADR is Accepted.
- Risk register has the three Q25 risks plus any architectural risks surfaced by `think-tiger`.
- CODEOWNERS routes `docs/architecture/` and `.kiro/steering/` to you.
- `.kiro/skills/` is populated and devs know the skills exist.

## Architectural baseline (if not opting out)

The template's defaults are documented in `README.md` §Architectural baseline. By default you get:
- Append-only / immutable business records
- Idempotent processing
- Single-writer-per-table
- Contract-first development
- Observability-by-default

If you opt out of any, the wizard records the override as ADR-0001-bootstrap with the trade-off you accepted.

## Common Day-0 failure modes

- **Filling out Q25 with platitudes.** Refuse yourself. Real risks force evidence.
- **Loading every steering file "to get a feel."** Trust the three-mode loading protocol (default / fileMatch / manual).
- **Letting a developer author the first ADR.** Architect owns ADRs. They implement.
- **Skipping the questionnaire.** The wizard refuses. So should you.
- **Agreeing with everything `think-tiger` says.** It's an attack surface, not a verdict.

## Sign in

```bash
cp team/_template/onboarded.md team/{your-handle}/onboarded.md
```

Tick the gates. Push. Now the team knows the architect is on board.
