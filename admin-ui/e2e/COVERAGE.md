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
| 12 | `12-services-crud.spec.ts` | Services CRUD round-trip: create→list→show→edit→delete | W1; F-OP-02; T-1.2.3 |
| 13 | `13-credentials-crud.spec.ts` | Credentials CRUD round-trip: attach→list→show→delete | W1; ADR-0018 |
| 14 | `14-agents-crud.spec.ts` | Agents CRUD: create→list→show (no API key)→edit→revoke | W1; ADR-0014.4; T-1.4.3 |
| 15 | `15-permissions-crud.spec.ts` | Permission grants CRUD round-trip | W2; T-1.5.x |
| 16 | `16-api-keys-crud.spec.ts` | API keys CRUD round-trip | W2; ADR-0018 §1.3 |
| 17 | `17-tenants-crud.spec.ts` | Tenants CRUD (PlatformAdmin scoped) | W2; ADR-0016.3 |
| 18 | `18-form-validation.spec.ts` | Form validation: required fields, bad input, error messages | W3 |
| 19 | `19-tenant-isolation.spec.ts` | PlatformAdmin sees all tenants; cross-tenant scoping | W4; ADR-0008 |
| 20 | `20-pagination-sorting.spec.ts` | Pagination (page 1 vs 2) + column sort URL param + direction toggle | W5 |
| 21 | `21-logout-session.spec.ts` | Logout invalidates session; cleared cookies redirect to login | W5; ADR-0019 |
| 22 | `22-write-auth-contract.spec.ts` | mintkey_session cookie present; write returns 200 no-error | W6; ADR-0019; ADR-0014.5 |
| 23 | `23-accessibility.spec.ts` | axe-core WCAG 2.1 AA: dashboard + 7 resource lists + show + new form | W7 |
| 25 | `25-console-error-self-test.spec.ts` | Fixture self-test — proves console-error guard fires | W0 |
| 26 | `26-smoke-regression.spec.ts` | 7 resource lists + tenants new-form: no JS-error box | ADMIN_UI_SPEC §2.1, §4 |
| 27 | `27-intros-dashboard.spec.ts` | SVG diagram + 6-step onboarding + per-resource intros | ux-uplift AC #1, #2 |
| 28 | `28-search-filters.spec.ts` | Filter params cause real row-count narrowing (5 scenarios) | search-filter AC #3, #4 |
| 29 | `29-tenants-pa.spec.ts` | PlatformAdmin sees tenants list with t_default | fix-tenants-403; ADR-0016.3 |
| 30 | `30-show-pages.spec.ts` | All 7 resource show pages: no React #31 / JSON columns render | fix-show-page-react-31; ADR-0019 |

## Fixture

All tests numbered 12+ import `test` from `e2e/fixtures/test.ts`, which extends
Playwright's base `test` with a `consoleErrors` fixture. The fixture captures
`page.on("pageerror")` and `console.error` events and throws after each test
body if any browser error was collected. Benign patterns (Google Font CDN errors
in Firefox) are filtered to avoid false positives in CI.

Tests that intentionally trigger a browser error must be annotated `test.fail()`.

## CI

`.github/workflows/playwright.yml` runs:
- **PR** (on `admin-ui/**`, `admin-api/**`, `docker-compose.yml` changes): chromium only; 30 min timeout.
- **Nightly** (cron `0 2 * * *`): chromium + firefox + webkit in parallel matrix; 60 min timeout.

Both jobs upload HTML report + JUnit XML as artifacts.

## Known cross-browser skips (W8)

| Test | Browser | Reason |
|------|---------|--------|
| `12-services-crud` | webkit | AdminJS/Axios access control errors for localhost API calls |
| `14-agents-crud` | webkit | AxiosError: Network Error — AdminJS/Axios localhost CORS |
| `28-search-filters` (agents smoke) | webkit | AdminJS URL filter params not processed on webkit |

Tracked for follow-up per `PLAYWRIGHT_EXTENSION_PLAN.md W8`.
