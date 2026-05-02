# Rule: Smallest first cut

**Always-loaded protocol rule.**

## The rule

When asked to produce an artifact (doc, spec, ADR, plan, register, code design), produce the **smallest version that unblocks the next decision** — not the most complete version.

If a one-paragraph note is enough, write a one-paragraph note. If a 4-section ADR is enough, write 4 sections — not 13. If a 6-row table is enough, don't pad to 20.

## Why

Over-elaboration is a failure mode. A 13-section workflow proposal when the user wanted 3 sections wastes their time, attracts more review cycles, and dilutes the signal of the decisions actually being made.

The user has explicitly opted into this discipline. When in doubt:
- Ship the small version.
- Offer to expand specific sections if the user asks.
- Do NOT pad with "for completeness" sections that aren't load-bearing.

## Heuristics

- ADR target: 250-500 words.
- Risk register entry: 1-3 sentences per risk.
- Decision-log entry: ≤ 80 words.
- Architecture vision skeleton at Discovery phase: ≤ 1 page.
- Working set at PoC phase: ≤ 3 pages.
- Full vision at pre-MVP: as long as needed but no longer.

## Application

Skills that generate artifacts (`adr-from-decision`, `decision-log-append`, `meeting-notes-distill`) honor this rule automatically. When the user asks for "the full plan," check whether the engagement phase warrants the full plan. If they're in Discovery, push back: "smallest cut would be X — do you want the full version anyway?"

This rule pairs with the steering anti-pollution caps (1500 words per file) and the ADR cadence rule (≤ 5 ADRs per sprint sustained).
