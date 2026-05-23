# Escalations — Post-Prealpha Readiness

**Session:** `2026-05-19-post-prealpha-readiness`

No escalations recorded yet.

## Trigger conditions

- Any implementer chunk fails review 3× → 🛑 hard-stop.
- A spec requirement appears to need an ADR edit → ⚠️ escalation (Requirement 9 explicitly forbids ADR edits).
- A spec requirement appears to need a core-service-code change → ⚠️ escalation.
- A red-team grep returns ANY match on any deliverable → 🛑 immediate hard-stop; scrub + force-push pattern (per DSBR `EV-LEAK-001` precedent).
- A task's "owner action" turns out to need a clarification not in the spec → ⚠️ ask the owner.

## Template

```
### E-N — <short title>
- **When:** YYYY-MM-DD HH:MM
- **Chunk:** <ID>
- **Trigger:** <which condition>
- **Evidence:** <quote / file:line>
- **Asked owner:** <yes/no>
- **Resolution:** <pending | <outcome>>
```
