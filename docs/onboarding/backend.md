# Onboarding — Backend developer

**Time:** ~2 hours, Day 1
**Outcome:** you can pick a starter ticket, write & test code that matches conventions, open a PR that passes pre-commit + CI.

| # | File | Time |
|---|---|---|
| 1 | [BOOTSTRAP.md](../../BOOTSTRAP.md) | 15 min |
| 2 | `.kiro/steering/structure.md` | 10 min |
| 3 | `.kiro/steering/{your-language}-conventions.md` (Python / TypeScript / Go / Java …) | 20 min |
| 4 | `.kiro/steering/api-contracts-and-schemas.md` | 20 min |
| 5 | [`contracts/README.md`](../../contracts/README.md) + skim one OpenAPI spec | 15 min |
| 6 | `.kiro/steering/database-conventions.md` (if persistence is in scope) | 15 min |
| 7 | `.kiro/steering/testing-strategy.md` + `fixtures-and-test-data-strategy.md` | 20 min |
| 8 | `.kiro/steering/developer-workflows.md` (PR flow) | 15 min |

## Before you write code

- Run `/spec-first-check`. It refuses if your ticket has no referenced spec / ADR / contract.
- Read the closest 1-2 ADRs. PR descriptions cite them.
- If you can't find a spec, surface that to the architect. Don't hand-wave one.

## Common Day-1 failure modes

- Writing code without a spec — `spec-first-check` will catch you.
- Editing files in `docs/architecture/` — that's architect-owned.
- Using `Field("camelCase")` Python attribute names instead of snake_case + `Field(alias=...)` (or your language's equivalent — see conventions file).
- Skipping fixtures — every contract change needs a fixture update.

## Sign in

```bash
cp team/_template/onboarded.md team/{your-handle}/onboarded.md
```
