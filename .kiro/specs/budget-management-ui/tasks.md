# Implementation Plan: Budget Management UI

## Overview

TDD-first implementation of budget management in the AdminJS admin console. Each functional area follows the pattern: write failing tests → implement code to pass → verify. Dependencies flow bottom-up: admin-api extension → pure utilities → BFF routes → React components → AdminJS wiring.

**Languages:** TypeScript (admin-ui BFF, components, utilities), Python (admin-api extension)

## Tasks

- [x] 1. Admin-API budget removal extension (Python)
  - [x] 1.1 Write pytest tests for budget removal via PATCH
    - Test PATCH with `{ constraints: { budget: null } }` removes budget from stored constraints
    - Test budget_counters rows are cleaned up on removal
    - Test audit event `budget.config_updated` emitted with removal payload
    - Test "budget absent from body" (not sent) leaves existing budget untouched
    - Use httpx + pytest-asyncio against the FastAPI test client
    - _Requirements: 4.2, 4.3_
  - [x] 1.2 Implement budget removal in PATCH handler
    - Distinguish "field not sent" vs "field sent as null" using `model_fields_set`
    - When `budget` in `body.constraints.model_fields_set` and value is None: delete budget key + clean up budget_counters
    - Emit `budget.config_updated` audit event with `action: "removed"`
    - _Requirements: 4.2, 4.3, 4.4_

