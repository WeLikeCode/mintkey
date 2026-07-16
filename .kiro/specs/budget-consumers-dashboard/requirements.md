# Requirements Document

## Introduction

A dedicated AdminJS custom page at `/admin/pages/budget-consumers` showing a live table of all budget-configured permission grants ranked by consumption percentage. Operators can quickly identify agents approaching or exceeding budget limits and unlock (reset) exhausted budgets directly from the table. The page auto-polls for freshness without requiring WebSocket infrastructure.

## Glossary

- **Admin_UI**: The AdminJS 7.x-based operator console (Node 20, Express BFF). Holds no direct DB connection per ADR-0019.
- **Admin_API**: The Python FastAPI REST API that owns all data access and business logic.
- **Budget_Consumers_Page**: The custom AdminJS page at `/admin/pages/budget-consumers`.
- **BFF_Route**: An Express route in admin-ui that proxies requests to admin-api (ADR-0019 pattern).
- **Aggregation_Endpoint**: The new `GET /v1/tenants/{tid}/budget-consumers` admin-api endpoint that performs server-side joins across permission_grants, budget_counters, agents, and services.
- **Consumption_Percentage**: The ratio `(used / ceiling) * 100`, representing how much of a budget period allocation has been consumed.
- **Exhausted_Budget**: A budget where `used >= ceiling` (consumption percentage >= 100%).
- **Budget_Reset**: The action of setting `used = 0` on a budget counter, re-enabling proxied requests for the permission grant.

## Requirements

### Requirement 1: Navigation Entry

**User Story:** As an operator, I want a sidebar navigation item leading to the budget consumers page, so that I can quickly access the budget consumption overview.

#### Acceptance Criteria

1. THE Admin_UI SHALL render a "Budget Consumers" navigation item in the AdminJS sidebar.
2. WHEN the operator clicks the "Budget Consumers" navigation item, THE Admin_UI SHALL navigate to `/admin/pages/budget-consumers`.
3. THE Budget_Consumers_Page SHALL be accessible to all authenticated operators regardless of platform-admin status.

### Requirement 2: Aggregation Endpoint

**User Story:** As the admin-ui BFF, I want a single admin-api endpoint that returns all budget-configured grants with consumption data, so that the page can render without multiple round-trips.

#### Acceptance Criteria

1. THE Admin_API SHALL expose `GET /v1/tenants/{tid}/budget-consumers` returning a JSON array of budget consumer records.
2. WHEN the Aggregation_Endpoint is called, THE Admin_API SHALL join permission_grants, budget_counters, agents, and services to produce each record.
3. THE Aggregation_Endpoint SHALL return for each record: agent_name, service_name, consumption_percentage, used_count, ceiling, period, and requests_last_30_min.
4. THE Aggregation_Endpoint SHALL compute requests_last_30_min by counting audit events with type "token.issued" for the permission within the last 30 minutes.
5. THE Aggregation_Endpoint SHALL return only permission grants that have a budget constraint configured.
6. THE Aggregation_Endpoint SHALL scope results to the authenticated operator's tenant (tenant isolation via session).

### Requirement 3: BFF Proxy Route

**User Story:** As the admin-ui, I want a BFF route that proxies the aggregation endpoint, so that the React page can fetch data without direct admin-api access from the browser.

#### Acceptance Criteria

1. THE Admin_UI SHALL expose `GET /admin/api/budget-consumers` as a BFF route behind the requireSession middleware.
2. WHEN the BFF_Route receives a request, THE Admin_UI SHALL extract tenant_id from the operator session and proxy to `GET /v1/tenants/{tid}/budget-consumers` on admin-api.
3. THE BFF_Route SHALL forward the admin-api response status and body unchanged to the caller.
4. IF the admin-api returns an error status, THEN THE BFF_Route SHALL forward the error response unchanged.

### Requirement 4: Table Display

**User Story:** As an operator, I want to see a table of budget consumers ranked by consumption, so that I can identify agents closest to exhausting their budgets.

#### Acceptance Criteria

1. THE Budget_Consumers_Page SHALL render a table with columns: Agent Name, Service Name, Consumption %, Used, Ceiling, Period, Requests (30 min).
2. THE Budget_Consumers_Page SHALL display Consumption % as the formatted ratio `used / ceiling` expressed as a percentage.
3. THE Budget_Consumers_Page SHALL sort rows by Consumption % in descending order by default (highest consumers first).
4. WHEN the table contains zero rows, THE Budget_Consumers_Page SHALL display an empty state message indicating no budget-configured grants exist.

### Requirement 5: Filtering

**User Story:** As an operator, I want to filter the budget consumers table by threshold, agent, and service, so that I can narrow down to specific areas of concern.

#### Acceptance Criteria

1. THE Budget_Consumers_Page SHALL provide a consumption threshold filter accepting a percentage value (e.g. 80) and showing only rows where consumption_percentage exceeds the threshold.
2. THE Budget_Consumers_Page SHALL provide an agent name filter accepting a text value and showing only rows where agent_name contains the filter value (case-insensitive).
3. THE Budget_Consumers_Page SHALL provide a service name filter accepting a text value and showing only rows where service_name contains the filter value (case-insensitive).
4. WHEN multiple filters are active simultaneously, THE Budget_Consumers_Page SHALL apply all filters as a logical AND (intersection).

### Requirement 6: Unlock (Reset) Action

**User Story:** As an operator, I want to reset an exhausted budget directly from the table, so that I can re-enable a blocked agent without navigating to the individual permission page.

#### Acceptance Criteria

1. WHILE a row has consumption_percentage >= 100 (used >= ceiling), THE Budget_Consumers_Page SHALL display an "Unlock" button on that row.
2. WHEN the operator clicks the "Unlock" button, THE Budget_Consumers_Page SHALL send a POST request to the existing BFF budget reset endpoint (`/admin/api/budget/:permId/reset`).
3. WHEN the reset request succeeds, THE Budget_Consumers_Page SHALL refresh the table data to reflect the updated state.
4. IF the reset request fails, THEN THE Budget_Consumers_Page SHALL display an inline error message on the affected row.
5. THE Budget_Consumers_Page SHALL NOT display the "Unlock" button on rows where used < ceiling.

### Requirement 7: Auto-Polling

**User Story:** As an operator, I want the table to auto-refresh periodically, so that I see near-real-time consumption data without manual page reloads.

#### Acceptance Criteria

1. THE Budget_Consumers_Page SHALL poll the BFF_Route every 30 seconds to refresh table data.
2. THE Budget_Consumers_Page SHALL display a "Last updated" timestamp indicator showing when data was last successfully fetched.
3. WHEN a poll request fails, THE Budget_Consumers_Page SHALL retain the previously displayed data and update the "Last updated" indicator to show the failure.
4. WHEN the operator navigates away from the page, THE Budget_Consumers_Page SHALL stop the polling interval.

### Requirement 8: Exhausted Budget Visual Indicator

**User Story:** As an operator, I want exhausted budgets to be visually prominent, so that I can immediately identify blocked agents.

#### Acceptance Criteria

1. WHILE a row has consumption_percentage >= 100, THE Budget_Consumers_Page SHALL apply a red visual indicator (row highlight or badge) to that row.
2. THE Budget_Consumers_Page SHALL visually differentiate exhausted rows from non-exhausted rows without requiring the operator to read the numeric percentage.
