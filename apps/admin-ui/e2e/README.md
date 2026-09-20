# Admin Console — Playwright E2E

Browser end-to-end tests for the AdminJS operator UI (`apps/admin-ui`). Driven
by Playwright against a running Mintkey stack; they log in through Keycloak SSO
and exercise the real operator screens.

- **Test tree:** `apps/admin-ui/e2e/tests/`
- **Page objects:** `apps/admin-ui/e2e/pages/`
- **Fixtures / seed helpers:** `apps/admin-ui/e2e/fixtures/`
- **Config:** `apps/admin-ui/e2e/playwright.config.ts`
- **Coverage map:** [`COVERAGE.md`](./COVERAGE.md)
- **Run:** `pnpm test:e2e` (from `apps/admin-ui/`) — chromium in CI, all browsers locally

## Why the e2e suite lives here (under `apps/admin-ui/`) and not in the root `tests/`

This is a deliberate placement, not an accident. The repo splits tests by
**language + scope**:

| Location | Owns | Toolchain |
|---|---|---|
| root [`tests/`](../../../tests/) (`acceptance/`, `integration/`, `architecture/`, `unit/`) | Python cross-service system tests (admin-api, mcp-server, mintkey-models) | `pytest` / `uv` |
| `apps/admin-ui/e2e/` (this folder) | Browser E2E for the AdminJS UI deployable | Playwright / `pnpm` (Node 20) |

Rationale for co-locating the browser E2E with the app it drives:

1. **Coupled to one deployable.** These specs exercise the Admin Console UI
   specifically — they are the admin-ui's own acceptance layer, owned by the
   admin-ui team. Keeping them in the component keeps ownership and tooling local.
2. **Toolchain locality.** Playwright is a Node dependency. Living under
   `apps/admin-ui/` means one `pnpm` resolution, one `package.json`, one config,
   one `test:e2e` script — no second detached Node package under root `tests/`.
3. **Consistent with the monorepo split.** Root `tests/` is the Python
   cross-service suite (see `.kiro/steering/structure.md`); the Node/browser E2E
   belongs with the Node app. The two trees are separated by language + scope on
   purpose, not by oversight.

The E2E suite still reaches admin-api, mcp-server, and Keycloak at runtime — it
is system-level in *behaviour* — but it is bound to the admin-ui deployable and
its Node toolchain, which is why it is packaged with the app.

> This placement is recorded in the structure steering file
> (`.kiro/steering/structure.md`, "Testing layout" note). If the convention
> changes, update both this README and the steering file, plus
> `.github/workflows/playwright.yml`, the `Makefile` `test:e2e*` targets, and the
> `.gitignore` e2e-artifact rules.

## Run artifacts (git-ignored)

Generated per run and never committed (see the repo `.gitignore`):

- `test-results/` — per-test traces, videos, failure screenshots
- `playwright-report/` — generated HTML report
- `state.json` — the OIDC session storage state (contains session cookies)

Only the **source** under `e2e/` (specs, page objects, fixtures, config, these
docs) is tracked.
