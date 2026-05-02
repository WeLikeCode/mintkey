# Onboarding — TL / Engineering Manager

**Time:** ~90 min, Day 0-1
**Outcome:** you can chair stand-up, run the ADR review meeting, route incoming work to the right CODEOWNER, sign off the team RACI.

| # | File | Time |
|---|---|---|
| 1 | [README.md](../../README.md) | 10 min |
| 2 | [BOOTSTRAP.md](../../BOOTSTRAP.md) | 10 min |
| 3 | `.kiro/steering/repo-governance.md` | 15 min |
| 4 | `.kiro/steering/ownership-and-codeowners-strategy.md` + `CODEOWNERS` | 15 min |
| 5 | `.kiro/steering/branching-and-release.md` | 15 min |
| 6 | [docs/architecture/risk-register.md](../architecture/risk-register.md) + [open-questions.md](../architecture/open-questions.md) | 15 min |
| 7 | [.kiro/steering/skills-catalog.md](../../.kiro/steering/skills-catalog.md) | 10 min |

## Your responsibilities

- **Chair the architecture review meeting.** Architect drives content; you keep cadence.
- **Track open questions.** Each must have an owner, a forcing function, and a target sprint.
- **Surface drift.** If devs are merging PRs without spec citations, the `vibe-check` CI report shows you. Coach, don't crackdown.
- **Protect the architect's bandwidth.** Triage. Not every question goes to the architect. Decision-log entries are fine for tactical choices.

## What you do NOT own

- ADR content — that's the architect.
- Schema authoring rules — architect.
- Risk register entries — architect (you can flag concerns; architect approves).
- Threat model — architect.

You implement governance; you don't author it. (See [`.kiro/steering/rule-role-ownership-architect-vs-developer.md`](../../.kiro/steering/rule-role-ownership-architect-vs-developer.md).)

## Common Day-0 failure modes

- TL author of the first ADR — should be architect.
- TL absorbing risk-register updates that lack evidence — push back on padding.
- Allowing scope creep through TL-level decisions when the call is architectural.

## Sign in

```bash
cp team/_template/onboarded.md team/{your-handle}/onboarded.md
```