- [x] 2. Pure utility functions (TypeScript)
  - [x] 2.1 Write unit + property tests for budget-validate.ts
    - Unit tests: specific invalid/valid examples (ceiling=0, ceiling=-1, ceiling=1.5, threshold=101, threshold=0)
    - Unit tests: ceiling+period co-dependency (one provided without the other)
    - _Requirements: 2.4, 2.5_
  - [x]* 2.2 Write property test for validateBudgetInput (fast-check)
    - **Property 5: Budget validation rejects all invalid inputs**
    - Generate random invalid ceilings (zero, negative, float, NaN, non-numeric) and thresholds outside [1,100]
    - Assert `{ valid: false }` with non-empty errors array for all
    - **Validates: Requirements 2.4, 2.5**
  - [x] 2.3 Implement budget-validate.ts
    - `validateBudgetInput(ceiling, period, thresholds)` → `{ valid: boolean; errors: string[] }`
    - Ceiling must be positive integer (>=1)
    - Each threshold must be integer in [1, 100]
    - If ceiling or period provided, both are required
    - _Requirements: 2.4, 2.5_
  - [x] 2.4 Write unit + property tests for budget-format.ts
    - Unit tests: formatPeriod with known dates, midnight boundaries, month transitions
    - Unit tests: edge cases (same-day period, year boundary)
    - _Requirements: 1.3_
  - [x]* 2.5 Write property test for formatPeriod (fast-check)
    - **Property 2: Period formatter produces valid output**
    - Generate random valid period strings and ISO 8601 timestamps
    - Assert non-empty string containing period type and both date representations
    - **Validates: Requirements 1.3**
  - [x] 2.6 Implement budget-format.ts
    - `formatPeriod(period, periodStart, periodEnd)` → human-readable string
    - E.g. "Daily: Jun 15, 2026 00:00 UTC – Jun 16, 2026 00:00 UTC"
    - _Requirements: 1.3_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. BFF route handlers (TypeScript)
  - [x] 4.1 Write integration tests for GET /admin/api/budget/:permId
    - Use supertest against the Express app with admin-api mocked (nock or msw)
    - Test successful proxy: correct upstream URL construction, response forwarded unchanged
    - Test 404 from admin-api → forwarded to client
    - Test 500 from admin-api → forwarded to client
    - Test session extraction: tenant_id comes from session, not URL
    - _Requirements: 6.1, 6.4, 6.5_
  - [x]* 4.2 Write property test for BFF proxy fidelity (fast-check)
    - **Property 6: BFF proxy fidelity**
    - Generate random HTTP statuses (200-599) + JSON bodies
    - Assert BFF returns same status code and same JSON body without modification
    - **Validates: Requirements 6.1, 6.5**
  - [x]* 4.3 Write property test for BFF URL construction (fast-check)
    - **Property 7: BFF URL construction from session**
    - Generate random valid tenantId strings and permId path parameters
    - Assert constructed upstream URL contains `/v1/tenants/{tenantId}/agents/{agentId}/permissions/{permId}`
    - **Validates: Requirements 6.4**
  - [x] 4.4 Implement GET /admin/api/budget/:permId handler
    - Extract tenantId from `req.session.adminUser`
    - Look up permission record for agent_id
    - Proxy to `GET /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget`
    - Forward response status + body unchanged
    - _Requirements: 6.1, 6.4, 6.5_
  - [x] 4.5 Write integration tests for POST /admin/api/budget/:permId/edit
    - Test correct PATCH body sent to admin-api (`{ constraints: { budget: {...} } }`)
    - Test response forwarded unchanged
    - Test 422 from admin-api forwarded
    - _Requirements: 6.3, 6.5_
  - [x] 4.6 Implement POST /admin/api/budget/:permId/edit handler
    - Parse body `{ ceiling, period, alert_thresholds }`
    - Call `apiWrite(PATCH /.../permissions/{pid}, { constraints: { budget: {...} } })`
    - Forward response
    - _Requirements: 6.3, 6.5_
  - [x] 4.7 Write integration tests for POST /admin/api/budget/:permId/remove
    - Test PATCH body sent with `{ constraints: { budget: null } }`
    - Test response forwarded unchanged
    - _Requirements: 6.3, 6.5_
  - [x] 4.8 Implement POST /admin/api/budget/:permId/remove handler
    - Call `apiWrite(PATCH /.../permissions/{pid}, { constraints: { budget: null } })`
    - Forward response
    - _Requirements: 6.3, 6.5_
  - [x] 4.9 Write integration tests for POST /admin/api/budget/:permId/reset
    - Test POST to reset endpoint via apiWrite
    - Test response forwarded unchanged
    - _Requirements: 6.2, 6.5_
  - [x] 4.10 Implement POST /admin/api/budget/:permId/reset handler
    - Call `apiWrite(POST /.../permissions/{pid}/budget/reset)`
    - Forward response
    - _Requirements: 6.2, 6.5_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. React components (TypeScript)
  - [x] 6.1 Write tests for BudgetStatusPanel
    - Test renders progress bar with correct percentage (used/ceiling)
    - Test renders threshold markers at correct positions
    - Test renders period info via formatPeriod
    - Test exhaustion state (used >= ceiling) shows red indicator
    - Test empty state when API returns 404 ("No budget configured")
    - Test error state when API returns 5xx
    - Test action buttons rendered (Edit, Reset, Remove)
    - Use React Testing Library
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_
  - [x]* 6.2 Write property test for progress bar percentage (fast-check)
    - **Property 1: Progress bar percentage accuracy**
    - Generate random `{ used, ceiling }` pairs where ceiling > 0 and 0 <= used <= ceiling
    - Assert computed percentage equals `Math.round((used / ceiling) * 100)`
    - **Validates: Requirements 1.2**
  - [x]* 6.3 Write property test for threshold marker positioning (fast-check)
    - **Property 3: Threshold marker positioning**
    - Generate random alert_thresholds arrays (each integer in [1, 100])
    - Assert each marker's position percentage equals the threshold value
    - **Validates: Requirements 1.4**
  - [x] 6.4 Implement BudgetStatusPanel component
    - Fetch budget data from BFF on mount (`/admin/api/budget/{permId}`)
    - Render progress bar (used/ceiling with percentage label)
    - Render threshold markers positioned at each alert_threshold percentage
    - Render period info using formatPeriod utility
    - Handle exhaustion state (red color when used >= ceiling)
    - Handle empty state (404 → "No budget configured")
    - Handle error state (5xx → "Unable to load budget status" with retry)
    - Render action buttons: Edit Budget, Reset Budget, Remove Budget
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - [x] 6.5 Write tests for BudgetForm
    - Test renders all fields: ceiling input, period dropdown, alert_thresholds input
    - Test create mode (empty fields, optional)
    - Test edit mode (pre-populated from BudgetStatus)
    - Test client-side validation errors displayed for invalid input
    - Test form submission calls correct BFF endpoint
    - _Requirements: 2.1, 2.4, 2.5, 3.1_
  - [x]* 6.6 Write property test for budget form serialization round-trip (fast-check)
    - **Property 4: Budget form serialization round-trip**
    - Generate random valid budget configs (positive integer ceiling, valid period, thresholds in [1,100])
    - Assert serializing form data into request body and parsing back preserves values
    - **Validates: Requirements 2.2, 3.1**
  - [x] 6.7 Implement BudgetForm component
    - Ceiling: number input (min=1, required when budget is being set)
    - Period: dropdown (hourly, daily, weekly, monthly, required when budget is being set)
    - Alert thresholds: text input (comma-separated integers 1-100, optional, defaults [50,80,100])
    - Client-side validation using validateBudgetInput before submission
    - Support create mode (embedded in new action) and edit mode (pre-populated)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. AdminJS resource config wiring (TypeScript)
  - [x] 8.1 Write tests for AdminJS permission resource config
    - Test custom `editBudget` action is registered with correct component
    - Test virtual `_budgetPanel` property renders BudgetStatusPanel on show page
    - Test generic `edit` action remains disabled
    - Test `new` action includes budget form fields
    - _Requirements: 7.1, 7.2, 7.3_
  - [x] 8.2 Implement AdminJS resource config changes
    - Register `editBudget` custom action (actionType: "record", component: BudgetForm)
    - Add virtual property `_budgetPanel` with show component: BudgetStatusPanel
    - Keep generic `edit` disabled (`isVisible: false`)
    - Extend `new` action handler to parse budget fields and include in `constraints.budget`
    - _Requirements: 7.1, 7.2, 7.3_
  - [x] 8.3 Wire confirmation prompts for Remove and Reset actions
    - Remove Budget: confirmation dialog before sending POST to BFF remove
    - Reset Budget: confirmation dialog before sending POST to BFF reset
    - _Requirements: 4.1, 5.1, 5.2_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit/integration tests validate specific examples and edge cases
- TDD discipline: tests are written BEFORE implementation in every functional area
- Admin-API tests use pytest + httpx; all admin-ui tests use vitest
- Property tests use fast-check (standard JS/TS PBT library per vitest ecosystem)
- BFF integration tests use supertest with mocked admin-api (nock or msw)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "2.2"] },
    { "id": 1, "tasks": ["1.2", "2.3", "2.4", "2.5"] },
    { "id": 2, "tasks": ["2.6", "4.1", "4.2", "4.3"] },
    { "id": 3, "tasks": ["4.4", "4.5", "4.7", "4.9"] },
    { "id": 4, "tasks": ["4.6", "4.8", "4.10"] },
    { "id": 5, "tasks": ["6.1", "6.2", "6.3", "6.5", "6.6"] },
    { "id": 6, "tasks": ["6.4", "6.7"] },
    { "id": 7, "tasks": ["8.1"] },
    { "id": 8, "tasks": ["8.2", "8.3"] }
  ]
}
```
