# Orchestration state — {{session-slug}}

<!-- Save this file as <session-dir>/04-progress.md or ORCHESTRATION_STATE.md at repo root.
     Keep it exact and complete — a future Claude session reads this to resume. -->

## DoD checklist

- [ ] AC-1 {{description}} — {{status: red | green | in-progress}}
- [ ] AC-2 {{description}} — {{status}}
- [ ] AC-3 {{description}} — {{status}}
<!-- Add all required DoD items. Do not summarize — be specific. -->

## Chunk plan

| # | Chunk | Owner files | Status | Round |
|---|---|---|---|---|
| C-1 | {{chunk_description}} | {{files}} | pending | — |
| C-2 | {{chunk_description}} | {{files}} | pending | — |
<!-- Status values: pending / in-flight / done / failed / escalated -->

## Current round

Round {{N}} for chunk {{C-X}}: implementer {{dispatched | done}},
reviewer {{not-yet | dispatched | done}}, verdict {{n/a | PASS | FAIL | ESCALATE}}.

## Round history (append-only)

<!-- Add one line per completed round. Never delete lines. -->
- Round 1 C-1: implementer DONE — commit {{hash}}; reviewer PASS.
- Round 1 C-2: implementer DONE — commit {{hash}}; reviewer FAIL — {{reason}}.
- Round 2 C-2: implementer DONE — commit {{hash}}; reviewer PASS.

## Open questions for the user

<!-- OQ entries: add when blocked on a decision; mark answered when resolved. -->
- OQ-1: {{question}} — open (asked {{YYYY-MM-DD}})
<!-- - OQ-1: {{question}} — answered {{YYYY-MM-DD}}: {{answer}} -->

## Notes

{{free_form_notes}}
