# Onboarding — Frontend developer

**Time:** ~2 hours, Day 1
**Outcome:** you can scaffold a new component using the kit, wire it to a real contract, ship a PR.

| # | File | Time |
|---|---|---|
| 1 | [BOOTSTRAP.md](../../BOOTSTRAP.md) | 15 min |
| 2 | `.kiro/steering/web-app-structure.md` | 15 min |
| 3 | `.kiro/steering/frontend-conventions.md` | 20 min |
| 4 | `packages/ui-kit/README.md` (if shipped) | 15 min |
| 5 | `.kiro/steering/api-contracts-and-schemas.md` (consumer view) | 15 min |
| 6 | `.kiro/steering/testing-strategy.md` (frontend section) | 15 min |
| 7 | `.kiro/steering/developer-workflows.md` | 15 min |
| 8 | Run one Storybook story end-to-end (or framework equivalent) | 15 min |

## Before you write a component

- Verify the contract exists. Frontend talks to backends through generated SDKs — don't roll your own client.
- If forms are involved and the engagement opted into schema-driven UI (Q19=Yes), the form is rendered from a JSON Schema. You don't author UI structure; you author the schema.

## Common Day-1 failure modes

- Hand-writing API client code instead of using the generated SDK.
- Inventing form fields not in the schema (defeats schema-driven UX).
- Missing accessibility attributes — frontend conventions enforce minimums.

## Sign in

```bash
cp team/_template/onboarded.md team/{your-handle}/onboarded.md
```
