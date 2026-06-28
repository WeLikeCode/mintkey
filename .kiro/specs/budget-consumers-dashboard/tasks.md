# Implementation Plan: Budget Consumers Dashboard

## Overview

A dedicated AdminJS custom page showing a live table of all budget-configured permission grants ranked by consumption percentage. Implementation follows the BFF pattern (ADR-0019): admin-api aggregation endpoint → BFF proxy route → React custom page. TDD discipline throughout — tests before implementation in every layer.

## Tasks

- [x] 1. Admin-API aggregation endpoint (Python)
  - [x] 1.1 Write pytest tests for the aggregation endpoint
    - Create `apps/admin-api/tests/api/test_budget_consumers.py`
    - Test: returns only budget-configured grants (seeded mix of grants with/without budget)
    - Test: response contains all required fields per BudgetConsumerRecord schema
    - Test: consumption_percentage computed as round((used/ceiling)*100)
    - Test: results sorted by consumption% descending, exhausted first
    - Test: requests_last_30_min counts audit events correctly
    - Test: tenant isolation — multi-tenant seed, verify no cross-tenant leakage
    - Test: empty result for tenant with no budget-configured grants
    - Test: 401 without valid session
    - Use httpx + pytest-asyncio + testcontainers pattern
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 1.2 Implement the aggregation endpoint
    - Create `apps/admin-api/src/admin_api/api/budget_consumers.py`
    - Router: `GET /v1/tenants/{tenant_id}/budget-consumers`
    - SQL join across permission_grants, budget_counters, agents, services
    - Compute consumption_percentage server-side: `round((used / ceiling) * 100)`
    - Count audit_events for requests_last_30_min
    - RLS-scoped via `set_tenant_context`
    - Sort: exhausted first, then by consumption% descending
    - Wire IDs in response (perm_, agent_, svc_ prefixes)
    - Register router in the FastAPI app
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 1.3 Write property test for aggregation completeness (Property 1)
    - **Property 1: Aggregation endpoint returns only budget-configured grants with complete fields**
    - Generate random tenant with mix of grants (budget/no-budget)
    - Assert: every returned record has all required fields; no non-budget grants appear
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.5**

  - [ ]* 1.4 Write property test for tenant isolation (Property 2)
    - **Property 2: Tenant isolation on aggregation endpoint**
    - Generate two tenants with seeded budget grants
    - Assert: querying as tenant A returns zero records belonging to tenant B
    - **Validates: Requirements 2.6**

- [x] 2. Checkpoint - Ensure admin-api tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. BFF proxy route (TypeScript)
  - [x] 3.1 Write integration tests for the BFF route
    - Create `apps/admin-ui/src/routes/budget-consumers.test.ts`
    - Use vitest + supertest + nock to mock admin-api upstream
    - Test: GET /admin/api/budget-consumers proxies correctly with tenant from session
    - Test: returns 401 without valid session
    - Test: returns 502 when admin-api is unreachable
    - Test: forwards various HTTP status codes (200, 404, 500) unchanged (proxy fidelity)
    - Test: forwards JSON body unchanged
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 3.2 Implement the BFF budget-consumers route
    - Create `apps/admin-ui/src/routes/budget-consumers.ts`
    - Handler: extract tenantId from session, proxy to admin-api
    - Forward cookie header for auth passthrough
    - Return upstream status + body unchanged
    - Return 401 if no session, 502 on network error
    - Mount as `app.get("/admin/api/budget-consumers", ...)` in Express app
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 3.3 Write property tests for BFF (Properties 3 & 4)
    - **Property 3: BFF URL construction from session**
    - Generate random tenant_id strings; verify URL is `/v1/tenants/{tenantId}/budget-consumers`
    - **Property 4: BFF proxy fidelity**
    - Generate random HTTP status codes (200-599) + random JSON bodies; verify identical forwarding
    - Use fast-check with vitest
    - **Validates: Requirements 3.2, 3.3, 3.4**

