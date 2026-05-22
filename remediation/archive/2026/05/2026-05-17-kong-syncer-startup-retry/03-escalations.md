# Escalations

**Session:** `2026-05-17-kong-syncer-startup-retry`

No escalations recorded yet.

## Trigger conditions

- Any implementer chunk fails review 3× in a row → 🛑 hard-stop, record here with FAIL evidence.
- Any owner-decision-touching ambiguity surfaces mid-implementation → ⚠️ escalation, record here and ask owner.
- Any forbidden-file edit detected → ❌ immediate FAIL with file path; record here.

## Template

```
### E-1 — <short title>
- **When:** YYYY-MM-DD HH:MM
- **Chunk:** <ID>
- **Trigger:** <which condition>
- **Evidence:** <log excerpt / file:line / reviewer note>
- **Asked owner:** <yes/no, when>
- **Resolution:** <pending | <one-line outcome>>
```
