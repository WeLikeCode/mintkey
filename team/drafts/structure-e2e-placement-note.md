# Draft: document the Playwright E2E placement in structure.md

**Status:** draft for architect review — `.kiro/steering/structure.md` is
architect-owned (steering protocol: agents suggest diffs in `team/drafts/`, the
architect applies). Do NOT apply this by agent edit.

**Why:** the browser E2E suite lives at `apps/admin-ui/e2e/`, not under the root
`tests/` tree. That is deliberate (co-located with the deployable it drives +
its Node/Playwright toolchain; the root `tests/` tree is the Python
cross-service suite). It is currently undocumented in steering, so a reader
seeing only the root `tests/` block could reasonably think e2e is misplaced.
This note makes the split explicit. Prompted by a reviewer question during the
agent-access-requests feature (Task 10.1 added `44-access-requests-review.spec.ts`).

## Suggested edit 1 — annotate the repo-map `tests/` block

In the repo-map fenced block, replace:

```
├── tests/
│   ├── acceptance/                  # Behavioral tests citing ADR / spec IDs
│   ├── integration/                 # Integration tests per service
│   ├── unit/                        # Implementation-coupled
│   └── architecture/                # Architecture tests (RLS, audit coverage)
```

with:

```
├── tests/                           # Python cross-service tests (pytest/uv)
│   ├── acceptance/                  # Behavioral tests citing ADR / spec IDs
│   ├── integration/                 # Integration tests per service
│   ├── unit/                        # Implementation-coupled
│   └── architecture/                # Architecture tests (RLS, audit coverage)
│   # Note: browser E2E for the Admin Console is NOT here — it lives with the
│   # app it drives, at apps/admin-ui/e2e/ (Playwright/pnpm). See "Testing layout".
```

And, in the `apps/` block, annotate the admin-ui line (optional):

```
│   ├── admin-ui/                    # Admin Console — AdminJS (Node 20 + Express); browser E2E in admin-ui/e2e/
```

## Suggested edit 2 — add a "Testing layout" subsection

Add after the "Key conventions" section (or wherever the architect prefers):

```markdown
## Testing layout

Tests are split by **language + scope**, not gathered in one tree:

| Location | Owns | Toolchain |
|---|---|---|
| `tests/` (`acceptance/`, `integration/`, `unit/`, `architecture/`) | Python cross-service system tests (admin-api, mcp-server, mintkey-models) | `pytest` / `uv` |
| `apps/admin-ui/e2e/` | Browser E2E for the AdminJS Admin Console deployable | Playwright / `pnpm` (Node 20) |

The Admin Console browser E2E is co-located with the app it drives: it is that
deployable's acceptance layer, uses admin-ui's own Node toolchain (one
`package.json` / `playwright.config.ts` / `test:e2e` script), and is owned by
the admin-ui team. It still reaches admin-api / mcp-server / Keycloak at runtime
(system-level behaviour), but it is packaged with the Node app rather than in
the Python `tests/` tree.

Rationale + run/artifact details: `apps/admin-ui/e2e/README.md`.
E2E run artifacts (`test-results/`, `playwright-report/`, `state.json`) are
git-ignored; only the suite source is tracked.

If this convention changes, update in lock-step: this file, the e2e README,
`.github/workflows/playwright.yml`, the `Makefile` `test:e2e*` targets, and the
`.gitignore` e2e-artifact rules.
```
