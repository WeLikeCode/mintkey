# <Session Title> — Chunk Catalog

> Copy from SESSION_TEMPLATE — fill in the placeholders.

**Session:** `<YYYY-MM-DD-kebab-slug>`
**Driver:** `remediation-orchestrator` skill
**Phase 0:** ⬜ pending baseline review

---

## Locked decisions (apply to every chunk)

<TODO: List any owner decisions resolved from `ISSUE_INTAKE.md` "Owner decisions needed" field.>

| Decision | Value | Source |
|---|---|---|
| <TODO: decision> | <TODO: value> | `ISSUE_INTAKE.md` → owner answer |

---

## Universal hard rules (every implementer brief inherits these)

- No `Co-Authored-By: Claude` trailer on any commit
- No `--no-verify` on commits
- No `docker compose down -v`
- No edits to accepted ADRs
- Validate via tools: every "done" claim carries command output
- Surgical changes; one logical change per commit
- Update `02-matrix.md` row(s) you closed before committing

---

## Chunk dispatch plan

### Wave 1

| # | Chunk | Owner files | Acceptance criterion | Status |
|---|---|---|---|---|
| <TODO: ID> | <TODO: short title> | <TODO: file(s)> | <TODO: pass condition> | ⬜ pending |

### Wave 2 (parallel, after Wave 1 passes)

| # | Chunk | Owner files | Acceptance criterion | Status |
|---|---|---|---|---|
| <TODO: ID> | <TODO: short title> | <TODO: file(s)> | <TODO: pass condition> | ⬜ pending |

---

## Status legend

| Symbol | Meaning |
|---|---|
| ⬜ | Pending |
| 🔵 | Dispatched (in-flight) |
| ✅ | Reviewer PASS |
| ❌ | Reviewer FAIL — new implementer dispatched |
| 🛑 | Hard-stop — 3 failures; awaiting user |
| ⚠️ | Escalated — awaiting owner decision |
