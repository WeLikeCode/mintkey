# <Session Title> — Tracking Matrix

> Copy from SESSION_TEMPLATE — fill in the placeholders.

**Session:** `<YYYY-MM-DD-kebab-slug>`
**Status:** ⬜ pending baseline review

---

## Severity legend

| Severity | Meaning |
|---|---|
| P0 | Blocking — session cannot close without this |
| P1 | High — must address before the closing report |
| P2 | Medium — fix this session if possible; escalate if not |
| P3 | Low — document as residual; defer acceptable |

## Status legend

| Symbol | Meaning |
|---|---|
| ⬜ | Not started |
| 🔵 | In progress |
| ✅ | Fixed and reviewer-verified |
| ⏭️ | Deferred to a future session (document in 99-report.md) |
| n/a | Not applicable |

---

## Matrix

| # | Area | Finding | Severity | Chunk | Status | Notes |
|---|---|---|---|---|---|---|
| M-1 | <TODO: area> | <TODO: what is broken> | P0 | <TODO: chunk ID> | ⬜ | <TODO: notes> |
| M-2 | <TODO: area> | <TODO: what is broken> | P1 | <TODO: chunk ID> | ⬜ | |
| M-3 | <TODO: area> | <TODO: what is broken> | P2 | <TODO: chunk ID> | ⬜ | |

---

## Verification DoD checklist

Reviewer runs these before writing `99-report.md`:

- [ ] <TODO: test / command proves M-1 fixed>
- [ ] <TODO: test / command proves M-2 fixed>
- [ ] No regressions in scope: `<TODO: command>`
- [ ] No `Co-Authored-By` trailer in any new commit
- [ ] No `--no-verify` used
