# Playwright E2E Coverage Map

> Canonical test tree: `admin-ui/e2e/tests/`
> Config: `admin-ui/e2e/playwright.config.ts`
> Run: `pnpm test:e2e` (chromium only for CI; all browsers locally)

## Test files

| # | File | Description | Source ADR / spec |
|---|------|-------------|-------------------|
| 00 | `00-diagnose.spec.ts` | Environment probe — prints env vars, checks base URL reachable | local |
| 01 | `01-login.spec.ts` | Login flows: valid, invalid, empty, logout, session persistence | F-OP-01; T-1.1.4 |
| 02 | `02-service-crud.spec.ts` | Service create / edit / delete via AdminJS UI | F-OP-02; T-1.2.x |
| 03 | `03-credential.spec.ts` | Credential attach / rotate / view via AdminJS UI | ADR-0018 |
| 04 | `04-agent.spec.ts` | Agent create / revoke via AdminJS UI | T-1.4.x |
| 05 | `05-permissions.spec.ts` | Permission grant create / delete via AdminJS UI | T-1.5.x |
| 06 | `06-api-keys.spec.ts` | API key create / revoke via AdminJS UI | ADR-0018 §1.3 |
| 07 | `07-audit.spec.ts` | Audit event list renders after state changes | ADR-0014.7 |
| 08 | `08-tenants.spec.ts` | Tenant list, show, create (PlatformAdmin scoped) | ADR-0016.3 |
| 09 | `09-settings.spec.ts` | Settings list / edit via AdminJS UI | T-1.9.x |
| 10 | `10-security.spec.ts` | CSRF protection; unauthenticated 401 redirect | ADR-0019 |
| 11 | `11-service-onboarding.spec.ts` | Full happy-path onboarding wizard | F-OP-03 |
| 25 | `25-console-error-self-test.spec.ts` | Fixture self-test — proves console-error guard fires | W0 |
| 26 | `26-smoke-regression.spec.ts` | 7 resource lists + tenants new-form: no JS-error box | ADMIN_UI_SPEC §2.1, §4 |
| 27 | `27-intros-dashboard.spec.ts` | SVG diagram + 6-step onboarding + per-resource intros | ux-uplift AC #1, #2 |
| 28 | `28-search-filters.spec.ts` | Filter params cause real row-count narrowing (5 scenarios) | search-filter AC #3, #4 |
| 29 | `29-tenants-pa.spec.ts` | PlatformAdmin sees tenants list with t_default | fix-tenants-403; ADR-0016.3 |
| 30 | `30-show-pages.spec.ts` | All 7 resource show pages: no React #31 / JSON columns render | fix-show-page-react-31; ADR-0019 |

## Fixture

All tests numbered 25+ import `test` from `e2e/fixtures/test.ts`, which extends
Playwright's base `test` with a `consoleErrors` fixture. The fixture captures
`page.on("pageerror")` and `console.error` events and throws after each test
body if any browser error was collected.

Tests that intentionally trigger a browser error must be annotated `test.fail()`.

## Gaps / planned W1-W8 additions

| Chunk | Planned file(s) | Coverage area |
|-------|----------------|---------------|
| W1 | `31-audit-hash-chain.spec.ts` | Audit hash-chain integrity via UI |
| W2 | `32-credential-rotation.spec.ts` | Credential rotation golden path |
| W3 | `33-permission-subset.spec.ts` | Permission ⊆ grant enforcement |
| W4 | `34-mcp-token-flow.spec.ts` | MCP → broker JWT exchange |
| W5 | `35-tenant-isolation.spec.ts` | Cross-tenant isolation: data not visible |
| W6 | `36-api-key-lifecycle.spec.ts` | API key create / revoke / expired states |
| W7 | `37-settings-crud.spec.ts` | Settings CRUD with validation |
| W8 | `38-observability-metrics.spec.ts` | /metrics endpoints reachable |
