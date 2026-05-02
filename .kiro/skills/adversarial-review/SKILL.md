---
name: adversarial-review
description: Multi-lens parallel review of a draft artifact. Spawns 2-4 subagents with different perspectives and synthesizes severity-tagged findings. Activate when the user says "adversarial review this", "validate via subagents", "review from multiple perspectives", or "tear this apart". NOT for routine PR review (use code-review skill) or premise attacks of un-drafted ideas (use think-tiger).
compatibility: Requires the ability to spawn parallel sub-agents. Best paired with adr-from-decision and risk-register-update for follow-through.
metadata:
  author: kiro-project-template
  version: 0.2
---

## Instructions

You run a multi-lens parallel review of a draft artifact. You spawn 2-4 subagents with different perspectives, collect their severity-tagged findings, and synthesize them into one actionable list.

## When to invoke

- "Adversarial review this"
- "Validate via subagents"
- "Review from multiple perspectives"
- "Tear this apart"

## When NOT to invoke

- PR / branch review → use the project's `code-review` skill if present
- Security-only review → use a dedicated security-review skill
- Single-perspective check → just answer directly
- Premise challenge of a not-yet-drafted idea → use `think-tiger`

## Default lens picker (by artifact type)

| Artifact | Default lenses |
|---|---|
| Data model / DBML | data-integrity, consumer-system, producer-system |
| API contract | backend, frontend-consumer, security |
| ADR | architectural-coherence, timeline-cost, operations |
| Sprint plan | capacity, risk, dependency |
| UX spec | frontend, accessibility, backend-feasibility |
| Code design / proposal | backend, frontend, timeline |
| Vision doc | named-stakeholder, internal-coherence, build-vs-buy |
| Workflow / state machine | backend, frontend-UX, project-timeline |

Override with `lens-overrides` if the artifact has a specific named audience.

## Workflow

1. Resolve scope; pick lenses via type table (override if user named them).
2. **Spawn N lenses in PARALLEL** — single turn, multiple Agent calls. Sequential is a bug.
3. Each lens prompt has: role framing, target path, companion docs, 8-12 attack questions, severity-tagged output format (CRITICAL / MAJOR / MINOR).
4. Synthesize findings: dedupe, number globally, group by severity.
5. **Reject "padding" findings** — generic platform stuff or speculative concerns get dropped (see steering rule on real-risks-not-padding).
6. Apply CRITICAL fixes inline; surface MAJOR / MINOR as a triage table for the user.
7. Re-validate (compile DBML, lint OAS, validate fixtures against schemas) — if validation fails, revert and surface as new finding.
8. Report: scope / findings table / fixes applied / open items / validation result.

## Output

Chat report with severity-tagged findings, inline fixes for CRITICAL only, triage table for MAJOR / MINOR.

## Anti-patterns

- Sequential lens calls (parallel is mandatory).
- Auto-applying MAJOR fixes.
- More than 4 lenses (noise > insight).
- Accepting subagent-invented "missing risks" without evidence cross-check.
- Reviewing your own session-authored work without flagging the conflict openly.
