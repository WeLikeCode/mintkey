---
name: risk-register-update
description: Update a risk register based on new evidence — validate, invalidate, add, or supersede a risk. Enforces the three-question test (what specifically breaks, cited evidence, named affected component). Activate when the user says "update risks", "is risk R-N still real", or "add a risk for {situation}".
compatibility: Requires read/write access to the project's risk-register.md. Pairs with assumption-validate (assumptions become risks if invalidated).
metadata:
  author: kiro-project-template
  version: 0.2
---

## Instructions

You update the risk register based on new evidence. You enforce the **three-question test** on every entry: (a) what specifically breaks, (b) cited evidence, (c) named affected component. Entries that fail the test are rejected as padding.

## When to invoke

- "Update risk R-N"
- "Is R-N still real?"
- "Add a risk for {situation}"
- "Validate the risks register"

## When NOT to invoke

- First-time register creation → write the doc directly using the template (see References)
- Generic platform concern → it's not a risk; send to backlog
- Stakeholder clarification → goes to Open Decisions, not Risks

## Inputs

- `register-path` (required)
- `risk-id` (for update) or `new-risk-statement` (for add)
- `evidence` (required for validate / invalidate / add)

## Template

The risk register template lives in this skill's references directory:

#[[file:.kiro/skills/risk-register-update/references/risk-register-template.md]]

## Workflow

1. Read the existing register.
2. For each proposed change, enforce the **three-question test**:
   - (a) What specifically breaks?
   - (b) What evidence shows this is real (citation)?
   - (c) Which decision / component depends on this?
   If any answer is missing → reject the change, ask for evidence.
3. **Reject these as padding** (per the steering rule on real-risks-not-padding):
   - Generic platform concerns (data sovereignty, container access, terminology drift)
   - Speculative "could potentially happen in some configuration"
   - Citations of prototype / PoC code as production-architecture evidence
   - Stakeholder clarification questions (those go to Open Decisions)
4. For supersession: link old entry to new with explicit reason.
5. Output diff of the register; let the user approve before writing.

## Output

- Markdown diff of risk register.
- Explicit list of rejected changes with reasons.

## Anti-patterns

- Adding speculative risks to look thorough.
- Citing prototype code as evidence.
- "Validating" a risk just because time has passed without new evidence.
- Letting an `adversarial-review` subagent inject padding risks.
