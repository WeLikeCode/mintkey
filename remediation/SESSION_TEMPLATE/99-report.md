# <Session Title> — Closing Report

> Copy from SESSION_TEMPLATE — fill in the placeholders.

**Session:** `<YYYY-MM-DD-kebab-slug>`
**Status:** <TODO: CLOSED | CLOSED-WITH-RESIDUALS | HARD-STOP>
**Closed by:** Final REVIEWER subagent

---

## Summary

<TODO: One paragraph. What was fixed, what was verified, what is left.>

---

## Verification commands and exit codes

All commands below were run by the final REVIEWER after all chunks passed:

```
<TODO: paste verification command>
exit code: <TODO: 0 | N>

<TODO: paste next verification command>
exit code: <TODO: 0 | N>
```

---

## Chunks completed

| Chunk | Commit | Reviewer verdict | Rounds |
|---|---|---|---|
| C-1: `<TODO: title>` | `<TODO: hash>` | PASS | 1 |
| C-2: `<TODO: title>` | `<TODO: hash>` | PASS | <TODO: N> |

---

## DoD checklist — final state

- [x] <TODO: AC-1> — verified via `<TODO: command>`
- [x] <TODO: AC-2> — verified via `<TODO: command>`
- [x] No `Co-Authored-By` trailer in any new commit
- [x] No `--no-verify` used

---

## Residual risks / deferred items

<TODO: List any P2/P3 items not addressed, or write "None."
Each deferred item should reference the matrix row (e.g. M-3) and explain why it was deferred.>

---

## Escalation resolutions

<TODO: Paste the answered escalation entries from `03-escalations.md`, or write "None.">>

---

## Lessons learned / notes for next session

<TODO: Optional. What should the next implementer or orchestrator know?>