- [x] 4. Pure utility functions (TypeScript)
  - [x] 4.1 Write unit tests for filterConsumers and isExhausted
    - Create `apps/admin-ui/src/components/pages/budget-consumers.utils.test.ts`
    - Test filterConsumers: threshold filter only, agent name filter only, service name filter only
    - Test filterConsumers: all filters combined (logical AND)
    - Test filterConsumers: case-insensitive matching
    - Test filterConsumers: empty dataset, no active filters
    - Test isExhausted: used == ceiling → true, used > ceiling → true, used < ceiling → false
    - Test isExhausted: boundary at ceiling-1 → false
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.5, 8.1_

  - [x] 4.2 Implement filterConsumers and isExhausted utilities
    - Create `apps/admin-ui/src/components/pages/budget-consumers.utils.ts`
    - Export `BudgetConsumerRecord` interface
    - Export `FilterState` interface
    - Export `filterConsumers(records, filters)` — logical AND of threshold, agentName, serviceName
    - Export `isExhausted(record)` — returns `used >= ceiling`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.5, 8.1, 8.2_

  - [ ]* 4.3 Write property tests for filter composition (Property 7)
    - **Property 7: Filter composition (logical AND)**
    - Generate random arrays of BudgetConsumerRecord + random FilterState
    - Assert: every visible row passes ALL active filters; every filtered-out row fails at least one
    - Use fast-check with vitest
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

  - [ ]* 4.4 Write property tests for exhausted state (Property 8)
    - **Property 8: Exhausted state determination**
    - Generate random `{ used: nat(), ceiling: nat(min=1) }` pairs
    - Assert: isExhausted returns true iff `used >= ceiling`
    - Use fast-check with vitest
    - **Validates: Requirements 6.1, 6.5, 8.1, 8.2**

  - [ ]* 4.5 Write property test for consumption percentage (Property 5)
    - **Property 5: Consumption percentage computation**
    - Generate random `{ used: nat(), ceiling: nat(min=1) }` pairs
    - Assert: computed percentage equals `Math.round((used / ceiling) * 100)`
    - Use fast-check with vitest
    - **Validates: Requirements 4.2**

  - [ ]* 4.6 Write property test for descending sort (Property 6)
    - **Property 6: Descending sort by consumption percentage**
    - Generate random arrays of records; sort; verify each element's consumption_percentage >= next
    - Use fast-check with vitest
    - **Validates: Requirements 4.3**

- [x] 5. Checkpoint - Ensure all utility and BFF tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. React page component (TypeScript)
  - [x] 6.1 Write component tests for BudgetConsumersPage
    - Create `apps/admin-ui/src/components/pages/BudgetConsumersPage.test.tsx`
    - Use vitest + @testing-library/react
    - Test: renders all expected table columns (Agent Name, Service, Consumption %, Used, Ceiling, Period, Requests 30 min)
    - Test: renders empty state when zero records
    - Test: exhausted rows have red highlight styling
    - Test: "Unlock" button appears only on exhausted rows
    - Test: "Unlock" click triggers POST to `/admin/api/budget/:permId/reset`
    - Test: "Last updated" timestamp renders and updates
    - Test: filter bar renders threshold, agent name, service name inputs
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 8.1, 8.2_

  - [x] 6.2 Implement BudgetConsumersPage component
    - Create `apps/admin-ui/src/components/pages/BudgetConsumersPage.tsx`
    - Fetch from `/admin/api/budget-consumers` on mount + 30s polling interval
    - Render DataTable sorted by consumption% descending (API pre-sorts)
    - FilterBar component: threshold %, agent name, service name inputs
    - Apply `filterConsumers` on client side
    - Red row highlight + "Unlock" button when `isExhausted(record)` is true
    - Unlock: POST to `/admin/api/budget/:permId/reset`; refresh on success; inline error on failure
    - "Last updated" timestamp with stale indicator on poll failure
    - Empty state message when zero records
    - `clearInterval` on unmount
    - Retain previous data on poll failure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2_

- [x] 7. AdminJS wiring and navigation
  - [x] 7.1 Register the page in AdminJS config
    - Add to `componentLoader.add()` in `apps/admin-ui/src/components/index.ts`
    - Add to AdminJS `pages` config in `apps/admin-ui/src/index.ts`: key `"budget-consumers"`, label "Budget Consumers", icon "Activity"
    - Verify: sidebar shows "Budget Consumers" item; navigating to it renders the page
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- TDD discipline: test tasks precede implementation tasks in each area
- Admin-API uses Python (pytest + httpx + testcontainers)
- Admin-UI uses TypeScript (vitest + supertest + fast-check + @testing-library/react)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1", "4.1"] },
    { "id": 1, "tasks": ["1.2", "3.2", "4.2"] },
    { "id": 2, "tasks": ["1.3", "1.4", "3.3", "4.3", "4.4", "4.5", "4.6"] },
    { "id": 3, "tasks": ["6.1"] },
    { "id": 4, "tasks": ["6.2", "7.1"] }
  ]
}
```
