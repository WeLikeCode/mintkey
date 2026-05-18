# Escalations — Dev Settings Backup & Recovery

**Session:** `2026-05-18-dev-settings-backup-recovery`

No escalations recorded yet.

## Trigger conditions

- Any implementer chunk fails review 3× in a row → 🛑 hard-stop, record here with FAIL evidence.
- C-1 evidence reveals that the only way to close a critical destructive path is a product-code change → ⚠️ escalation (the chunk catalog explicitly forbids product-code edits without owner approval).
- The only way to verify the restore round-trip is to wipe and restore real state → ⚠️ escalation (default is dry-run only).
- A backup containing real secrets accidentally lands somewhere non-gitignored → 🛑 immediate hard-stop, owner-notify with the leak path.
- C-1 evidence cannot be gathered without running a destructive command → ⚠️ escalation.

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
